"""
Brain — LLM client and tool-calling loop for Nova.

Provides a provider abstraction (LLMProvider) so Ollama can be swapped
for cloud APIs (Claude, OpenAI) later without rewriting the core loop.
"""

import asyncio
import json
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

import ollama as ollama_pkg

from core.memory import Memory
from core.tool_router import ToolRouter

logger = logging.getLogger(__name__)

_MAX_TOOL_ITERATIONS = 10

# Summarization prompt — asks for JSON with summary + extracted facts.
# Robust parsing handles malformed JSON by extracting what it can.
_SUMMARIZE_PROMPT = """Summarize this conversation briefly. Return ONLY valid JSON in this exact format:
{
  "summary": "2-3 sentences describing what was discussed and accomplished",
  "facts": ["fact about the user worth remembering long-term", "another fact"]
}

Rules:
- summary: what was discussed, what was accomplished, any important outcomes
- facts: ONLY genuinely new, reusable facts about the user (preferences, personal info, work context). Empty list [] if nothing notable.
- Return ONLY the JSON object, no other text.

Conversation:
"""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class LLMResponse:
    """Unified response from any LLM provider."""

    content: str | None = None
    tool_calls: list[dict] | None = None  # List of {name, arguments} dicts


# ---------------------------------------------------------------------------
# Provider abstraction
# ---------------------------------------------------------------------------


class LLMProvider(ABC):
    """Abstract base class for LLM backends."""

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        thinking: bool = False,
    ) -> LLMResponse:
        """
        Send a chat request to the LLM.

        Args:
            messages: Conversation history in OpenAI-style format.
            tools: Optional list of tool definitions (Ollama format).
            thinking: Whether to enable extended reasoning.

        Returns:
            LLMResponse with either content or tool_calls populated.
        """


class OllamaProvider(LLMProvider):
    """Ollama backend using the official Python client."""

    def __init__(self, model: str, base_url: str) -> None:
        self.model = model
        self._client = ollama_pkg.AsyncClient(host=base_url)

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        thinking: bool = False,
    ) -> LLMResponse:
        """
        Call Ollama chat API.

        Thinking is passed via options if the client supports it.
        # TODO: Verify that ollama-python exposes options.think once
        # https://github.com/ollama/ollama-python supports it officially.
        """
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        # Attempt to pass thinking flag via options; silently ignore if
        # the installed ollama package version doesn't support it.
        try:
            kwargs["options"] = {"think": thinking}
        except Exception:  # pragma: no cover
            pass

        response = await self._client.chat(**kwargs)
        msg = response.message

        # Parse tool calls if present
        if msg.tool_calls:
            tool_calls = [
                {
                    "name": tc.function.name,
                    "arguments": dict(tc.function.arguments),
                }
                for tc in msg.tool_calls
            ]
            return LLMResponse(tool_calls=tool_calls)

        # Strip <think>...</think> blocks that Qwen3 emits in thinking mode
        content = msg.content or ""
        content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
        return LLMResponse(content=content)


# ---------------------------------------------------------------------------
# Tool status messages (always visible to the user)
# ---------------------------------------------------------------------------

# Tools that may take a while — show a friendlier message
_TOOL_STATUS: dict[str, str] = {
    "pc_ask_project": "Asking Claude Code about {project}...",
    "pc_claude_code": "Running Claude Code...",
    "pc_open_app": "Opening {target}...",
    "web_search": "Searching the web...",
    "wikipedia_lookup": "Looking up Wikipedia...",
    "summarize_url": "Reading URL...",
    "news_headlines": "Fetching news...",
}


def _print_tool_status(tool_name: str, tool_args: dict) -> None:
    """Print a short user-visible status line when a tool is invoked."""
    template = _TOOL_STATUS.get(tool_name)
    if template:
        try:
            msg = template.format(**tool_args)
        except KeyError:
            msg = template.split("...")[0] + "..."
        print(f"  [{msg}]", flush=True)


# ---------------------------------------------------------------------------
# Brain
# ---------------------------------------------------------------------------


class Brain:
    """
    Orchestrates LLM calls, tool dispatching, and memory persistence.
    """

    def __init__(
        self,
        config: dict,
        memory: Memory,
        tool_router: ToolRouter,
        system_prompt: str,
        long_term_memory=None,  # LongTermMemory | None
    ) -> None:
        self._config = config
        self._memory = memory
        self._tool_router = tool_router
        self._system_prompt = system_prompt
        self._ltm = long_term_memory
        self._summarization_task: asyncio.Task | None = None

        brain_cfg = config.get("brain", {})
        provider_name = brain_cfg.get("provider", "ollama")

        if provider_name == "ollama":
            self._provider: LLMProvider = OllamaProvider(
                model=brain_cfg["model"],
                base_url=brain_cfg["base_url"],
            )
        else:
            raise ValueError(f"Unknown LLM provider: {provider_name}")

        self._thinking: bool = brain_cfg.get("thinking", True)

    # ------------------------------------------------------------------
    # Long-term memory injection
    # ------------------------------------------------------------------

    async def _build_augmented_prompt(self, user_message: str) -> str:
        """
        Append long-term memory context to the system prompt.
        Returns the original prompt unchanged if LTM is disabled.
        """
        if self._ltm is None:
            return self._system_prompt

        sections = []

        facts = await self._ltm.get_facts_for_prompt()
        if facts:
            sections.append(
                "## What Nova knows about you\n"
                + facts
                + "\n*(Use remember_fact / list_facts / forget_fact to manage these)*"
            )

        summaries = await self._ltm.get_summaries_for_prompt(query=user_message)
        if summaries:
            sections.append("## Past conversation context\n" + summaries)

        if not sections:
            return self._system_prompt

        return self._system_prompt + "\n\n" + "\n\n".join(sections)

    # ------------------------------------------------------------------
    # Session summarization (background, non-blocking)
    # ------------------------------------------------------------------

    def _schedule_summarization(self, current_session_id: str) -> None:
        """
        Fire-and-forget: summarize any old unsummarized sessions in the background.
        Does not block the current conversation. Called once per Brain instance.
        """
        if self._ltm is None:
            return
        if self._summarization_task is not None:
            return  # already scheduled

        self._summarization_task = asyncio.create_task(
            self._summarize_old_sessions(current_session_id),
            name="nova-summarize-sessions",
        )
        self._summarization_task.add_done_callback(self._on_summarization_done)

    def _on_summarization_done(self, task: asyncio.Task) -> None:
        if task.exception():
            logger.warning("Background summarization failed: %s", task.exception())

    async def _summarize_old_sessions(self, current_session_id: str) -> None:
        """Summarize all old sessions that haven't been summarized yet."""
        if self._ltm is None:
            return

        pending = await self._ltm.get_sessions_needing_summary(current_session_id)
        if not pending:
            logger.debug("No sessions need summarizing.")
            return

        logger.debug("Summarizing %d old session(s) in background...", len(pending))

        for session_id, messages in pending:
            await self._summarize_session(session_id, messages)

    async def _summarize_session(self, session_id: str, messages: list[dict]) -> None:
        """Summarize a single session and store the result + any extracted facts."""
        try:
            conversation_text = "\n".join(
                f"{m['role'].upper()}: {m['content']}" for m in messages
            )
            prompt = _SUMMARIZE_PROMPT + conversation_text

            response = await self._provider.chat(
                messages=[{"role": "user", "content": prompt}],
                tools=None,
                thinking=False,  # fast, no reasoning needed
            )

            raw = (response.content or "").strip()
            summary, facts = self._parse_summary_response(raw, session_id)

            await self._ltm.add_summary(session_id, summary, len(messages))
            logger.debug("Summarized session %s: %s", session_id, summary[:80])

            for fact in facts:
                if fact.strip():
                    await self._ltm.add_fact(fact.strip(), category="auto")
                    logger.debug("Auto-extracted fact: %s", fact)

        except Exception as exc:
            logger.warning("Failed to summarize session %s: %s", session_id, exc)

    def _parse_summary_response(
        self, raw: str, session_id: str
    ) -> tuple[str, list[str]]:
        """
        Robustly parse the LLM's JSON summary response.

        Tries strict JSON parse first. Falls back to regex extraction if the
        LLM returns malformed JSON — we never lose the summary because of a
        formatting mistake.
        """
        # Try strict JSON first
        try:
            # Extract first JSON object if there's surrounding text
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                data = json.loads(match.group())
                summary = str(data.get("summary", "")).strip()
                facts = [str(f) for f in data.get("facts", []) if f]
                if summary:
                    return summary, facts
        except (json.JSONDecodeError, TypeError, KeyError):
            pass

        # Fallback: extract summary with regex
        summary_match = re.search(r'"summary"\s*:\s*"([^"]+)"', raw)
        if summary_match:
            summary = summary_match.group(1).strip()
        else:
            # Last resort: use the raw text truncated as the summary
            summary = raw[:300].strip() or f"Conversation session {session_id}"
            logger.debug(
                "Could not parse summary JSON for session %s — using raw text fallback",
                session_id,
            )

        # Try to extract facts array even if full JSON failed
        facts: list[str] = []
        facts_match = re.search(r'"facts"\s*:\s*\[(.*?)\]', raw, re.DOTALL)
        if facts_match:
            for item in re.findall(r'"([^"]+)"', facts_match.group(1)):
                facts.append(item)

        return summary, facts

    # ------------------------------------------------------------------
    # Main chat loop
    # ------------------------------------------------------------------

    async def chat(self, user_message: str, session_id: str) -> str:
        """
        Process a user message through the full tool-calling loop.

        1. Schedule background summarization of old sessions (non-blocking).
        2. Save user message to memory.
        3. Build context (augmented system prompt + conversation history).
        4. Call LLM.
        5. If tool call: dispatch, save result, loop back (max 10 times).
        6. Save final assistant response to memory.
        7. Return final text response.

        Args:
            user_message: Raw input from the user.
            session_id: Identifies the conversation session.

        Returns:
            The assistant's final natural language response.
        """
        # 1. Fire-and-forget background summarization (doesn't block this message)
        self._schedule_summarization(session_id)

        # 2. Persist user message
        await self._memory.add_message(session_id, "user", user_message)

        # 3. Build message list with long-term memory injected
        max_ctx = self._config.get("memory", {}).get("max_context_messages", 20)
        history = await self._memory.get_context(session_id, max_messages=max_ctx)
        augmented_prompt = await self._build_augmented_prompt(user_message)
        messages = [{"role": "system", "content": augmented_prompt}] + history

        tools = self._tool_router.get_tool_definitions()

        # 4–6. Tool-calling loop
        # Track expensive tool calls that returned substantial results so we
        # can block the LLM from re-calling them (it gets confused by large
        # tool outputs and loops). Keyed by (name, args_json).
        _completed_expensive: dict[tuple[str, str], str] = {}
        _EXPENSIVE_RESULT_THRESHOLD = 500  # chars — below this, allow re-calls

        for iteration in range(_MAX_TOOL_ITERATIONS):
            response = await self._provider.chat(
                messages=messages,
                tools=tools or None,
                thinking=self._thinking,
            )

            if response.tool_calls:
                force_text = False
                for tc in response.tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc.get("arguments", {})

                    # Detect duplicate call to a tool that already returned a
                    # large result — the LLM is looping, not making progress.
                    call_sig = (tool_name, json.dumps(tool_args, sort_keys=True))
                    if call_sig in _completed_expensive:
                        logger.warning(
                            "Duplicate tool call detected: %s — forcing text response",
                            tool_name,
                        )
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "You already called that tool and got a result. "
                                    "Please answer based on the information you have."
                                ),
                            }
                        )
                        force_text = True
                        break

                    logger.debug("[tool] → %s(%s)", tool_name, tool_args)
                    # Always show tool activity to the user so they know Nova isn't stuck
                    _print_tool_status(tool_name, tool_args)

                    result = await self._tool_router.dispatch(tool_name, tool_args)
                    logger.debug("[tool] ← %s: %s", tool_name, result)

                    # Add assistant tool-call turn and tool result to in-memory
                    # message list (not persisted — tool turns are transient)
                    messages.append(
                        {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": tool_name,
                                        "arguments": tool_args,
                                    }
                                }
                            ],
                        }
                    )
                    messages.append(
                        {"role": "tool", "content": result, "name": tool_name}
                    )

                    # Persist tool result to memory
                    await self._memory.add_message(
                        session_id, "tool", result, tool_name=tool_name
                    )

                    # Track expensive calls so we can block duplicate re-calls
                    if len(result) >= _EXPENSIVE_RESULT_THRESHOLD:
                        _completed_expensive[call_sig] = result

                if force_text:
                    # Continue the outer loop so the LLM gets another chance
                    # to produce a text response instead of re-calling a tool.
                    continue
            else:
                # Final text response
                final_text = response.content or ""
                if not final_text.strip():
                    # LLM returned empty content — use a safe fallback so the
                    # user always gets a response rather than silent nothing.
                    final_text = "Done."
                await self._memory.add_message(session_id, "assistant", final_text)
                return final_text

        # Safety fallback — should rarely hit this
        logger.warning("Reached max tool iterations (%d)", _MAX_TOOL_ITERATIONS)
        fallback = "I'm sorry, I got stuck in a loop trying to answer that. Please try again."
        await self._memory.add_message(session_id, "assistant", fallback)
        return fallback

"""
Brain — LLM client and tool-calling loop for Nova.

Provides a provider abstraction (LLMProvider) so Ollama can be swapped
for cloud APIs (Claude, OpenAI) later without rewriting the core loop.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

import ollama as ollama_pkg

from core.memory import Memory
from core.tool_router import ToolRouter

logger = logging.getLogger(__name__)

_MAX_TOOL_ITERATIONS = 10


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

        return LLMResponse(content=msg.content)


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
    ) -> None:
        self._config = config
        self._memory = memory
        self._tool_router = tool_router
        self._system_prompt = system_prompt

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

    async def chat(self, user_message: str, session_id: str) -> str:
        """
        Process a user message through the full tool-calling loop.

        1. Save user message to memory.
        2. Build context (system prompt + conversation history).
        3. Call LLM.
        4. If tool call: dispatch, save result, loop back (max 10 times).
        5. Save final assistant response to memory.
        6. Return final text response.

        Args:
            user_message: Raw input from the user.
            session_id: Identifies the conversation session.

        Returns:
            The assistant's final natural language response.
        """
        # 1. Persist user message
        await self._memory.add_message(session_id, "user", user_message)

        # 2. Build message list
        max_ctx = (
            self._config.get("memory", {}).get("max_context_messages", 20)
        )
        history = await self._memory.get_context(session_id, max_messages=max_ctx)
        messages = [{"role": "system", "content": self._system_prompt}] + history

        tools = self._tool_router.get_tool_definitions()

        # 3–5. Tool-calling loop
        for iteration in range(_MAX_TOOL_ITERATIONS):
            response = await self._provider.chat(
                messages=messages,
                tools=tools or None,
                thinking=self._thinking,
            )

            if response.tool_calls:
                for tc in response.tool_calls:
                    tool_name = tc["name"]
                    tool_args = tc.get("arguments", {})
                    logger.info("Tool call: %s(%s)", tool_name, tool_args)

                    result = await self._tool_router.dispatch(tool_name, tool_args)
                    logger.debug("Tool result: %s", result)

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
            else:
                # Final text response
                final_text = response.content or ""
                await self._memory.add_message(session_id, "assistant", final_text)
                return final_text

        # Safety fallback — should rarely hit this
        logger.warning("Reached max tool iterations (%d)", _MAX_TOOL_ITERATIONS)
        fallback = "I'm sorry, I got stuck in a loop trying to answer that. Please try again."
        await self._memory.add_message(session_id, "assistant", fallback)
        return fallback

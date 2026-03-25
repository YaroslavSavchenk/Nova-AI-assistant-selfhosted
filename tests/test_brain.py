"""
Tests for core/brain.py

The OllamaProvider is mocked so no real Ollama instance is needed.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from core.brain import Brain, LLMResponse, OllamaProvider
from core.long_term_memory import LongTermMemory
from core.memory import Memory
from core.tool_router import ToolRouter
from modules.base import NovaModule


# ---------------------------------------------------------------------------
# Helpers & fixtures
# ---------------------------------------------------------------------------


def make_config(thinking: bool = False) -> dict:
    return {
        "brain": {
            "provider": "ollama",
            "model": "qwen3:14b",
            "base_url": "http://localhost:11434",
            "thinking": thinking,
        },
        "memory": {
            "db_path": ":memory:",  # not used directly — Memory is injected
            "max_context_messages": 20,
        },
    }


class EchoModule(NovaModule):
    name = "echo"
    description = "Echoes text"
    parameters = {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    }

    async def run(self, **kwargs) -> str:
        try:
            return f"Echo: {kwargs.get('text', '')}"
        except Exception as exc:
            return f"Echo error: {exc}"


class CounterModule(NovaModule):
    """Counts how many times it has been called — used for multi-step tests."""
    name = "counter"
    description = "Returns call count"
    parameters = {"type": "object", "properties": {}}
    call_count: int = 0

    async def run(self, **kwargs) -> str:
        CounterModule.call_count += 1
        return f"Call #{CounterModule.call_count}"


@pytest_asyncio.fixture
async def memory(tmp_path):
    db_path = str(tmp_path / "brain_test.db")
    mem = Memory(db_path=db_path)
    await mem.init()
    return mem


@pytest_asyncio.fixture
def router():
    r = ToolRouter()
    r.register(EchoModule())
    return r


def make_brain(memory, router, config=None):
    cfg = config or make_config()
    brain = Brain(
        config=cfg,
        memory=memory,
        tool_router=router,
        system_prompt="You are Nova.",
    )
    return brain


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_plain_text_response(memory, router):
    """A plain LLM text response (no tool calls) is returned directly."""
    brain = make_brain(memory, router)
    brain._provider = AsyncMock()
    brain._provider.chat = AsyncMock(
        return_value=LLMResponse(content="Hello there!", tool_calls=None)
    )

    result = await brain.chat("Hi", session_id="test")
    assert result == "Hello there!"

    # Verify message was persisted
    ctx = await memory.get_context("test")
    roles = [m["role"] for m in ctx]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_single_tool_call(memory, router):
    """LLM calls echo tool, result is fed back, LLM returns final response."""
    brain = make_brain(memory, router)

    # First call → tool call; second call → final text
    brain._provider.chat = AsyncMock(
        side_effect=[
            LLMResponse(
                content=None,
                tool_calls=[{"name": "echo", "arguments": {"text": "ping"}}],
            ),
            LLMResponse(content="The echo said: Echo: ping", tool_calls=None),
        ]
    )

    result = await brain.chat("Echo ping for me", session_id="test")
    assert result == "The echo said: Echo: ping"
    assert brain._provider.chat.call_count == 2


@pytest.mark.asyncio
async def test_multi_step_tool_calls(memory, router):
    """LLM makes two sequential tool calls before producing a final response."""
    router.register(CounterModule())
    CounterModule.call_count = 0
    brain = make_brain(memory, router)

    brain._provider.chat = AsyncMock(
        side_effect=[
            LLMResponse(
                content=None,
                tool_calls=[{"name": "counter", "arguments": {}}],
            ),
            LLMResponse(
                content=None,
                tool_calls=[{"name": "counter", "arguments": {}}],
            ),
            LLMResponse(content="Done after two tool calls.", tool_calls=None),
        ]
    )

    result = await brain.chat("Count twice", session_id="multi")
    assert result == "Done after two tool calls."
    assert brain._provider.chat.call_count == 3
    assert CounterModule.call_count == 2


@pytest.mark.asyncio
async def test_tool_not_found_returns_graceful_error(memory, router):
    """Calling a non-existent tool returns a graceful error string, not an exception."""
    brain = make_brain(memory, router)

    brain._provider.chat = AsyncMock(
        side_effect=[
            LLMResponse(
                content=None,
                tool_calls=[{"name": "nonexistent_tool", "arguments": {}}],
            ),
            LLMResponse(content="I could not find that tool.", tool_calls=None),
        ]
    )

    # Should not raise
    result = await brain.chat("Use a fake tool", session_id="err")
    assert result == "I could not find that tool."
    assert brain._provider.chat.call_count == 2


@pytest.mark.asyncio
async def test_tool_not_found_passes_error_to_llm(memory, router):
    """The 'Tool not found' error string is included in messages sent back to LLM."""
    brain = make_brain(memory, router)
    captured_messages = []

    async def mock_chat(messages, tools=None, thinking=False):
        captured_messages.append(messages[:])
        if len(captured_messages) == 1:
            return LLMResponse(
                content=None,
                tool_calls=[{"name": "ghost", "arguments": {}}],
            )
        return LLMResponse(content="OK", tool_calls=None)

    brain._provider.chat = mock_chat

    await brain.chat("invoke ghost", session_id="ghost_test")

    # The second call should include a tool message with the error
    second_call_messages = captured_messages[1]
    tool_messages = [m for m in second_call_messages if m.get("role") == "tool"]
    assert any("Tool not found: ghost" in m["content"] for m in tool_messages)


# ---------------------------------------------------------------------------
# Long-term memory integration tests
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def ltm(tmp_path):
    """Initialised LongTermMemory for Brain integration tests."""
    db = LongTermMemory(db_path=str(tmp_path / "brain_ltm_test.db"), semantic_search=False)
    await db.init()
    return db


def make_brain_with_ltm(memory, router, ltm):
    return Brain(
        config=make_config(),
        memory=memory,
        tool_router=router,
        system_prompt="You are Nova.",
        long_term_memory=ltm,
    )


@pytest.mark.asyncio
async def test_augmented_prompt_without_ltm(memory, router):
    """When LTM is None, _build_augmented_prompt returns the original prompt unchanged."""
    brain = make_brain(memory, router)
    brain._system_prompt = "Base prompt."
    result = await brain._build_augmented_prompt("hello")
    assert result == "Base prompt."


@pytest.mark.asyncio
async def test_augmented_prompt_injects_facts(memory, router, ltm):
    """When LTM has facts, they appear in the augmented system prompt."""
    await ltm.add_fact("I prefer dark mode")
    await ltm.add_fact("I work in Python")

    brain = make_brain_with_ltm(memory, router, ltm)
    brain._system_prompt = "Base prompt."
    result = await brain._build_augmented_prompt("hello")

    assert "I prefer dark mode" in result
    assert "I work in Python" in result
    assert "Base prompt." in result


@pytest.mark.asyncio
async def test_augmented_prompt_injects_summaries(memory, router, ltm):
    """When LTM has summaries, they appear in the augmented system prompt."""
    await ltm.add_summary("sess-old", "We discussed Docker setup.", 6)

    brain = make_brain_with_ltm(memory, router, ltm)
    brain._system_prompt = "Base prompt."
    result = await brain._build_augmented_prompt("hello")

    assert "We discussed Docker setup." in result


@pytest.mark.asyncio
async def test_augmented_prompt_base_returned_when_ltm_empty(memory, router, ltm):
    """When LTM is enabled but empty, original prompt is returned unchanged."""
    brain = make_brain_with_ltm(memory, router, ltm)
    brain._system_prompt = "Base prompt."
    result = await brain._build_augmented_prompt("hello")
    assert result == "Base prompt."


@pytest.mark.asyncio
async def test_chat_uses_augmented_prompt(memory, router, ltm):
    """brain.chat() injects facts into the system message sent to the LLM."""
    await ltm.add_fact("My name is Sava")
    brain = make_brain_with_ltm(memory, router, ltm)

    captured_messages = []

    async def mock_chat(messages, tools=None, thinking=False):
        captured_messages.append(messages[:])
        return LLMResponse(content="Hello Sava!", tool_calls=None)

    brain._provider.chat = mock_chat

    await brain.chat("Hi", session_id="ltm-test")

    system_message = captured_messages[0][0]
    assert system_message["role"] == "system"
    assert "My name is Sava" in system_message["content"]


# ---------------------------------------------------------------------------
# _parse_summary_response tests
# ---------------------------------------------------------------------------


def make_parser_brain():
    """Minimal Brain instance for testing _parse_summary_response only."""
    config = make_config()
    mem = MagicMock()
    router = ToolRouter()
    brain = Brain(
        config=config,
        memory=mem,
        tool_router=router,
        system_prompt="",
    )
    return brain


def test_parse_summary_valid_json():
    brain = make_parser_brain()
    raw = '{"summary": "We talked about Python.", "facts": ["User likes Python"]}'
    summary, facts = brain._parse_summary_response(raw, "sess-1")
    assert summary == "We talked about Python."
    assert facts == ["User likes Python"]


def test_parse_summary_valid_json_no_facts():
    brain = make_parser_brain()
    raw = '{"summary": "Just a chat.", "facts": []}'
    summary, facts = brain._parse_summary_response(raw, "sess-2")
    assert summary == "Just a chat."
    assert facts == []


def test_parse_summary_json_with_surrounding_text():
    brain = make_parser_brain()
    raw = 'Here is the result: {"summary": "Discussed music.", "facts": ["User likes jazz"]} — end'
    summary, facts = brain._parse_summary_response(raw, "sess-3")
    assert summary == "Discussed music."
    assert "User likes jazz" in facts


def test_parse_summary_malformed_json_regex_fallback():
    brain = make_parser_brain()
    # Broken JSON — mismatched quotes but summary key is readable
    raw = '{"summary": "Talked about Docker.", "facts": ["User runs Linux"]'
    summary, facts = brain._parse_summary_response(raw, "sess-4")
    # Should extract summary via regex fallback
    assert "Docker" in summary or "Talked" in summary


def test_parse_summary_no_json_raw_fallback():
    brain = make_parser_brain()
    raw = "The user asked about Spotify. Nothing else notable."
    summary, facts = brain._parse_summary_response(raw, "sess-5")
    assert "Spotify" in summary
    assert isinstance(facts, list)


def test_parse_summary_empty_string_uses_session_id():
    brain = make_parser_brain()
    summary, facts = brain._parse_summary_response("", "sess-fallback")
    assert "sess-fallback" in summary
    assert isinstance(facts, list)


# ---------------------------------------------------------------------------
# _STOP_AFTER_TOOLS tests
# ---------------------------------------------------------------------------


class StopAfterModule(NovaModule):
    """Fake module that uses a _STOP_AFTER_TOOLS name."""
    name = "cc_workflow_add_step"
    description = "Add step to workflow"
    parameters = {
        "type": "object",
        "properties": {"prompt": {"type": "string"}},
        "required": ["prompt"],
    }

    async def run(self, **kwargs) -> str:
        return "Step added successfully."


class WorkflowCreateModule(NovaModule):
    """Fake module for cc_workflow_create."""
    name = "cc_workflow_create"
    description = "Create workflow"
    parameters = {
        "type": "object",
        "properties": {"title": {"type": "string"}},
        "required": ["title"],
    }

    async def run(self, **kwargs) -> str:
        return "Workflow created."


class WebSearchModule(NovaModule):
    """Fake web_search module — not in _STOP_AFTER_TOOLS."""
    name = "web_search"
    description = "Search the web"
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    }

    async def run(self, **kwargs) -> str:
        return "Search results here."


@pytest.mark.asyncio
async def test_stop_after_workflow_add_step_forces_text(memory):
    """After cc_workflow_add_step returns, brain injects force-text message
    and the LLM produces text instead of chaining another tool call."""
    router = ToolRouter()
    router.register(StopAfterModule())
    brain = make_brain(memory, router)

    captured_messages = []

    async def mock_chat(messages, tools=None, thinking=False):
        captured_messages.append((messages[:], tools))
        if len(captured_messages) == 1:
            return LLMResponse(
                content=None,
                tool_calls=[{"name": "cc_workflow_add_step",
                             "arguments": {"prompt": "Write tests"}}],
            )
        return LLMResponse(content="Step added!", tool_calls=None)

    brain._provider.chat = mock_chat

    result = await brain.chat("Add a step", session_id="stop-after-test")
    assert result == "Step added!"

    # Check that a force-text user message was injected
    second_call_msgs = captured_messages[1][0]
    user_msgs = [m for m in second_call_msgs if m.get("role") == "user"]
    assert any("Do NOT call any more tools" in m["content"] for m in user_msgs)


@pytest.mark.asyncio
async def test_stop_after_workflow_create_forces_text(memory):
    """After cc_workflow_create returns, brain forces text response."""
    router = ToolRouter()
    router.register(WorkflowCreateModule())
    brain = make_brain(memory, router)

    brain._provider.chat = AsyncMock(
        side_effect=[
            LLMResponse(
                content=None,
                tool_calls=[{"name": "cc_workflow_create",
                             "arguments": {"title": "My workflow"}}],
            ),
            LLMResponse(content="Workflow created successfully.", tool_calls=None),
        ]
    )

    result = await brain.chat("Create a workflow", session_id="stop-create")
    assert result == "Workflow created successfully."
    assert brain._provider.chat.call_count == 2


@pytest.mark.asyncio
async def test_non_stop_after_tool_allows_chaining(memory):
    """web_search is NOT in _STOP_AFTER_TOOLS, so it allows chaining tool calls."""
    router = ToolRouter()
    router.register(WebSearchModule())
    router.register(EchoModule())
    brain = make_brain(memory, router)

    brain._provider.chat = AsyncMock(
        side_effect=[
            # First call: LLM calls web_search
            LLMResponse(
                content=None,
                tool_calls=[{"name": "web_search",
                             "arguments": {"query": "python async"}}],
            ),
            # Second call: LLM chains another tool call (echo)
            LLMResponse(
                content=None,
                tool_calls=[{"name": "echo",
                             "arguments": {"text": "chained"}}],
            ),
            # Third call: final text
            LLMResponse(content="Here are the results.", tool_calls=None),
        ]
    )

    result = await brain.chat("Search and echo", session_id="chain-test")
    assert result == "Here are the results."
    # All three calls should have been made (no early force-text)
    assert brain._provider.chat.call_count == 3


# ---------------------------------------------------------------------------
# _force_text_next tests (tools=None on forced iteration)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_force_text_passes_tools_none_to_llm(memory):
    """When force_text is triggered, the next LLM call passes tools=None."""
    router = ToolRouter()
    router.register(StopAfterModule())
    brain = make_brain(memory, router)

    captured_calls = []

    async def mock_chat(messages, tools=None, thinking=False):
        captured_calls.append({"tools": tools})
        if len(captured_calls) == 1:
            return LLMResponse(
                content=None,
                tool_calls=[{"name": "cc_workflow_add_step",
                             "arguments": {"prompt": "step 1"}}],
            )
        return LLMResponse(content="Done.", tool_calls=None)

    brain._provider.chat = mock_chat

    await brain.chat("Add step", session_id="force-none")

    # First call should have tools (non-None)
    assert captured_calls[0]["tools"] is not None
    # Second call (forced text) should have tools=None
    assert captured_calls[1]["tools"] is None


@pytest.mark.asyncio
async def test_force_text_flag_resets_after_use(memory):
    """After the force-text call completes, subsequent iterations pass tools again."""
    router = ToolRouter()
    router.register(StopAfterModule())
    router.register(EchoModule())
    brain = make_brain(memory, router)

    captured_calls = []

    async def mock_chat(messages, tools=None, thinking=False):
        captured_calls.append({"tools": tools})
        if len(captured_calls) == 1:
            # First: tool call to stop-after tool
            return LLMResponse(
                content=None,
                tool_calls=[{"name": "cc_workflow_add_step",
                             "arguments": {"prompt": "step 1"}}],
            )
        if len(captured_calls) == 2:
            # Second: forced text iteration (tools=None), but LLM returns
            # another tool call anyway (shouldn't happen with tools=None in
            # practice, but let's simulate the LLM deciding to call echo)
            # Actually with tools=None, LLM should return text. Let's return text.
            return LLMResponse(content="Step was added.", tool_calls=None)
        # Should not reach here
        return LLMResponse(content="Extra.", tool_calls=None)

    brain._provider.chat = mock_chat

    result = await brain.chat("Add step", session_id="reset-test")
    assert result == "Step was added."
    # Verify: call 1 had tools, call 2 had tools=None
    assert captured_calls[0]["tools"] is not None
    assert captured_calls[1]["tools"] is None


# ---------------------------------------------------------------------------
# OllamaProvider think-block stripping tests
# ---------------------------------------------------------------------------


class TestThinkBlockStripping:
    """Test the think-block and artifact stripping in OllamaProvider.chat()."""

    @pytest.fixture
    def provider(self):
        """Create an OllamaProvider with mocked client."""
        p = OllamaProvider(model="test", base_url="http://localhost:11434")
        p._client = AsyncMock()
        return p

    def _make_response(self, content, tool_calls=None):
        """Build a fake Ollama response object."""
        msg = MagicMock()
        msg.content = content
        msg.tool_calls = tool_calls
        resp = MagicMock()
        resp.message = msg
        return resp

    @pytest.mark.asyncio
    async def test_strips_closed_think_block(self, provider):
        """<think>...</think> blocks are removed, leaving only the real answer."""
        provider._client.chat = AsyncMock(
            return_value=self._make_response(
                "<think>some reasoning here</think>Real answer"
            )
        )
        result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
        assert result.content == "Real answer"

    @pytest.mark.asyncio
    async def test_strips_multiline_closed_think_block(self, provider):
        """Multiline <think> blocks are fully stripped."""
        provider._client.chat = AsyncMock(
            return_value=self._make_response(
                "<think>line one\nline two\nline three</think>The actual response"
            )
        )
        result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
        assert result.content == "The actual response"

    @pytest.mark.asyncio
    async def test_strips_unclosed_think_block(self, provider):
        """Unclosed <think> blocks strip everything from <think> to end."""
        provider._client.chat = AsyncMock(
            return_value=self._make_response(
                "<think>some reasoning\nmore reasoning"
            )
        )
        result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
        assert result.content == ""

    @pytest.mark.asyncio
    async def test_strips_unicode_artifact(self, provider):
        """The 崧 unicode artifact from Qwen3 is stripped."""
        provider._client.chat = AsyncMock(
            return_value=self._make_response(
                "崧\n\nActual response"
            )
        )
        result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
        assert result.content == "Actual response"

    @pytest.mark.asyncio
    async def test_content_without_think_blocks_unchanged(self, provider):
        """Content without think blocks or artifacts passes through unchanged."""
        provider._client.chat = AsyncMock(
            return_value=self._make_response("Hello, how can I help?")
        )
        result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
        assert result.content == "Hello, how can I help?"

    @pytest.mark.asyncio
    async def test_strips_think_block_with_trailing_whitespace(self, provider):
        """Think block followed by whitespace and content strips cleanly."""
        provider._client.chat = AsyncMock(
            return_value=self._make_response(
                "<think>reasoning</think>\n\n  Final answer here  "
            )
        )
        result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
        assert result.content == "Final answer here"

    @pytest.mark.asyncio
    async def test_strips_artifact_before_think_block(self, provider):
        """Combined artifact + think block is fully stripped."""
        provider._client.chat = AsyncMock(
            return_value=self._make_response(
                "崧\n<think>internal monologue</think>Clean output"
            )
        )
        result = await provider.chat(messages=[{"role": "user", "content": "hi"}])
        assert result.content == "Clean output"

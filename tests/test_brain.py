"""
Tests for core/brain.py

The OllamaProvider is mocked so no real Ollama instance is needed.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from core.brain import Brain, LLMResponse, OllamaProvider
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

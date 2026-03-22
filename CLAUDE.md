# Nova — Personal AI Assistant

Conversational AI assistant (codename "Nova") running on WSL2 (Ubuntu). Python async codebase using a local LLM via Ollama for reasoning, with a modular tool system, persistent memory, and voice interface.

## Hardware & LLM

- **GPU**: NVIDIA RTX 5070 (12 GB VRAM)
- **RAM**: 64 GB DDR5 — **CPU**: Ryzen 7800X3D
- **LLM**: Qwen 3 14B (Q5_K_M quantization) via Ollama on `localhost:11434`
- **Thinking toggle**: Qwen 3 supports `/think` and `/no_think`. Use thinking ON for tool-calling and complex reasoning, thinking OFF for fast casual chat.
- **Future**: `brain.py` uses a provider abstraction (`LLMProvider` base class) so cloud APIs (Claude, OpenAI) can be added later without rewriting the core loop.

## Commands

- `ollama serve` — Start Ollama daemon (must be running before Nova)
- `ollama run qwen3:14b` — Test the model interactively
- `python main.py` — Start Nova in terminal (text mode)
- `python main.py --voice` — Start Nova with voice input/output
- `python -m pytest tests/` — Run all tests
- `python -m pytest tests/ -k "test_module_name"` — Run specific module tests
- `pip install -r requirements.txt --break-system-packages` — Install dependencies

## Architecture

```
nova/
├── main.py                  # Entry point, CLI arg parsing
├── config.yaml              # API keys, model settings, module toggles
├── core/
│   ├── brain.py             # LLM client wrapper, tool-calling loop
│   ├── memory.py            # SQLite-backed conversation + fact memory
│   ├── tool_router.py       # Registers modules, matches LLM tool calls to handlers
│   └── config_loader.py     # Loads and validates config.yaml
├── voice/
│   ├── listener.py          # STT (Speech-to-Text) via Whisper API
│   └── speaker.py           # TTS (Text-to-Speech) via ElevenLabs/Piper
├── modules/                 # Each file = one tool Nova can use
│   ├── base.py              # Abstract base class all modules implement
│   ├── web_search.py
│   ├── calendar_tool.py
│   ├── email_tool.py
│   ├── smart_home.py
│   └── spotify.py
├── data/
│   └── memory.db            # SQLite database (gitignored)
└── tests/
    ├── test_brain.py
    ├── test_memory.py
    └── test_modules/
```

## Module Contract

Every module in `modules/` MUST inherit from `modules.base.NovaModule` and implement:

```python
class MyModule(NovaModule):
    name: str = "my_module"                    # Unique identifier
    description: str = "What this tool does"   # Shown to LLM for tool selection
    parameters: dict = { ... }                 # JSON Schema for tool inputs

    async def run(self, **kwargs) -> str:
        # Execute the tool, return result as string for LLM
```

Register new modules in `core/tool_router.py` by adding to `ENABLED_MODULES` list. The router auto-converts modules into LLM tool definitions.

## Critical Rules

- **Async everywhere**: All I/O operations (API calls, DB, file reads) MUST be async. The main loop is `asyncio.run()`.
- **No hardcoded secrets**: API keys live in `config.yaml` (gitignored) or env vars. Never inline them.
- **Module isolation**: Modules must not import from each other. They communicate only through the brain's tool-calling loop.
- **Graceful errors**: Module `run()` must catch exceptions and return human-readable error strings — never let exceptions crash the main loop.
- **Memory writes are explicit**: Only `core/memory.py` touches `data/memory.db`. Modules request memory operations through return values, not direct DB access.

## LLM Integration Pattern

Nova uses **tool-calling** (function calling) via the Ollama Python client (`ollama` package). The loop in `brain.py`:

1. User message + conversation history + system prompt → Ollama chat API
2. LLM responds with either text OR a tool call (Qwen 3 supports native tool calling in Ollama)
3. If tool call → `tool_router.py` dispatches to the module's `run()`
4. Tool result fed back to LLM as a tool role message
5. LLM generates final natural language response
6. Loop supports multi-step: LLM can chain multiple tool calls before responding

Provider abstraction in `brain.py`:
```python
class LLMProvider(ABC):
    async def chat(self, messages, tools=None, thinking=False) -> LLMResponse
    
class OllamaProvider(LLMProvider):  # Current default
class ClaudeProvider(LLMProvider):  # Future expansion
```

System prompt for Nova's personality lives in `core/prompts/system.md`. Edit personality there, not in `brain.py`.

## Voice Pipeline

WSL2 audio goes through PulseAudio/PipeWire. If audio devices aren't detected:
- Check `pactl list sinks` in WSL
- Fallback: run `voice/listener.py` on Windows side, pipe via localhost socket

STT and TTS run in separate async tasks so Nova can listen while speaking is still finishing.

## Testing

- Every new module needs a corresponding test in `tests/test_modules/`
- Mock all external API calls in tests — never hit real APIs
- Test the tool-calling loop with fake LLM responses in `test_brain.py`
- Use `pytest-asyncio` for async test functions

## Git Conventions

- Branch naming: `feature/module-name` or `fix/description`
- Commit messages: imperative mood, e.g. "Add Spotify module" not "Added Spotify module"
- Never commit `config.yaml`, `data/memory.db`, or any `.env` files

## When Compacting

Always preserve: the full module contract, the tool-calling loop description, the list of implemented modules, and any active bug context.

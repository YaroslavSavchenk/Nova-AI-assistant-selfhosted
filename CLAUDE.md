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
│   ├── memory.py            # SQLite-backed conversation history
│   ├── long_term_memory.py  # Persistent facts + session summaries (Phase 7)
│   ├── tool_router.py       # Registers modules, matches LLM tool calls to handlers
│   └── config_loader.py     # Loads and validates config.yaml
├── voice/
│   ├── listener.py          # STT (Speech-to-Text) via Faster-Whisper (local, CPU)
│   ├── speaker.py           # TTS (Text-to-Speech) via edge-tts (no API key)
│   └── wake_word.py         # Wake word detection via Whisper tiny model
├── modules/                 # Each file/package = one tool Nova can use
│   ├── base.py              # Abstract base class all modules implement
│   ├── web_search.py
│   ├── system_monitor.py
│   ├── todo_reminders.py
│   ├── memory/              # Long-term memory tools (Phase 7)
│   │   ├── __init__.py      # Re-exports RememberFactModule, RecallFactsModule, ForgetFactModule
│   │   ├── remember.py      # RememberFactModule
│   │   ├── recall.py        # RecallFactsModule
│   │   └── forget.py        # ForgetFactModule
│   ├── research/            # News, Wikipedia, URL summarization
│   │   ├── __init__.py      # Re-exports NewsModule, WikipediaModule, SummarizeUrlModule
│   │   ├── news.py          # NewsModule
│   │   ├── wikipedia.py     # WikipediaModule
│   │   └── summarize.py     # SummarizeUrlModule
│   ├── calendar/            # Google Calendar (service account auth)
│   │   ├── __init__.py      # Re-exports all calendar modules
│   │   ├── _client.py       # Shared build_service() helper
│   │   ├── list_events.py   # CalendarListEventsModule
│   │   ├── create_event.py  # CalendarCreateEventModule
│   │   └── delete_event.py  # CalendarDeleteEventModule
│   ├── spotify/             # Spotify package
│   │   ├── __init__.py      # Re-exports all public module classes
│   │   ├── _client.py       # Shared spotipy client + device helpers
│   │   ├── _helpers.py      # Shared formatting/parsing helpers
│   │   ├── play.py          # SpotifyPlayModule
│   │   ├── control.py       # SpotifyControlModule, SpotifySkipToModule
│   │   ├── now_playing.py   # SpotifyNowPlayingModule
│   │   ├── queue.py         # SpotifyQueueModule, SpotifyViewQueueModule
│   │   ├── playlists.py     # SpotifyMyPlaylistsModule
│   │   └── lyrics_search.py # SpotifyLyricsSearchModule (Genius API)
│   ├── cc_workflows/         # Claude Code workflow system (Phase 9)
│   │   ├── __init__.py       # Re-exports all workflow module classes
│   │   ├── _store.py         # Workflow JSON file persistence
│   │   ├── create.py         # CCWorkflowCreateModule
│   │   ├── add_step.py       # CCWorkflowAddStepModule
│   │   ├── list.py           # CCWorkflowListModule
│   │   ├── view.py           # CCWorkflowViewModule
│   │   ├── run.py            # CCWorkflowRunModule (real-time streaming)
│   │   ├── edit_step.py      # CCWorkflowEditStepModule
│   │   └── delete.py         # CCWorkflowDeleteModule
│   └── pc_control/          # PC control tools (Phase 8)
│       ├── __init__.py      # Re-exports all module classes
│       ├── _safety.py       # Allowlist validation, shell injection prevention, fuzzy project resolution
│       ├── run_command.py   # RunCommandModule
│       ├── claude_code.py   # ClaudeCodeModule
│       ├── open_app.py      # OpenAppModule (WSL2-aware, 30+ Windows app shortcuts)
│       ├── read_file.py     # ReadFileModule
│       ├── write_file.py    # WriteFileModule
│       ├── projects.py      # ListProjectsModule
│       ├── notes.py         # ProjectNotesReadModule, ProjectNotesWriteModule
│       └── ask_project.py   # AskProjectModule (combined notes + Claude Code)
├── scripts/
│   ├── spotify_auth.py      # One-time Spotify OAuth token setup
│   └── google_auth.py       # Google Calendar service account connection test
├── data/
│   ├── memory.db            # SQLite database (gitignored)
│   ├── notes/               # Project notes written by Nova (gitignored)
│   └── workflows/           # Workflow JSON files (gitignored)
└── tests/
    ├── test_brain.py
    ├── test_memory.py
    ├── test_long_term_memory.py
    └── test_modules/
        ├── test_pc_control.py            # 51 tests for PC control modules
        ├── test_pc_control_projects.py   # 19 tests for project/notes modules
        └── test_cc_workflows.py          # 39 tests for workflow modules
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

Register new modules in `main.py` by instantiating and passing them to `tool_router.register()`. The router auto-converts modules into LLM tool definitions.

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
class ClaudeProvider(LLMProvider):  # Planned — not yet implemented
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

## Session Management

- **Default session**: Each `python main.py` run gets a fresh UUID session (`run-<hex8>`). No history bleed between runs.
- **Named sessions**: Pass `--session work` to resume a persistent named session with full history.
- This prevents stale Spotify state (e.g. "Now playing: X") from a previous run contaminating the LLM's context.

## PC Control (Phase 8)

Nova can run shell commands, open Windows apps, read/write files, and delegate coding tasks to Claude Code. All operations are sandboxed:

- **Command allowlist**: Only commands listed in `modules.pc_control_allowed_commands` can run. Shell metacharacters (`|`, `;`, `&&`, `` ` ``, `$()`) are blocked to prevent injection.
- **Writable directory allowlist**: `WriteFileModule` only writes to paths under `modules.pc_control_writable_dirs`.
- **Project registry**: The `projects:` top-level key in `config.yaml` maps project names to paths. `ListProjectsModule`, `AskProjectModule`, and `ClaudeCodeModule` resolve projects by fuzzy name match via `_safety.py`.
- **Project notes**: Stored as Markdown files in `data/notes/` (one per project, gitignored). Nova reads/writes notes to remember project context across sessions.
- **Command timeout**: Configurable via `modules.pc_control_command_timeout` (default 30s).

## Claude Code Workflows (Phase 9)

Nova manages multi-step Claude Code checklists with real-time output streaming and session continuity.

- **Workflow storage**: JSON files in `data/workflows/` (one per workflow, gitignored)
- **Real-time output**: `CCWorkflowRunModule` reads Claude Code stdout line-by-line, printing to terminal live
- **Session continuity**: Uses `--continue` / `--resume` so each step builds on the previous Claude Code conversation
- **Step lifecycle**: `pending` → `running` → `done` / `failed`
- **Project integration**: Workflows are tied to registered projects from `config.yaml`

## When Compacting

Always preserve: the full module contract, the tool-calling loop description, the list of implemented modules, and any active bug context.

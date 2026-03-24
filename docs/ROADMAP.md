# Nova — Development Roadmap

> Living document. Updated as phases complete or priorities shift.

---

## Current status: Phase 9 next — Persona

---

## Phase 0 — Foundation `[COMPLETE]`

Core infrastructure everything else depends on. Must be solid before any modules are added.

**Goals:**
- Runnable Nova skeleton (text mode only)
- Tool-calling loop working end-to-end with a dummy module
- Persistent conversation memory across sessions

**Deliverables:**

| File | Description |
|------|-------------|
| `main.py` | Entry point, CLI arg parsing (`--voice`, `--debug`) |
| `core/brain.py` | `OllamaProvider`, tool-calling loop, multi-step chaining |
| `core/memory.py` | SQLite conversation history, context window management |
| `core/tool_router.py` | Module registration, LLM tool definition generation |
| `core/config_loader.py` | Load and validate `config.yaml` |
| `core/prompts/system.md` | Nova's personality — wit, trilingual behavior, assistant role |
| `modules/base.py` | `NovaModule` abstract base class |
| `config.example.yaml` | Template config with all options documented |
| `.env.example` | Template env file showing required secrets |
| `tests/test_brain.py` | Tool-calling loop tests with mocked LLM responses |
| `tests/test_memory.py` | SQLite memory persistence tests |

**Done when:** `python main.py` starts a conversation, the LLM can call a dummy echo tool, and the conversation persists across restarts.

---

## Phase 1 — MVP Modules `[COMPLETE]`

Three tools that make Nova immediately useful without any external accounts.

**Modules:**

| Module | File | External dep | API key needed |
|--------|------|-------------|----------------|
| Web search | `modules/web_search.py` | `duckduckgo-search` | No |
| System monitor | `modules/system_monitor.py` | `psutil`, `GPUtil` | No |
| Todo & reminders | `modules/todo_reminders.py` | SQLite (built-in) | No |

**Done when:** Nova can answer "search for X", "what's my CPU usage", and "remind me to Y" through natural conversation.

Tests: `tests/test_modules/test_web_search.py`, `tests/test_modules/test_system_monitor.py`, `tests/test_modules/test_todo.py`

---

## Phase 2 — Voice Pipeline `[COMPLETE]`

Add the voice interface. This is where Nova goes from chatbot to assistant.

**Components:**

| Component | Technology | Notes |
|-----------|-----------|-------|
| STT | Faster-Whisper `base` | CPU inference, EN/NL/RU auto-detect |
| TTS | edge-tts (Microsoft neural voices) | No API key, Python 3.12 compatible |
| Wake word | Whisper `tiny` model | Fully offline, "Hey Nova" / "Nova" |
| VAD | webrtcvad (aggressiveness=3) | Only real speech resets silence timer |
| Audio routing | PulseAudio via WSLg | `PULSE_SERVER=unix:/mnt/wslg/PulseServer` |

**Files:**
- `voice/listener.py` — Faster-Whisper STT, webrtcvad silence detection
- `voice/speaker.py` — edge-tts TTS, voice map per language
- `voice/wake_word.py` — Whisper-based wake word detection

**VRAM budget:** All voice models run on CPU — full 12 GB VRAM stays free for the LLM.

**Done when:** `python main.py --voice` lets you speak to Nova and hear a response, with wake word activation.

---

## Phase 3 — News & Research `[COMPLETE]`

Give Nova better research capabilities beyond a single web search.

**Module:** `modules/research/` package (`news.py`, `wikipedia.py`, `summarize.py`)

**Capabilities:**
- Multi-source web search with summarization
- News headlines by topic (via RSS or NewsAPI)
- Wikipedia lookups
- Read and summarize a URL

**Thinking toggle note:** Enable `/think` for research tasks — the LLM should reason about which sources to trust and how to synthesize results before responding.

**Tests:** `tests/test_modules/test_research.py`

**Done when:** Nova can fetch today's news by topic, look up a Wikipedia article, and summarize a URL — all through natural conversation.

---

## Phase 4 — Spotify `[COMPLETE]`

Music control through natural language.

**Module:** `modules/spotify/` (package)

**Integration:** Spotify Web API (OAuth 2.0 via spotipy)

**Capabilities:**
- Play track, artist, album, or playlist by name (album context for correct queue behavior)
- Play user's own playlists (fuzzy name matching) or public playlists
- Play Liked Songs collection
- Pause, resume, skip, previous (with repeat count)
- Skip directly to a named song in the queue (fuzzy + `&`/`and` normalization)
- Volume control (0–100)
- Shuffle toggle (on / off / toggle)
- Query current playback — track, artist, album, progress
- Add a track to the queue ("play X next")
- View the current queue (deduplicated, up to 5 tracks)
- List all user playlists (created + saved/followed), with Liked Songs count

**Tools registered:**
| Tool | Description |
|------|-------------|
| `spotify_play` | Search and play track / artist / album / playlist |
| `spotify_control` | Pause, resume, next, previous, volume, shuffle (with optional count) |
| `spotify_now_playing` | Get current track info and progress |
| `spotify_queue` | Add a track to the playback queue |
| `spotify_view_queue` | Show what's currently in the playback queue |
| `spotify_skip_to` | Skip forward to a specific song by name |
| `spotify_my_playlists` | List user's playlists |

**Config needed in `.env`:** `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`

**OAuth note:** Initial auth flow requires a browser — run `python3 scripts/spotify_auth.py` once to authorize and cache the token.

---

## Phase 5 — Spotify Lyrics Search `[COMPLETE]`

Find songs from lyric snippets and confirm before playing.

**Problem:** `spotify_play` searches by title/artist only — half-remembered song names, foreign lyrics, or vague descriptions all fail. This phase lets the user hum a line and have Nova identify and confirm the track.

**Module:** `modules/spotify/lyrics_search.py`

**Tool registered:**

| Tool | Description |
|------|-------------|
| `spotify_lyrics_search` | Identify a song from a lyric snippet via Genius API, return top candidates for confirmation |

**How the flow works:**
1. User says a lyric (e.g. *"play that song that goes 'is this the real life'"*)
2. Nova calls `spotify_lyrics_search` with the snippet
3. Module hits Genius search API, returns top 1–3 candidates (title + artist)
4. Nova asks: *"Found: Bohemian Rhapsody by Queen — shall I play it?"*
5. User confirms → LLM calls existing `spotify_play` tool
6. No changes to `brain.py` or `tool_router.py` — confirmation is pure conversational flow

**Tech stack:**
- **Genius API** — `GET https://api.genius.com/search?q=<lyric>` with Bearer auth
- `httpx` — already in `requirements.txt`, no new dependencies

**Config needed in `.env`:** `GENIUS_ACCESS_TOKEN`

**Tests:** `tests/test_modules/test_spotify_lyrics_search.py`

---

## Phase 6 — Google Calendar `[COMPLETE]`

Google Calendar integration via service account authentication.

**Module:** `modules/calendar/` package (`list_events.py`, `create_event.py`, `delete_event.py`)

**Tools registered:**

| Tool | Description |
|------|-------------|
| `calendar_list_events` | List upcoming events (configurable days ahead, max results) |
| `calendar_create_event` | Create event with title, start, end, optional description — confirms with user first |
| `calendar_delete_event` | Delete event by ID — confirms with user first |

**Capabilities:**
- Read upcoming events (today, this week, or by date range)
- Create calendar events with natural language date resolution
- Delete calendar events by ID
- Confirmation flow — Nova always asks before creating or deleting

**Auth:** Google service account (`data/service.account.json`) — no browser flow needed.
The service account must be shared with your calendar (Make changes to events permission).

**Config needed in `config.yaml`:**
```yaml
modules:
  calendar: true
  calendar_id: "your.email@gmail.com"
  calendar_timezone: "Europe/Amsterdam"
```

**Setup:** Run `python3 scripts/google_auth.py` to verify credentials are working.

**Note:** Email (Gmail) intentionally excluded — deferred to backlog.

---

## Phase 7 — Memory Upgrade `[COMPLETE]`

Upgrade Nova from a session-only memory to a persistent long-term memory system.
Nova now remembers facts about you across sessions and maintains summaries of past conversations.

**Components:**

| Feature | Description | Tech |
|---------|-------------|------|
| Manual facts | "Remember that I prefer dark mode" | `remember_fact` tool → SQLite |
| Fact extraction | Auto-extracted from sessions during summarization | LLM JSON prompt |
| Session summaries | Compressed recaps of past conversations | LLM summarization on session start |
| Semantic search | Find relevant past memories by meaning | ChromaDB + `nomic-embed-text` (optional) |

**Tools registered:**

| Tool | Description |
|------|-------------|
| `remember_fact` | Store a long-term fact about the user |
| `list_facts` | List all stored facts (optionally by category) |
| `forget_fact` | Delete a fact by ID |

**Architecture:**
- `core/long_term_memory.py` — `LongTermMemory` class (facts + summaries + optional ChromaDB)
- `modules/memory/` — package with 3 tools (remember, recall, forget)
- Facts injected into every system prompt
- Session summaries injected as past context (recent 3, or semantic search if ChromaDB enabled)
- Summarization runs at session start for all unprocessed previous sessions

**Embedding model:** `nomic-embed-text` via Ollama (optional — enables semantic search)

**Config:**
```yaml
memory:
  long_term_enabled: true
  semantic_search: false   # set true + ollama pull nomic-embed-text to enable
```

**Files:**
- `core/long_term_memory.py` — LongTermMemory class
- `modules/memory/` — remember, recall, forget tools
- `data/chroma/` — ChromaDB persistent store (gitignored, only used if semantic_search: true)

---

## Phase 8 — PC Control `[COMPLETE]`

Nova can interact with the local machine, open Windows apps from WSL2, run commands, read/write files, query Claude Code about projects, and maintain per-project notes.

**Module:** `modules/pc_control/` package

**Tools registered:**

| Tool | Description |
|------|-------------|
| `pc_run_command` | Run allowlisted shell commands (Linux + Windows via WSL2) |
| `pc_claude_code` | Send prompts to Claude Code CLI, target specific projects |
| `pc_open_app` | Open Windows/Linux apps, files, or URLs (30+ app shortcuts) |
| `pc_read_file` | Read local text files with size limits |
| `pc_write_file` | Write/append to files in configured writable directories |
| `pc_list_projects` | List registered development projects |
| `pc_write_notes` | Save per-project development notes/checklists |
| `pc_ask_project` | Ask any question about a project (checks notes + Claude Code) |

**Safety:**
- Command allowlist in `config.yaml` — only approved commands can run
- Shell injection blocking: `;`, `|`, `&&`, `||`, `$()`, backticks, redirects
- `asyncio.create_subprocess_exec` only — never `shell=True`
- File writes restricted to configured writable directories
- Expensive tool calls force the LLM to respond (prevents infinite tool chaining)

**WSL2 integration:**
- `cmd.exe /c start` fallback for opening Windows apps
- Windows commands in allowlist: `powershell.exe`, `cmd.exe`, `ipconfig.exe`, etc.
- `/mnt/c/Windows` as safe CWD for cmd.exe (avoids UNC path errors)

**Project system:**
- Projects defined in `config.yaml` with name, path, description
- Fuzzy name matching (exact → case-insensitive → substring)
- Per-project markdown notes in `data/notes/`
- `pc_ask_project` combines notes + Claude Code in one tool call

**Config:**
```yaml
modules:
  pc_control: true
  pc_control_allowed_commands: [ls, cat, ps, code, claude, powershell.exe, ...]
  pc_control_writable_dirs: [~/Documents, ~/notes]
  pc_control_command_timeout: 30

projects:
  nova:
    path: ~/projects/Nova-AI-assistant-selfhosted
    description: "Personal AI assistant"
```

**Tests:** 70 tests in `test_pc_control.py` + `test_pc_control_projects.py`

---

## Phase 9 — Persona `[PLANNED]`

Give Nova a fully customizable personality layer — name, voice, tone, language defaults, and behavioral traits.

**Capabilities:**
- Custom name (not hardcoded "Nova") configurable in `config.yaml`
- Personality tone presets: professional, casual, witty, concise
- Language preference — default response language, or auto-detect from user input
- Wake word tied to persona name
- Per-context tone switching (e.g. casual for chat, professional for email drafts)

**Files:**
- `core/prompts/system.md` — already exists, will be templated from config
- `core/persona.py` — new, loads persona config and injects into system prompt at startup

**Config:** `persona.name`, `persona.tone`, `persona.language` in `config.yaml`

**Done when:** You can change Nova's name and tone in config and it behaves consistently across all interactions.

---

## Backlog / Ideas

These are not scheduled but worth keeping track of:

- **Provider Abstraction** — Swap the LLM brain from Ollama to Claude or OpenAI. `providers/` package with `LLMProvider` ABC, `OllamaProvider`, `ClaudeProvider`, `OpenAIProvider`. Config: `brain.provider: ollama | claude | openai`. Use cases: cloud fallback, routing complex tasks to larger models, A/B testing response quality.
- **Email (Gmail)** — Read recent emails, send with mandatory confirmation preview. Excluded from Phase 6 (Calendar) by design — highest privacy risk, revisit later.
- **Smart Home** — Home Assistant REST API integration (lights, switches, scenes, sensors). Config: `HA_URL`, `HA_TOKEN`. Module: `modules/smart_home.py`. Skipped Phase 3 — no HA setup yet.
- **File assistant** — read, summarize, and answer questions about local files (PDFs, text, code)
- **Proactive notifications** — Nova initiates contact on scheduled triggers (morning briefing, reminders)
- **REST API / Backend server** — expose Nova core as a FastAPI server so external clients can connect. Required foundation for the phone app and hardware device goals below.
- **Phone app** — mobile client (iOS/Android) that connects to the Nova backend over the network. User talks to Nova and gets responses through the app.
- **Standalone home device** — always-on hardware box (like an Echo) running Nova locally, connected to the same backend.
- **Web UI** — simple browser interface as an alternative to terminal (FastAPI + HTMX or similar)
- **Multi-modal input** — accept images (describe what's in a photo, read text from a screenshot)
- **Custom wake phrase training** — train a personalized "Hey Nova" model on your own voice
- **Windows-native audio** — bridge WSL2 Nova to Windows audio stack via localhost socket for lower latency

---

## Non-goals (explicit out of scope)

- Cloud hosting / multi-user support — Nova is a personal, local-first assistant
- General-purpose agent framework — this is not LangChain; the architecture stays simple and Nova-specific

---

## Architecture decisions log

| Decision | Rationale |
|----------|-----------|
| Ollama over llama.cpp directly | Easier model management, native tool-calling support in Qwen 3, hot-swap |
| SQLite over Postgres | Local-first, zero-dependency, sufficient for single-user assistant |
| Module isolation (no cross-imports) | Prevents dependency tangles, makes each module independently testable |
| `config.yaml` + `.env` split | Non-secret settings (model choice, toggles) in YAML; secrets always in env |
| Async everywhere | LLM calls, audio, and API calls all benefit from non-blocking I/O |
| Qwen 3 14B Q5_K_M | Best quality/VRAM tradeoff for RTX 5070; Q5_K_M is near-lossless for 14B |

---

- **API Server Layer** — Expose Nova core as a FastAPI + WebSocket backend so external clients (phone, desktop, browser) can connect. Endpoints: `POST /chat`, `POST /voice`, `WS /stream`, `GET /status`, `GET /history/{session_id}`, `GET /modules`. Token-based auth even on local network. Terminal REPL stays unchanged — API runs alongside it via `python main.py --server`. This is the critical foundation for every frontend below.
- **Phone App** — Mobile client (React Native, Flutter, or PWA) that connects to the Nova API server over local WiFi or Tailscale for remote access. Chat interface with voice button, now-playing widget, quick actions for todos/calendar/music. Push notifications for reminders and proactive alerts.
- **Desktop App** — Native desktop frontend (Electron or Tauri). System tray icon, global hotkey (e.g. Alt+Space) to summon Nova as a floating overlay from anywhere. Persistent chat window optional. Connects to the same API server as the phone app.
- **Browser UI** — Lightweight web interface (FastAPI + HTMX or simple React) served directly by the API server on localhost. Zero-install alternative to the desktop app for quick access.
- **Smart LLM Routing** — Extend provider abstraction with routing logic in `brain.py`. Simple requests stay on local Qwen, complex multi-step tool chains route to Claude API. Cost tracking per request. Fully optional — Nova must always work 100% offline with just Qwen.

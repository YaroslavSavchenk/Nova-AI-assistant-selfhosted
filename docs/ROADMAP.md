# Nova — Development Roadmap

> Living document. Updated as phases complete or priorities shift.

---

## Current status: Phase 6 complete — starting Phase 7 (Memory Upgrade)

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

## Phase 7 — Memory Upgrade `[PLANNED]`

Upgrade the SQLite conversation log to a full semantic memory system.

**Components:**

| Feature | Description | Tech |
|---------|-------------|------|
| Session summaries | Compress old conversations into compact recaps | LLM summarization |
| Fact extraction | Auto-detect user preferences, names, facts | LLM extraction prompt |
| Manual facts | "Remember that I prefer dark mode" | Explicit user command |
| Semantic search | Find relevant past memories by meaning | ChromaDB + embeddings |

**Embedding model:** `nomic-embed-text` via Ollama (runs locally, no API key)

**Files:**
- `core/memory.py` — extend existing SQLite layer
- `data/chroma/` — ChromaDB persistent store (gitignored)

---

## Phase 8 — Provider Abstraction `[PLANNED]`

Enable swapping the LLM brain from Ollama to Claude or OpenAI.

**Files:**
- `providers/base.py` — `LLMProvider` ABC (already specced in CLAUDE.md)
- `providers/ollama_provider.py` — current default
- `providers/claude_provider.py` — Anthropic API
- `providers/openai_provider.py` — OpenAI API

**Use cases:**
- Fall back to Claude API when the local model is unavailable
- Route complex reasoning tasks to a larger cloud model
- A/B test response quality between providers

**Config:** `config.yaml` `brain.provider: ollama | claude | openai` — hot-swappable without restart ideally.

---

## Phase 9 — PC Control `[PLANNED]`

Let Nova interact with the local machine — run commands, control apps, and act as an agent that can operate your dev environment.

**Module:** `modules/pc_control.py`

**Capabilities:**
- Run shell commands from an explicit allowlist (safe, no arbitrary execution)
- Send prompts to Claude Code via CLI (`claude -p "..."`) and return the response
- Open applications or files
- Read/write local files on request
- Query running processes

**Safety rules:**
- Commands must be on a pre-approved allowlist in `config.yaml`
- Destructive commands (rm, kill, etc.) require explicit confirmation before running
- Never execute arbitrary strings from the LLM without allowlist validation

**Config:** `pc_control.allowed_commands` list in `config.yaml`

**Done when:** "Ask Claude Code to explain this function" and "open VS Code" work through Nova.

---

## Phase 10 — Persona `[PLANNED]`

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

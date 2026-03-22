# Nova — Development Roadmap

> Living document. Updated as phases complete or priorities shift.

---

## Current status: Phase 2 complete — smart home next

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

Tests: `tests/test_modules/test_web_search.py`, `test_system_monitor.py`, `test_todo_reminders.py`

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

## Phase 3 — Smart Home `[NEXT]`

Control Home Assistant devices through Nova.

**Module:** `modules/smart_home.py`

**Integration:** Home Assistant REST API (long-lived access token, local network)

**Capabilities:**
- Turn lights/switches on/off
- Query device states ("is the front door locked?")
- Run scenes and automations
- Get sensor readings (temperature, motion, etc.)

**Config needed in `.env`:** `HA_URL`, `HA_TOKEN`

**Done when:** "Turn off the living room lights" works.

---

## Phase 4 — News & Research `[PLANNED]`

Give Nova better research capabilities beyond a single web search.

**Module:** `modules/research.py`

**Capabilities:**
- Multi-source web search with summarization
- News headlines by topic (via RSS or NewsAPI)
- Wikipedia lookups
- Read and summarize a URL

**Thinking toggle note:** Enable `/think` for research tasks — the LLM should reason about which sources to trust and how to synthesize results before responding.

---

## Phase 5 — Spotify `[PLANNED]`

Music control through natural language.

**Module:** `modules/spotify.py`

**Integration:** Spotify Web API (OAuth 2.0)

**Capabilities:**
- Play artist, album, track, or playlist
- Pause, skip, previous
- Query current playback ("what's playing?")
- Add to queue

**Config needed in `.env`:** `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`

**OAuth note:** Initial auth flow requires a browser — run `python -m modules.spotify --auth` once to get a refresh token, then store it.

---

## Phase 6 — Calendar & Email `[PLANNED]`

Google Workspace integration. Highest privacy sensitivity — requires OAuth consent.

**Modules:** `modules/calendar_tool.py`, `modules/email_tool.py`

**Capabilities:**
- Read upcoming events
- Create and delete calendar events
- Read recent emails (unread, filtered by sender/subject)
- Send emails (with confirmation before sending)

**Config needed:** Google OAuth credentials (`credentials.json`, stored securely outside the repo)

**Safety rule:** Email sending must always show a preview and ask "send this?" before dispatching. Never auto-send.

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

## Backlog / Ideas

These are not scheduled but worth keeping track of:

- **File assistant** — read, summarize, and answer questions about local files (PDFs, text, code)
- **Shell executor** — run pre-approved shell commands (with an allowlist, never arbitrary code)
- **Proactive notifications** — Nova initiates contact on scheduled triggers (morning briefing, reminders)
- **Web UI** — simple browser interface as an alternative to terminal (FastAPI + HTMX or similar)
- **Multi-modal input** — accept images (describe what's in a photo, read text from a screenshot)
- **Custom wake phrase training** — train a personalized "Hey Nova" model on your own voice
- **Windows-native audio** — bridge WSL2 Nova to Windows audio stack via localhost socket for lower latency

---

## Non-goals (explicit out of scope)

- Cloud hosting / multi-user support — Nova is a personal, local-first assistant
- Mobile app — terminal and voice are the only interfaces for now
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

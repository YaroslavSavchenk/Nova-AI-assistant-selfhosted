"""
main.py — Nova AI Assistant entry point.

Usage:
    python main.py                      # text mode, default session
    python main.py --voice              # voice input/output
    python main.py --debug              # verbose logging
    python main.py --session work       # named session
"""

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

# WSL2: PulseAudio is served by WSLg — point sounddevice/portaudio at it
_WSL_PULSE_SERVER = "/mnt/wslg/PulseServer"
if Path(_WSL_PULSE_SERVER).exists() and "PULSE_SERVER" not in os.environ:
    os.environ["PULSE_SERVER"] = f"unix:{_WSL_PULSE_SERVER}"

# Suppress known noisy warnings
import warnings
warnings.filterwarnings("ignore", message=".*CUDAExecutionProvider.*")
warnings.filterwarnings("ignore", message=".*unauthenticated requests.*")
warnings.filterwarnings("ignore", message=".*HF_TOKEN.*")

from core.config_loader import load_config
from core.memory import Memory
from core.tool_router import ToolRouter
from core.brain import Brain
from modules.base import NovaModule
from modules.web_search import WebSearchModule
from modules.system_monitor import SystemMonitorModule
from modules.todo_reminders import TodoModule


# ---------------------------------------------------------------------------
# Built-in echo module for testing tool calling
# ---------------------------------------------------------------------------


class EchoModule(NovaModule):
    """
    Simple echo tool for verifying the tool-calling pipeline works end-to-end.
    Not useful in production — disable once real modules are registered.
    """

    name: str = "echo"
    description: str = (
        "Echoes back whatever text you give it. Use this to test tool calling."
    )
    parameters: dict = {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "Text to echo",
            }
        },
        "required": ["text"],
    }

    async def run(self, **kwargs) -> str:
        try:
            text = kwargs.get("text", "")
            return f"Echo: {text}"
        except Exception as exc:
            return f"Echo tool error: {exc}"


# ---------------------------------------------------------------------------
# Text REPL
# ---------------------------------------------------------------------------


async def repl(brain: Brain, session_id: str) -> None:
    """Run the interactive read-eval-print loop."""
    print("Nova is ready. Type your message, or Ctrl-C to exit.\n")
    while True:
        try:
            user_input = input("> ").strip()
            # Sanitize surrogate characters that WSL2 terminals can inject
            user_input = user_input.encode("utf-8", "surrogatepass").decode("utf-8", "replace")
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue

        try:
            print("Nova is thinking...", end="\r", flush=True)
            response = await brain.chat(user_input, session_id=session_id)
            print(" " * 20, end="\r")  # clear the thinking line
            print(f"\n{response}\n")
        except Exception as exc:
            logging.getLogger(__name__).exception("Unexpected error in brain.chat")
            print(f"[Error] Something went wrong: {exc}\n")


# ---------------------------------------------------------------------------
# Voice REPL
# ---------------------------------------------------------------------------


async def voice_repl(
    brain: Brain,
    session_id: str,
    listener,
    speaker,
    wake_detector,
    voice_cfg: dict,
) -> None:
    """
    Voice interaction loop.

    If wake word detection is enabled: waits for the wake word, then records
    and responds. If wake word is disabled or unavailable: press Enter to
    trigger a recording (push-to-talk).
    """
    logger = logging.getLogger(__name__)
    stop_event = asyncio.Event()
    wake_cfg = voice_cfg.get("wake_word", {})
    wake_enabled = wake_cfg.get("enabled", True)

    silence_seconds: float = voice_cfg.get("stt", {}).get("silence_seconds", 5.0)

    async def handle_interaction() -> None:
        """Record speech until silence, get response, speak it."""
        print("Listening...          ", end="\r", flush=True)
        user_text = await listener.listen_until_silence(silence_seconds=silence_seconds)
        print(" " * 30, end="\r")

        if not user_text.strip():
            logger.debug("Empty transcription — ignoring.")
            return

        print(f"\nYou: {user_text}")
        print("Nova is thinking...", end="\r", flush=True)

        response = await brain.chat(user_text, session_id=session_id)
        print(" " * 20, end="\r")
        print(f"Nova: {response}\n")

        # Detect language for TTS (mirror user language)
        tts_lang = voice_cfg.get("tts", {}).get("language", "en")
        await speaker.speak(response, language=tts_lang)

    print("Nova voice mode active. Loading wake word model...", flush=True)
    print("(First run downloads ~39 MB — cached after that)\n")

    try:
        if wake_enabled:
            await wake_detector.listen_for_wake_word(
                callback=handle_interaction,
                stop_event=stop_event,
            )
        else:
            # Push-to-talk fallback: press Enter to record
            print("(Wake word disabled — press Enter to speak)\n")
            while True:
                try:
                    input("")
                except (EOFError, KeyboardInterrupt):
                    break
                await handle_interaction()
    except KeyboardInterrupt:
        pass
    finally:
        stop_event.set()
        print("\nGoodbye.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Nova — personal AI assistant",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--voice",
        action="store_true",
        default=False,
        help="Enable voice input/output (requires voice dependencies)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="Set logging level to DEBUG",
    )
    parser.add_argument(
        "--session",
        type=str,
        default="default",
        help="Conversation session identifier",
    )
    return parser.parse_args()


def setup_logging(debug: bool, log_file: str | None) -> None:
    level = logging.DEBUG if debug else logging.INFO
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
    )
    # Suppress noisy HTTP request logs from httpx/ollama/ddgs unless in debug mode
    if not debug:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("primp").setLevel(logging.WARNING)
        logging.getLogger("faster_whisper").setLevel(logging.ERROR)
        logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
        logging.getLogger("voice.wake_word").setLevel(logging.WARNING)


async def main() -> None:
    args = parse_args()

    # Load config
    config = load_config("config.yaml")

    # Logging setup (uses config level unless --debug overrides)
    log_cfg = config.get("logging", {})
    setup_logging(
        debug=args.debug or log_cfg.get("level", "INFO").upper() == "DEBUG",
        log_file=log_cfg.get("file"),
    )

    logger = logging.getLogger(__name__)
    logger.debug("Config loaded. Session: %s", args.session)

    # Load system prompt
    prompt_path = Path(__file__).parent / "core" / "prompts" / "system.md"
    system_prompt = prompt_path.read_text(encoding="utf-8")

    # Initialise components
    memory = Memory(db_path=config["memory"]["db_path"])
    await memory.init()

    tool_router = ToolRouter()
    tool_router.register(EchoModule())

    modules_cfg = config.get("modules", {})

    if modules_cfg.get("web_search", False):
        tool_router.register(WebSearchModule())
        logger.debug("Registered module: web_search")

    if modules_cfg.get("system_monitor", False):
        tool_router.register(SystemMonitorModule())
        logger.debug("Registered module: system_monitor")

    if modules_cfg.get("todo_reminders", False):
        db_path = config["memory"]["db_path"]
        todo_module = TodoModule(db_path=db_path)
        await todo_module.init()
        tool_router.register(todo_module)
        logger.debug("Registered module: todo")

    brain = Brain(
        config=config,
        memory=memory,
        tool_router=tool_router,
        system_prompt=system_prompt,
    )

    if args.voice:
        voice_cfg = config.get("voice", {})
        stt_cfg = voice_cfg.get("stt", {})
        tts_cfg = voice_cfg.get("tts", {})
        wake_cfg = voice_cfg.get("wake_word", {})

        from voice.listener import Listener
        from voice.speaker import Speaker
        from voice.wake_word import WakeWordDetector

        listener = Listener(
            model_size=stt_cfg.get("model_size", "base"),
            language=stt_cfg.get("language") or None,
            device=stt_cfg.get("device", "cpu"),
        )
        speaker = Speaker(
            language=tts_cfg.get("language", "en"),
        )
        wake_detector = WakeWordDetector(
            model_name=wake_cfg.get("model", "hey_nova"),
            threshold=wake_cfg.get("threshold", 0.5),
            access_key=wake_cfg.get("access_key", ""),
            model_path=wake_cfg.get("model_path", ""),
        )

        await voice_repl(
            brain=brain,
            session_id=args.session,
            listener=listener,
            speaker=speaker,
            wake_detector=wake_detector,
            voice_cfg=voice_cfg,
        )
    else:
        await repl(brain, session_id=args.session)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass

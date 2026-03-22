"""
voice/wake_word.py — Wake word detection using Faster-Whisper.

Listens to short overlapping audio chunks and transcribes them with the
Whisper "tiny" model. If the transcript contains the wake phrase, the
callback fires. Fully offline — no accounts, no API keys, no external pings.
"""

import asyncio
import logging
import re
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wake_word")

_SAMPLE_RATE = 16000
_CHUNK_SECONDS = 2.0          # Record 2-second windows
_CHUNK_SIZE = int(_SAMPLE_RATE * _CHUNK_SECONDS)


class WakeWordDetector:
    """
    Continuously records short audio windows and uses Faster-Whisper (tiny)
    to detect the wake phrase "hey nova" or just "nova".

    Fully local — uses the same Whisper runtime already installed for STT.
    """

    def __init__(
        self,
        model_name: str = "hey_nova",
        threshold: float = 0.5,
        access_key: str = "",       # unused, kept for config compatibility
        model_path: str = "",       # unused, kept for config compatibility
        wake_phrases: list[str] | None = None,
    ):
        """
        Args:
            model_name:   Ignored — kept for config compatibility.
            wake_phrases: List of phrases that trigger detection.
                          Defaults to ["hey nova", "nova"].
        """
        self.wake_phrases = wake_phrases or ["hey nova", "hey, nova", "nova"]
        self._whisper = None  # lazy-loaded

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_whisper(self) -> bool:
        """Lazy-load Faster-Whisper tiny model."""
        if self._whisper is not None:
            return True
        try:
            from faster_whisper import WhisperModel  # noqa: PLC0415
            self._whisper = WhisperModel("tiny", device="cpu", compute_type="int8")
            print("Say 'Hey Nova' to activate.")
            return True
        except Exception as exc:
            log.warning("Failed to load Whisper for wake word detection: %s", exc)
            return False

    def _contains_wake_phrase(self, text: str) -> bool:
        """Check if transcription contains any wake phrase."""
        text = text.lower().strip()
        return any(phrase in text for phrase in self.wake_phrases)

    def _record_and_check(self) -> bool:
        """
        Record one audio chunk, transcribe it, return True if wake phrase detected.
        Blocking — runs in executor thread.
        """
        import numpy as np  # noqa: PLC0415
        import sounddevice as sd  # noqa: PLC0415
        import tempfile, os  # noqa: PLC0415, E401
        import soundfile as sf  # noqa: PLC0415

        audio = sd.rec(_CHUNK_SIZE, samplerate=_SAMPLE_RATE, channels=1, dtype="float32")
        sd.wait()
        audio = np.squeeze(audio)

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            sf.write(tmp_path, audio, _SAMPLE_RATE)

            segments, _ = self._whisper.transcribe(
                tmp_path,
                language=None,   # auto-detect — handles EN/NL/RU
                beam_size=1,     # fastest setting for wake word use
                vad_filter=True, # skip silent chunks quickly
            )
            text = " ".join(seg.text.strip() for seg in segments)
            if text:
                log.debug("Wake word check: '%s'", text)
            return self._contains_wake_phrase(text)
        except Exception as exc:
            log.debug("Wake word transcription error: %s", exc)
            return False
        finally:
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def listen_for_wake_word(
        self,
        callback: callable,
        stop_event: asyncio.Event,
    ) -> None:
        """
        Loop: record → transcribe → if wake phrase detected → call callback.
        Repeats until stop_event is set.
        """
        loop = asyncio.get_event_loop()

        if not self._load_whisper():
            log.warning("Wake word detection disabled — falling back to push-to-talk.")
            await stop_event.wait()
            return

        while not stop_event.is_set():
            try:
                detected = await loop.run_in_executor(_executor, self._record_and_check)
            except Exception as exc:
                log.warning("Wake word loop error: %s", exc)
                continue

            if detected:
                log.info("Wake word detected — activating Nova.")
                try:
                    await callback()
                except Exception as exc:
                    log.warning("Wake word callback error: %s", exc)

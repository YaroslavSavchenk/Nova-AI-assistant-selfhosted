"""
voice/listener.py — Speech-to-text using Faster-Whisper.
Runs on CPU to preserve GPU VRAM for the LLM.
"""

import asyncio
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

# ThreadPoolExecutor for running blocking calls
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="listener")


class Listener:
    """
    Transcribes audio using Faster-Whisper.

    Lazy-loads the WhisperModel on first use to avoid startup overhead.
    All blocking operations are offloaded to a thread executor so the
    asyncio event loop is never blocked.
    """

    def __init__(
        self,
        model_size: str = "base",
        language: str | None = None,
        device: str = "cpu",
    ):
        """
        Args:
            model_size: Whisper model variant — "base", "small", "medium",
                        "large-v3", "distil-large-v3".
            language:   BCP-47 language code for forced decoding (e.g. "en",
                        "nl", "ru"), or None for auto-detection.
            device:     "cpu" or "cuda".  Default is "cpu" to keep VRAM free
                        for the LLM.
        """
        self.model_size = model_size
        self.language = language
        self.device = device
        self._model = None  # Loaded lazily on first use

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Lazy-load the WhisperModel (blocking — call from executor)."""
        if self._model is not None:
            return
        try:
            from faster_whisper import WhisperModel  # noqa: PLC0415

            log.info(
                "Loading Faster-Whisper model '%s' on %s …",
                self.model_size,
                self.device,
            )
            self._model = WhisperModel(
                self.model_size,
                device=self.device,
                compute_type="int8",
            )
            log.info("Faster-Whisper model loaded.")
        except Exception as exc:
            log.warning("Failed to load Faster-Whisper model: %s", exc)
            self._model = None

    def _transcribe_sync(self, audio_path: str) -> str:
        """Blocking transcription — run inside executor."""
        self._load_model()
        if self._model is None:
            return ""
        try:
            segments, _info = self._model.transcribe(
                audio_path,
                language=self.language,
                beam_size=5,
            )
            return " ".join(seg.text.strip() for seg in segments)
        except Exception as exc:
            log.warning("Transcription error for '%s': %s", audio_path, exc)
            return ""

    def _record_sync(self, duration: float, sample_rate: int) -> "numpy.ndarray":  # noqa: F821
        """Blocking microphone recording — run inside executor."""
        import numpy as np  # noqa: PLC0415
        import sounddevice as sd  # noqa: PLC0415

        frames = int(duration * sample_rate)
        log.debug("Recording %.1f s at %d Hz …", duration, sample_rate)
        audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
        sd.wait()
        return np.squeeze(audio)

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def transcribe_file(self, audio_path: str) -> str:
        """
        Transcribe an existing audio file and return the recognised text.

        Args:
            audio_path: Absolute or relative path to a WAV/MP3/FLAC file.

        Returns:
            Transcribed text, or an empty string on failure.
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._transcribe_sync, audio_path)

    async def listen_once(
        self,
        duration: float = 5.0,
        sample_rate: int = 16000,
    ) -> str:
        """
        Record audio from the default microphone for *duration* seconds,
        transcribe it, and return the text.

        Args:
            duration:    Recording length in seconds.
            sample_rate: Sampling rate in Hz (16 000 is optimal for Whisper).

        Returns:
            Transcribed text, or an empty string on failure.
        """
        loop = asyncio.get_event_loop()
        try:
            audio_data = await loop.run_in_executor(
                _executor,
                self._record_sync,
                duration,
                sample_rate,
            )
        except Exception as exc:
            log.warning("Microphone recording failed: %s", exc)
            return ""

        # Write to a temporary WAV file, transcribe, then clean up
        try:
            import soundfile as sf  # noqa: PLC0415

            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name

            def _write_and_transcribe() -> str:
                sf.write(tmp_path, audio_data, sample_rate)
                return self._transcribe_sync(tmp_path)

            result = await loop.run_in_executor(_executor, _write_and_transcribe)
        except Exception as exc:
            log.warning("Failed to save or transcribe audio: %s", exc)
            result = ""
        finally:
            # Best-effort cleanup — ignore errors if file was never created
            import os  # noqa: PLC0415

            try:
                os.unlink(tmp_path)
            except Exception:
                pass

        return result

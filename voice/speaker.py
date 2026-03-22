"""
voice/speaker.py — Text-to-speech using Coqui XTTS v2.
Runs on CPU to preserve GPU VRAM for the LLM.
"""

import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

import sounddevice as sd
import soundfile as sf

logger = logging.getLogger(__name__)

# Module-level thread pool for blocking TTS and audio operations
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="speaker")


class Speaker:
    def __init__(
        self,
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        speaker_wav: str | None = None,
        language: str = "en",
        device: str = "cpu",
    ):
        """
        Initialize the Speaker.

        Args:
            model_name: Coqui TTS model identifier.
            speaker_wav: Optional path to a reference audio file for voice cloning.
                         If None, the first available built-in speaker is used.
            language: Default output language code ("en", "nl", "ru", …).
            device: Torch device for TTS inference — "cpu" or "cuda".
                    Defaults to "cpu" to preserve GPU VRAM for the LLM.
        """
        self.model_name = model_name
        self._speaker_wav = speaker_wav
        self.language = language
        self.device = device
        self._model = None  # lazy-loaded on first use

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> None:
        """Lazy-load the TTS model (blocking — call from executor)."""
        if self._model is not None:
            return
        from TTS.api import TTS  # type: ignore[import]

        logger.info("Loading TTS model %s on %s …", self.model_name, self.device)
        self._model = TTS(self.model_name).to(self.device)
        logger.info("TTS model loaded.")

    def _synthesize(self, text: str, output_path: str, language: str) -> None:
        """
        Run TTS synthesis (blocking — call from executor).

        Chooses between voice-cloning mode (speaker_wav provided) and
        built-in-speaker mode (first available speaker as fallback).
        """
        self._load_model()

        if self._speaker_wav is not None:
            self._model.tts_to_file(
                text=text,
                speaker_wav=self._speaker_wav,
                language=language,
                file_path=output_path,
            )
        else:
            speaker = self._model.speakers[0] if self._model.speakers else None
            self._model.tts_to_file(
                text=text,
                speaker=speaker,
                language=language,
                file_path=output_path,
            )

    def _play_wav(self, wav_path: str) -> None:
        """Play a WAV file through the default audio output (blocking)."""
        data, samplerate = sf.read(wav_path)
        sd.play(data, samplerate)
        sd.wait()

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def speak(self, text: str, language: str | None = None) -> None:
        """
        Convert *text* to speech and play it through the speakers.

        Args:
            text: Text to synthesise.
            language: Optional language override (e.g. "nl", "ru").
                      Falls back to the instance default when None.
        """
        lang = language if language is not None else self.language
        loop = asyncio.get_event_loop()

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="nova_tts_")
        os.close(tmp_fd)

        try:
            await loop.run_in_executor(_executor, self._synthesize, text, tmp_path, lang)
            await loop.run_in_executor(_executor, self._play_wav, tmp_path)
        except Exception as exc:
            logger.error("Speaker.speak() failed: %s", exc)
        finally:
            try:
                os.remove(tmp_path)
            except OSError:
                pass

    async def speak_to_file(
        self, text: str, output_path: str, language: str | None = None
    ) -> None:
        """
        Convert *text* to speech and save the result to *output_path*.

        Useful for testing and offline pre-rendering.

        Args:
            text: Text to synthesise.
            output_path: Destination file path (WAV format).
            language: Optional language override.
        """
        lang = language if language is not None else self.language
        loop = asyncio.get_event_loop()

        try:
            await loop.run_in_executor(
                _executor, self._synthesize, text, output_path, lang
            )
        except Exception as exc:
            logger.error("Speaker.speak_to_file() failed: %s", exc)

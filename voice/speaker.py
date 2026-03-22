"""
voice/speaker.py — Text-to-speech using Microsoft Edge TTS.

Uses edge-tts (free, no API key, high quality neural voices).
Supports English, Dutch, and Russian to match Nova's trilingual personality.
Audio playback via sounddevice.
"""

import asyncio
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor

import edge_tts
import sounddevice as sd
import soundfile as sf

logger = logging.getLogger(__name__)

# Thread pool for blocking audio playback
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="speaker")

# Voice map per language code
_VOICES: dict[str, str] = {
    "en": "en-US-AriaNeural",
    "nl": "nl-NL-ColetteNeural",
    "ru": "ru-RU-SvetlanaNeural",
}
_DEFAULT_VOICE = "en-US-AriaNeural"


class Speaker:
    def __init__(
        self,
        language: str = "en",
        **kwargs,  # absorb unused config keys (model, device, speaker_wav)
    ):
        """
        Args:
            language: Default output language code ("en", "nl", "ru").
        """
        self.language = language

    def _voice_for(self, language: str) -> str:
        return _VOICES.get(language, _DEFAULT_VOICE)

    def _play_wav(self, wav_path: str) -> None:
        """Play a WAV file through the default audio output (blocking)."""
        data, samplerate = sf.read(wav_path)
        sd.play(data, samplerate)
        sd.wait()

    async def speak(self, text: str, language: str | None = None) -> None:
        """
        Convert text to speech and play it through the speakers.

        Args:
            text: Text to synthesise.
            language: Optional language override ("en", "nl", "ru").
        """
        lang = language if language is not None else self.language
        voice = self._voice_for(lang)

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".mp3", prefix="nova_tts_")
        os.close(tmp_fd)

        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(tmp_path)
            loop = asyncio.get_event_loop()
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
        Convert text to speech and save to output_path (MP3).
        Useful for testing and offline pre-rendering.
        """
        lang = language if language is not None else self.language
        voice = self._voice_for(lang)

        try:
            communicate = edge_tts.Communicate(text, voice)
            await communicate.save(output_path)
        except Exception as exc:
            logger.error("Speaker.speak_to_file() failed: %s", exc)

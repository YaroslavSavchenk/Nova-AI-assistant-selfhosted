"""
tests/test_voice/test_speaker.py — Unit tests for voice/speaker.py.

All external dependencies (TTS model, sounddevice, soundfile) are fully
mocked so no real audio hardware or model download is required.
"""

import asyncio
import os
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest

# ---------------------------------------------------------------------------
# Stub the heavy optional imports before the speaker module is imported so
# that tests can run in CI without installing TTS / sounddevice / soundfile.
# ---------------------------------------------------------------------------

def _make_stub_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


if "sounddevice" not in sys.modules:
    sd_stub = _make_stub_module("sounddevice")
    sd_stub.play = MagicMock()
    sd_stub.wait = MagicMock()

if "soundfile" not in sys.modules:
    sf_stub = _make_stub_module("soundfile")
    sf_stub.read = MagicMock(return_value=(b"audio", 22050))

if "TTS" not in sys.modules:
    tts_pkg = _make_stub_module("TTS")
    tts_api = _make_stub_module("TTS.api")
    tts_api.TTS = MagicMock()

from voice.speaker import Speaker  # noqa: E402  (must come after stubs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_model(speakers=("default_speaker",)):
    """Return a MagicMock that looks like a loaded TTS model."""
    model = MagicMock()
    model.speakers = list(speakers)
    model.tts_to_file = MagicMock()
    return model


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSpeakToFileCallsTtsModel:
    """speak_to_file() must call tts_to_file with the correct arguments."""

    def test_speak_to_file_calls_tts_model(self, tmp_path):
        mock_model = _make_mock_model()
        speaker = Speaker(speaker_wav="/ref/voice.wav", language="en")
        speaker._model = mock_model  # inject pre-loaded model

        output = str(tmp_path / "out.wav")
        _run(speaker.speak_to_file("Hello Nova", output_path=output))

        mock_model.tts_to_file.assert_called_once_with(
            text="Hello Nova",
            speaker_wav="/ref/voice.wav",
            language="en",
            file_path=output,
        )


class TestSpeakPlaysAudio:
    """speak() must synthesise audio and then call sd.play / sd.wait."""

    def test_speak_plays_audio(self, tmp_path):
        import sounddevice as sd
        import soundfile as sf

        mock_model = _make_mock_model()
        sf.read = MagicMock(return_value=(b"pcm_data", 22050))
        sd.play = MagicMock()
        sd.wait = MagicMock()

        speaker = Speaker(speaker_wav="/ref/voice.wav", language="en")
        speaker._model = mock_model

        _run(speaker.speak("Hello"))

        mock_model.tts_to_file.assert_called_once()
        sd.play.assert_called_once()
        sd.wait.assert_called_once()


class TestSpeakExceptionDoesNotRaise:
    """speak() must swallow exceptions and return None — never raise."""

    def test_speak_exception_does_not_raise(self):
        mock_model = _make_mock_model()
        mock_model.tts_to_file.side_effect = RuntimeError("GPU OOM")

        speaker = Speaker(language="en")
        speaker._model = mock_model

        # Must not raise anything
        result = _run(speaker.speak("crash me"))
        assert result is None


class TestLanguageOverrideInSpeak:
    """The language parameter passed to speak() must reach tts_to_file."""

    def test_language_override_in_speak(self, tmp_path):
        mock_model = _make_mock_model()
        speaker = Speaker(speaker_wav="/ref/voice.wav", language="en")
        speaker._model = mock_model

        output = str(tmp_path / "out_nl.wav")
        _run(speaker.speak_to_file("Hallo", output_path=output, language="nl"))

        _, kwargs = mock_model.tts_to_file.call_args
        assert kwargs["language"] == "nl"


class TestDefaultSpeakerUsedWhenNoSpeakerWav:
    """When speaker_wav is None, the first item from model.speakers must be passed."""

    def test_default_speaker_used_when_no_speaker_wav(self, tmp_path):
        mock_model = _make_mock_model(speakers=["builtin_speaker_0", "builtin_speaker_1"])
        speaker = Speaker(speaker_wav=None, language="en")
        speaker._model = mock_model

        output = str(tmp_path / "out_default.wav")
        _run(speaker.speak_to_file("Test default speaker", output_path=output))

        _, kwargs = mock_model.tts_to_file.call_args
        # speaker= (not speaker_wav=) must be set to the first available speaker
        assert kwargs.get("speaker") == "builtin_speaker_0"
        assert "speaker_wav" not in kwargs

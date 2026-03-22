"""
Tests for voice/speaker.py (edge-tts backend)
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def speaker():
    from voice.speaker import Speaker
    return Speaker(language="en")


class TestSpeakToFileCallsTtsModel:
    async def test_speak_to_file_calls_tts_model(self, speaker):
        """speak_to_file calls edge_tts.Communicate.save with correct path."""
        mock_communicate = AsyncMock()
        mock_cls = MagicMock(return_value=mock_communicate)

        with patch("voice.speaker.edge_tts") as mock_edge:
            mock_edge.Communicate = mock_cls
            await speaker.speak_to_file("Hello Nova", "/tmp/test.mp3")

        mock_cls.assert_called_once_with("Hello Nova", "en-US-AriaNeural")
        mock_communicate.save.assert_awaited_once_with("/tmp/test.mp3")


class TestSpeakPlaysAudio:
    async def test_speak_plays_audio(self, speaker):
        """speak() synthesises audio and plays it via sounddevice."""
        mock_communicate = AsyncMock()
        mock_cls = MagicMock(return_value=mock_communicate)

        with patch("voice.speaker.edge_tts") as mock_edge, \
             patch("voice.speaker.sf") as mock_sf, \
             patch("voice.speaker.sd") as mock_sd:
            mock_edge.Communicate = mock_cls
            mock_sf.read.return_value = (MagicMock(), 22050)
            await speaker.speak("Hello")

        mock_sd.play.assert_called_once()
        mock_sd.wait.assert_called_once()


class TestSpeakExceptionDoesNotRaise:
    async def test_speak_exception_does_not_raise(self, speaker):
        """An exception from edge_tts is caught; speak() returns None silently."""
        with patch("voice.speaker.edge_tts") as mock_edge:
            mock_edge.Communicate.side_effect = RuntimeError("network error")
            result = await speaker.speak("Hello")

        assert result is None


class TestLanguageOverrideInSpeak:
    async def test_language_override_in_speak(self, speaker):
        """Passing language='nl' uses the Dutch voice."""
        mock_communicate = AsyncMock()
        mock_cls = MagicMock(return_value=mock_communicate)

        with patch("voice.speaker.edge_tts") as mock_edge, \
             patch("voice.speaker.sf") as mock_sf, \
             patch("voice.speaker.sd"):
            mock_edge.Communicate = mock_cls
            mock_sf.read.return_value = (MagicMock(), 22050)
            await speaker.speak("Hallo", language="nl")

        mock_cls.assert_called_once_with("Hallo", "nl-NL-ColetteNeural")


class TestDefaultSpeakerUsedWhenNoSpeakerWav:
    async def test_unknown_language_falls_back_to_default_voice(self, speaker):
        """An unknown language code falls back to the default English voice."""
        mock_communicate = AsyncMock()
        mock_cls = MagicMock(return_value=mock_communicate)

        with patch("voice.speaker.edge_tts") as mock_edge, \
             patch("voice.speaker.sf") as mock_sf, \
             patch("voice.speaker.sd"):
            mock_edge.Communicate = mock_cls
            mock_sf.read.return_value = (MagicMock(), 22050)
            await speaker.speak("Hello", language="xx")

        mock_cls.assert_called_once_with("Hello", "en-US-AriaNeural")

"""
tests/test_voice/test_wake_word.py — Unit tests for voice/wake_word.py.

All external dependencies (faster_whisper, sounddevice, soundfile) are mocked.
"""

import asyncio
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from voice.wake_word import WakeWordDetector


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_whisper_mock(transcript: str):
    """Return a fake WhisperModel whose transcribe() returns the given text."""
    seg = MagicMock()
    seg.text = transcript

    mock_model = MagicMock()
    mock_model.transcribe.return_value = ([seg], MagicMock())

    mock_cls = MagicMock(return_value=mock_model)
    return mock_cls, mock_model


def _patch_audio():
    """Patch sounddevice and soundfile so no real audio hardware is needed."""
    import numpy as np
    mock_sd = MagicMock()
    mock_sd.rec.return_value = np.zeros((_CHUNK_SIZE := 32000, 1), dtype="float32")
    mock_sf = MagicMock()
    return mock_sd, mock_sf


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWakeWordCallbackFires:
    async def test_callback_fires_on_hey_nova(self):
        """Callback is called when transcript contains 'hey nova'."""
        import numpy as np

        mock_cls, mock_model = _make_whisper_mock("hey nova")
        mock_sd = MagicMock()
        mock_sd.rec.return_value = np.zeros((32000, 1), dtype="float32")
        mock_sf = MagicMock()

        callback_called = asyncio.Event()

        async def fake_callback():
            callback_called.set()

        stop_event = asyncio.Event()

        with patch("voice.wake_word.WhisperModel", mock_cls, create=True), \
             patch("faster_whisper.WhisperModel", mock_cls, create=True):
            detector = WakeWordDetector()
            detector._whisper = mock_model  # inject pre-loaded mock

            # After callback fires, set stop_event to end the loop
            original_callback = fake_callback
            async def one_shot_callback():
                await original_callback()
                stop_event.set()

            with patch("sounddevice.rec", mock_sd.rec), \
                 patch("sounddevice.wait", mock_sd.wait), \
                 patch("soundfile.write", mock_sf.write):
                await detector.listen_for_wake_word(one_shot_callback, stop_event)

        assert callback_called.is_set()


class TestWakeWordDoesNotFireOnUnrelated:
    async def test_no_callback_on_unrelated_speech(self):
        """Callback is NOT called for unrelated speech."""
        import numpy as np

        mock_cls, mock_model = _make_whisper_mock("what is the weather today")
        mock_sd = MagicMock()
        mock_sd.rec.return_value = np.zeros((32000, 1), dtype="float32")
        mock_sf = MagicMock()

        callback = MagicMock()
        stop_event = asyncio.Event()

        detector = WakeWordDetector()
        detector._whisper = mock_model

        call_count = 0

        async def counting_callback():
            nonlocal call_count
            call_count += 1

        # Run for 3 iterations then stop
        iteration = 0
        original_record = detector._record_and_check

        def limited_record():
            nonlocal iteration
            iteration += 1
            if iteration >= 3:
                stop_event.set()
            return detector._contains_wake_phrase("what is the weather today")

        with patch.object(detector, "_record_and_check", side_effect=limited_record):
            await detector.listen_for_wake_word(counting_callback, stop_event)

        assert call_count == 0


class TestWakeWordPhraseMatching:
    def test_hey_nova_matches(self):
        d = WakeWordDetector()
        assert d._contains_wake_phrase("hey nova how are you")

    def test_just_nova_matches(self):
        d = WakeWordDetector()
        assert d._contains_wake_phrase("nova what time is it")

    def test_unrelated_does_not_match(self):
        d = WakeWordDetector()
        assert not d._contains_wake_phrase("what is the capital of france")

    def test_case_insensitive(self):
        d = WakeWordDetector()
        assert d._contains_wake_phrase("HEY NOVA")


class TestWakeWordGracefulDegradation:
    async def test_graceful_when_whisper_fails_to_load(self):
        """If Whisper fails to load, listen_for_wake_word waits for stop_event."""
        callback = MagicMock()
        stop_event = asyncio.Event()
        stop_event.set()  # exit immediately

        detector = WakeWordDetector()

        with patch("voice.wake_word.WhisperModel", side_effect=RuntimeError("no model"), create=True):
            # _load_whisper will fail, should wait on stop_event
            with patch("faster_whisper.WhisperModel", side_effect=RuntimeError("no model"), create=True):
                await detector.listen_for_wake_word(callback, stop_event)

        callback.assert_not_called()

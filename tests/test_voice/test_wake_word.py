"""
tests/test_voice/test_wake_word.py — Unit tests for voice/wake_word.py.

All external dependencies (openwakeword, sounddevice) are mocked so no real
audio hardware is required.
"""

import asyncio
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_openwakeword(model_name: str, score: float):
    """
    Return a fake openwakeword package whose Model.predict always returns
    *score* for *model_name*.
    """
    oww_pkg = ModuleType("openwakeword")
    oww_model_mod = ModuleType("openwakeword.model")

    class FakeModel:
        def __init__(self, wakeword_models=None, inference_framework=None):
            self._model_name = wakeword_models[0] if wakeword_models else ""

        def predict(self, chunk):
            return {self._model_name: score}

    oww_model_mod.Model = FakeModel
    oww_pkg.model = oww_model_mod
    return {"openwakeword": oww_pkg, "openwakeword.model": oww_model_mod}


def _make_fake_sounddevice(chunks):
    """
    Return a fake sounddevice module whose InputStream yields *chunks* one
    by one through stream.read(), then raises StopIteration (causing the
    stream loop to exit).
    """
    import numpy as np

    sd_module = ModuleType("sounddevice")

    class FakeStream:
        def __init__(self, *a, **kw):
            self._iter = iter(chunks)

        def read(self, n):
            try:
                chunk = next(self._iter)
            except StopIteration:
                # Simulate end-of-stream by raising an error the thread handles
                raise RuntimeError("stream exhausted")
            return np.array(chunk, dtype="int16").reshape(-1, 1), False

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    sd_module.InputStream = FakeStream
    return sd_module


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestWakeWordCallbackFires:
    @pytest.mark.asyncio
    async def test_wake_word_callback_fires_when_threshold_exceeded(self):
        """Callback is awaited when prediction score exceeds the threshold."""
        import numpy as np

        fake_chunk = np.zeros(1280, dtype="int16")
        fake_sd = _make_fake_sounddevice([fake_chunk])
        fake_oww_mods = _make_fake_openwakeword("hey_nova", score=0.9)

        callback_called = asyncio.Event()

        async def fake_callback():
            callback_called.set()

        stop_event = asyncio.Event()

        with patch.dict(sys.modules, {**fake_oww_mods, "sounddevice": fake_sd}):
            import importlib
            import voice.wake_word as ww_mod
            importlib.reload(ww_mod)

            detector = ww_mod.WakeWordDetector(model_name="hey_nova", threshold=0.5)
            # The stream raises RuntimeError after one chunk, which causes the
            # thread to exit and sends None → loop exits without needing stop_event
            await detector.listen_for_wake_word(fake_callback, stop_event)

        assert callback_called.is_set(), "Callback should have been called"


class TestWakeWordStopsOnEvent:
    @pytest.mark.asyncio
    async def test_wake_word_stops_when_stop_event_set(self):
        """
        Setting the stop_event causes listen_for_wake_word to return cleanly
        even while the stream is running.
        """
        import numpy as np

        # Provide many chunks so the stream would never naturally end
        many_chunks = [np.zeros(1280, dtype="int16")] * 10
        fake_sd = _make_fake_sounddevice(many_chunks)
        # Score is below threshold so callback never fires
        fake_oww_mods = _make_fake_openwakeword("hey_nova", score=0.1)

        callback = MagicMock()

        stop_event = asyncio.Event()

        with patch.dict(sys.modules, {**fake_oww_mods, "sounddevice": fake_sd}):
            import importlib
            import voice.wake_word as ww_mod
            importlib.reload(ww_mod)

            detector = ww_mod.WakeWordDetector(model_name="hey_nova", threshold=0.5)

            # Set the stop event after a short delay while detection runs
            async def _set_stop():
                await asyncio.sleep(0.05)
                stop_event.set()

            await asyncio.gather(
                detector.listen_for_wake_word(callback, stop_event),
                _set_stop(),
            )

        # Verify the function returned (test would hang otherwise)
        assert stop_event.is_set()
        callback.assert_not_called()


class TestWakeWordGracefulDegradation:
    @pytest.mark.asyncio
    async def test_wake_word_graceful_when_openwakeword_not_installed(self):
        """
        When openwakeword is not importable, listen_for_wake_word returns
        without crashing and waits for stop_event.
        """
        callback = MagicMock()
        stop_event = asyncio.Event()

        # Remove openwakeword from sys.modules to simulate it not being installed
        modules_override = {
            "openwakeword": None,
            "openwakeword.model": None,
        }

        with patch.dict(sys.modules, modules_override):
            import importlib
            import voice.wake_word as ww_mod
            importlib.reload(ww_mod)

            detector = ww_mod.WakeWordDetector(model_name="hey_nova", threshold=0.5)

            # Set stop_event immediately so the fallback path exits right away
            stop_event.set()
            await detector.listen_for_wake_word(callback, stop_event)

        callback.assert_not_called()

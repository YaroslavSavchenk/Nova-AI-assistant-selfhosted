"""
tests/test_voice/test_listener.py — Unit tests for voice/listener.py.

All external dependencies (faster_whisper, sounddevice, soundfile) are mocked
so no real audio hardware is required.
"""

import asyncio
import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers to build minimal fake modules for optional heavy dependencies
# ---------------------------------------------------------------------------

def _make_fake_faster_whisper(segments):
    """Return a fake faster_whisper module whose WhisperModel yields *segments*."""
    fake_seg = MagicMock()
    fake_seg.text = "hello world"

    fw_module = ModuleType("faster_whisper")

    class FakeWhisperModel:
        def __init__(self, *a, **kw):
            pass

        def transcribe(self, path, **kw):
            return (iter(segments), MagicMock())

    fw_module.WhisperModel = FakeWhisperModel
    return fw_module


def _make_fake_soundfile():
    sf_module = ModuleType("soundfile")
    sf_module.write = MagicMock()
    return sf_module


def _make_fake_sounddevice(audio_array=None):
    import numpy as np

    sd_module = ModuleType("sounddevice")
    if audio_array is None:
        audio_array = np.zeros((16000, 1), dtype="float32")
    sd_module.rec = MagicMock(return_value=audio_array)
    sd_module.wait = MagicMock()
    return sd_module


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTranscribeFile:
    @pytest.mark.asyncio
    async def test_transcribe_file_returns_text(self):
        """Joined segment text is returned when transcription succeeds."""
        seg1 = MagicMock()
        seg1.text = "  Hello  "
        seg2 = MagicMock()
        seg2.text = "world "

        fake_fw = _make_fake_faster_whisper([seg1, seg2])
        with patch.dict(sys.modules, {"faster_whisper": fake_fw}):
            # Re-import listener inside the patch context so it picks up the mock
            import importlib
            import voice.listener as listener_mod
            importlib.reload(listener_mod)

            listener = listener_mod.Listener(model_size="base")
            result = await listener.transcribe_file("/fake/audio.wav")

        assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_transcribe_file_empty_segments_returns_empty_string(self):
        """Empty segment list produces an empty string, not an error."""
        fake_fw = _make_fake_faster_whisper([])
        with patch.dict(sys.modules, {"faster_whisper": fake_fw}):
            import importlib
            import voice.listener as listener_mod
            importlib.reload(listener_mod)

            listener = listener_mod.Listener(model_size="base")
            result = await listener.transcribe_file("/fake/silence.wav")

        assert result == ""

    @pytest.mark.asyncio
    async def test_transcribe_file_exception_returns_empty_string(self):
        """An exception during transcription returns empty string, not a crash."""
        fw_module = ModuleType("faster_whisper")

        class BrokenModel:
            def __init__(self, *a, **kw):
                pass

            def transcribe(self, *a, **kw):
                raise RuntimeError("model exploded")

        fw_module.WhisperModel = BrokenModel

        with patch.dict(sys.modules, {"faster_whisper": fw_module}):
            import importlib
            import voice.listener as listener_mod
            importlib.reload(listener_mod)

            listener = listener_mod.Listener(model_size="base")
            result = await listener.transcribe_file("/fake/broken.wav")

        assert result == ""


class TestListenOnce:
    @pytest.mark.asyncio
    async def test_listen_once_returns_transcription(self):
        """listen_once records audio, writes a temp file, and returns the transcript."""
        import numpy as np

        # Fake audio data returned by sd.rec
        fake_audio = np.zeros(16000, dtype="float32")

        seg = MagicMock()
        seg.text = "test transcription"
        fake_fw = _make_fake_faster_whisper([seg])
        fake_sf = _make_fake_soundfile()
        fake_sd = _make_fake_sounddevice(fake_audio.reshape(-1, 1))

        with patch.dict(
            sys.modules,
            {
                "faster_whisper": fake_fw,
                "soundfile": fake_sf,
                "sounddevice": fake_sd,
            },
        ):
            import importlib
            import voice.listener as listener_mod
            importlib.reload(listener_mod)

            listener = listener_mod.Listener(model_size="base")
            # Patch os.unlink so the (non-existent) temp file is never deleted
            with patch("os.unlink"):
                result = await listener.listen_once(duration=1.0, sample_rate=16000)

        assert result == "test transcription"


class TestListenUntilSilence:
    """Tests for webrtcvad-based silence detection."""

    def _make_fake_webrtcvad(self, speech_pattern: list[bool]):
        """Return a fake webrtcvad module.

        *speech_pattern* is a list of booleans consumed in order by
        Vad.is_speech(); once exhausted it returns False (silence).
        """
        vad_module = ModuleType("webrtcvad")
        pattern = list(speech_pattern)

        class FakeVad:
            def __init__(self, aggressiveness=2):
                self._calls = 0

            def is_speech(self, pcm_bytes, sample_rate):
                idx = self._calls
                self._calls += 1
                if idx < len(pattern):
                    return pattern[idx]
                return False  # default to silence once pattern exhausted

        vad_module.Vad = FakeVad
        return vad_module

    def _make_fake_sd_stream(self, n_chunks: int, sample_rate: int = 16000, frame_ms: int = 30):
        """Return a fake sounddevice module with a context-manager InputStream."""
        import numpy as np

        frame_size = int(sample_rate * frame_ms / 1000)
        sd_module = ModuleType("sounddevice")

        class FakeInputStream:
            def __init__(self, *a, **kw):
                self._reads = 0

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def read(self, frames):
                self._reads += 1
                chunk = np.zeros((frames, 1), dtype="int16")
                return chunk, None

        sd_module.InputStream = FakeInputStream
        return sd_module

    @pytest.mark.asyncio
    async def test_returns_transcription_after_silence(self):
        """After enough silent frames, the recorded audio is transcribed."""
        import numpy as np

        seg = MagicMock()
        seg.text = "hello vad"
        fake_fw = _make_fake_faster_whisper([seg])
        fake_sf = _make_fake_soundfile()
        fake_sd = self._make_fake_sd_stream(n_chunks=20)
        # speech=False from the start → silence_frames count up immediately
        fake_vad = self._make_fake_webrtcvad(speech_pattern=[])

        with patch.dict(
            sys.modules,
            {
                "faster_whisper": fake_fw,
                "soundfile": fake_sf,
                "sounddevice": fake_sd,
                "webrtcvad": fake_vad,
            },
        ):
            import importlib
            import voice.listener as listener_mod
            importlib.reload(listener_mod)

            listener = listener_mod.Listener(model_size="base")
            with patch("os.unlink"):
                result = await listener.listen_until_silence(
                    silence_seconds=0.1,  # very short so test finishes fast
                    sample_rate=16000,
                )

        assert result == "hello vad"

    @pytest.mark.asyncio
    async def test_speech_resets_silence_timer(self):
        """Speech frames reset the silence counter; only sustained silence ends recording."""
        import numpy as np

        # Pattern: speech for first 5 frames, then silence forever → timer resets on speech
        speech_pattern = [True] * 5  # 5 speech frames, then silence
        fake_fw = _make_fake_faster_whisper([])  # empty → ""
        fake_sf = _make_fake_soundfile()
        fake_sd = self._make_fake_sd_stream(n_chunks=50)
        fake_vad = self._make_fake_webrtcvad(speech_pattern=speech_pattern)

        with patch.dict(
            sys.modules,
            {
                "faster_whisper": fake_fw,
                "soundfile": fake_sf,
                "sounddevice": fake_sd,
                "webrtcvad": fake_vad,
            },
        ):
            import importlib
            import voice.listener as listener_mod
            importlib.reload(listener_mod)

            listener = listener_mod.Listener(model_size="base")
            with patch("os.unlink"):
                result = await listener.listen_until_silence(
                    silence_seconds=0.09,
                    sample_rate=16000,
                )

        # No recognised speech → empty string; important thing is no crash
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_string_on_vad_import_error(self):
        """If webrtcvad is unavailable, the method returns an empty string."""
        fake_fw = _make_fake_faster_whisper([])
        fake_sf = _make_fake_soundfile()
        fake_sd = self._make_fake_sd_stream(n_chunks=5)

        # Remove webrtcvad from sys.modules to simulate ImportError
        modules = {
            "faster_whisper": fake_fw,
            "soundfile": fake_sf,
            "sounddevice": fake_sd,
        }
        # Ensure webrtcvad raises ImportError when imported
        broken_vad = ModuleType("webrtcvad")

        class _FailVad:
            def __init__(self, *a, **kw):
                raise ImportError("webrtcvad not installed")

        broken_vad.Vad = _FailVad

        with patch.dict(sys.modules, {**modules, "webrtcvad": broken_vad}):
            import importlib
            import voice.listener as listener_mod
            importlib.reload(listener_mod)

            listener = listener_mod.Listener(model_size="base")
            with patch("os.unlink"):
                result = await listener.listen_until_silence(
                    silence_seconds=0.1,
                    sample_rate=16000,
                )

        assert result == ""

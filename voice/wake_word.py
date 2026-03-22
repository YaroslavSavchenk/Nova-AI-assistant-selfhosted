"""
voice/wake_word.py — Wake word detection.

Supports two backends, selected via config:
  - porcupine  (default) — Picovoice Porcupine, supports custom "Hey Nova" keyword
  - openwakeword          — fallback, built-in keywords only (alexa, hey_jarvis, …)

Porcupine setup (one-time):
  1. Create a free account at console.picovoice.ai
  2. Wake Word → New → type "Hey Nova" → train → download Linux .ppn file
  3. Place the .ppn file anywhere and set voice.wake_word.model_path in config.yaml
  4. Set voice.wake_word.access_key to your Picovoice AccessKey
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wake_word")

_SAMPLE_RATE = 16000
_CHUNK_SIZE = 512  # Porcupine requires 512 samples per frame at 16 kHz


class WakeWordDetector:
    """
    Listens continuously for a wake word and fires an async callback on detection.

    Tries Porcupine first (if access_key + model_path are set), then falls back
    to OpenWakeWord for built-in keywords.
    """

    def __init__(
        self,
        model_name: str = "hey_nova",
        threshold: float = 0.5,
        access_key: str = "",
        model_path: str = "",
    ):
        """
        Args:
            model_name:  Wake word name (used for OpenWakeWord fallback).
            threshold:   Detection confidence threshold (OpenWakeWord only).
            access_key:  Picovoice AccessKey (required for Porcupine).
            model_path:  Path to the .ppn keyword file (required for Porcupine).
        """
        self.model_name = model_name
        self.threshold = threshold
        self.access_key = access_key
        self.model_path = model_path
        self._backend: str = ""  # "porcupine" or "openwakeword" — set on load
        self._porcupine = None
        self._oww_model = None

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def _load_porcupine(self) -> bool:
        """Try to load the Porcupine backend."""
        if not self.access_key or not self.model_path:
            return False
        try:
            import pvporcupine  # noqa: PLC0415
            from pathlib import Path  # noqa: PLC0415

            ppn_path = str(Path(self.model_path).expanduser().resolve())
            log.info("Loading Porcupine wake word model from '%s' …", ppn_path)
            self._porcupine = pvporcupine.create(
                access_key=self.access_key,
                keyword_paths=[ppn_path],
            )
            self._backend = "porcupine"
            log.info("Porcupine wake word loaded (frame_length=%d).", self._porcupine.frame_length)
            return True
        except ImportError:
            log.warning("pvporcupine not installed — trying OpenWakeWord fallback.")
            return False
        except Exception as exc:
            log.warning("Failed to load Porcupine model: %s", exc)
            return False

    def _load_openwakeword(self) -> bool:
        """Try to load the OpenWakeWord backend."""
        try:
            import openwakeword  # noqa: PLC0415
            from openwakeword.model import Model  # noqa: PLC0415

            all_paths = openwakeword.get_pretrained_model_paths()
            matched = [p for p in all_paths if self.model_name.lower() in p.lower()]
            if not matched:
                log.warning(
                    "No OpenWakeWord model found for '%s'. Available: %s. "
                    "Configure Porcupine for custom wake words.",
                    self.model_name,
                    [p.split("/")[-1] for p in all_paths],
                )
                return False

            log.info("Loading OpenWakeWord model '%s' …", self.model_name)
            self._oww_model = Model(wakeword_model_paths=[matched[0]])
            self._backend = "openwakeword"
            log.info("OpenWakeWord model '%s' loaded.", self.model_name)
            return True
        except ImportError:
            log.warning("openwakeword not installed — wake word detection disabled.")
            return False
        except Exception as exc:
            log.warning("Failed to load OpenWakeWord model: %s", exc)
            return False

    def _load_model(self) -> bool:
        return self._load_porcupine() or self._load_openwakeword()

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def listen_for_wake_word(
        self,
        callback: callable,
        stop_event: asyncio.Event,
    ) -> None:
        """Stream mic audio and call callback() whenever the wake word fires."""
        loop = asyncio.get_event_loop()

        if not self._load_model():
            log.info("Wake word detection inactive; falling back to push-to-talk.")
            await stop_event.wait()
            return

        audio_queue: asyncio.Queue = asyncio.Queue()
        _triggered = False

        if self._backend == "porcupine":
            chunk_size = self._porcupine.frame_length
        else:
            chunk_size = 1280  # OpenWakeWord expects 1280 samples

        def _stream_audio() -> None:
            nonlocal _triggered
            try:
                import sounddevice as sd  # noqa: PLC0415
                import numpy as np  # noqa: PLC0415

                with sd.InputStream(
                    samplerate=_SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=chunk_size,
                ) as stream:
                    log.debug("Wake word stream started (%s backend).", self._backend)
                    while not stop_event.is_set():
                        chunk, _ = stream.read(chunk_size)
                        audio_chunk = np.squeeze(chunk)

                        detected = False
                        if self._backend == "porcupine":
                            result = self._porcupine.process(audio_chunk.tolist())
                            detected = result >= 0
                        else:
                            pred = self._oww_model.predict(audio_chunk)
                            score = max(pred.values()) if pred else 0.0
                            detected = score > self.threshold

                        if detected and not _triggered:
                            log.info("Wake word detected (%s).", self._backend)
                            _triggered = True
                            loop.call_soon_threadsafe(audio_queue.put_nowait, "WAKE")

            except Exception as exc:
                log.warning("Wake word stream error: %s", exc)
            finally:
                if self._backend == "porcupine" and self._porcupine:
                    self._porcupine.delete()
                loop.call_soon_threadsafe(audio_queue.put_nowait, None)

        future = loop.run_in_executor(_executor, _stream_audio)

        while not stop_event.is_set():
            try:
                event = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if event is None:
                break
            if event == "WAKE":
                try:
                    await callback()
                except Exception as exc:
                    log.warning("Wake word callback error: %s", exc)
                finally:
                    _triggered = False

        await asyncio.gather(future, return_exceptions=True)

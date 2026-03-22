"""
voice/wake_word.py — Wake word detection using OpenWakeWord.

Listens continuously for a configured wake word and fires an async callback
when the confidence score exceeds a threshold. Designed to run alongside the
main asyncio event loop without blocking it.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

# One dedicated thread for the blocking audio stream
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wake_word")

# Chunk size expected by OpenWakeWord: 1280 samples @ 16 kHz ≈ 80 ms
_CHUNK_SIZE = 1280
_SAMPLE_RATE = 16000


class WakeWordDetector:
    """
    Continuously streams microphone audio and fires a callback when the
    configured wake word is detected.

    If the ``openwakeword`` package is not installed, or the requested model
    fails to load, a warning is logged and detection is silently disabled.
    Nova will then fall back to push-to-talk / text mode.
    """

    def __init__(self, model_name: str = "hey_nova", threshold: float = 0.5):
        """
        Args:
            model_name: Name of the OpenWakeWord model to load.  Built-in
                        options include "alexa" and "hey_mycroft".  A custom
                        "hey_nova" model can be provided by placing the ONNX
                        file in the OpenWakeWord model directory.
            threshold:  Confidence score (0.0–1.0) above which a detection is
                        reported.
        """
        self.model_name = model_name
        self.threshold = threshold
        self._oww_model = None  # Loaded lazily on first call

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_model(self) -> bool:
        """
        Attempt to load the OpenWakeWord model.

        Returns:
            True on success, False if the package/model is unavailable.
        """
        try:
            import openwakeword  # noqa: PLC0415
            from openwakeword.model import Model  # noqa: PLC0415

            # Resolve model name to a file path for built-in models
            all_paths = openwakeword.get_pretrained_model_paths()
            matched = [p for p in all_paths if self.model_name.lower() in p.lower()]
            if not matched:
                log.warning(
                    "No built-in OpenWakeWord model found for '%s'. "
                    "Available: %s",
                    self.model_name,
                    [p.split("/")[-1] for p in all_paths],
                )
                return False

            model_path = matched[0]
            log.info("Loading OpenWakeWord model '%s' …", self.model_name)
            self._oww_model = Model(wakeword_model_paths=[model_path])
            log.info("OpenWakeWord model '%s' loaded.", self.model_name)
            return True
        except ImportError:
            log.warning(
                "openwakeword is not installed — wake word detection disabled. "
                "Nova will fall back to push-to-talk / text mode."
            )
            return False
        except Exception as exc:
            log.warning(
                "Failed to load OpenWakeWord model '%s': %s — "
                "wake word detection disabled.",
                self.model_name,
                exc,
            )
            return False

    # ------------------------------------------------------------------
    # Public async API
    # ------------------------------------------------------------------

    async def listen_for_wake_word(
        self,
        callback: callable,
        stop_event: asyncio.Event,
    ) -> None:
        """
        Stream microphone audio continuously and call *callback* whenever the
        wake word is detected.

        Audio chunks are produced in a background thread (to avoid blocking the
        event loop) and passed to the async side via an :class:`asyncio.Queue`.
        The OpenWakeWord scoring also runs in the background thread so the CPU
        work stays off the event loop.

        Args:
            callback:   Async callable invoked when the wake word fires.
            stop_event: Setting this event causes the listener to stop cleanly.
        """
        loop = asyncio.get_event_loop()

        if not self._load_model():
            # Gracefully degrade — just wait until stop_event is set
            log.info("Wake word detection inactive; waiting for stop_event.")
            await stop_event.wait()
            return

        audio_queue: asyncio.Queue = asyncio.Queue()
        _triggered = False  # cooldown flag — reset after callback completes

        def _stream_audio() -> None:
            """Background thread: stream mic chunks into the async queue."""
            nonlocal _triggered
            try:
                import sounddevice as sd  # noqa: PLC0415
                import numpy as np  # noqa: PLC0415

                with sd.InputStream(
                    samplerate=_SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=_CHUNK_SIZE,
                ) as stream:
                    log.debug("Wake word audio stream started.")
                    while not stop_event.is_set():
                        chunk, _ = stream.read(_CHUNK_SIZE)
                        audio_chunk = np.squeeze(chunk)
                        # Score on this thread (CPU-only, ~1 ms per chunk)
                        prediction = self._oww_model.predict(audio_chunk)
                        # Key may include version suffix (e.g. "alexa_v0.1")
                        score = max(prediction.values()) if prediction else 0.0
                        if score > self.threshold and not _triggered:
                            log.info(
                                "Wake word '%s' detected (score=%.3f).",
                                self.model_name,
                                score,
                            )
                            _triggered = True
                            # Signal the async side
                            loop.call_soon_threadsafe(
                                audio_queue.put_nowait, "WAKE"
                            )
            except Exception as exc:
                log.warning("Wake word audio stream error: %s", exc)
            finally:
                log.debug("Wake word audio stream stopped.")
                # Unblock the async consumer so it can exit cleanly
                loop.call_soon_threadsafe(audio_queue.put_nowait, None)

        # Start the background thread
        future = loop.run_in_executor(_executor, _stream_audio)

        # Consume events on the async side
        while not stop_event.is_set():
            try:
                event = await asyncio.wait_for(audio_queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                continue

            if event is None:
                # Stream thread exited
                break
            if event == "WAKE":
                try:
                    await callback()
                except Exception as exc:
                    log.warning("Wake word callback raised an exception: %s", exc)
                finally:
                    _triggered = False  # re-arm after interaction completes

        # Ensure the executor thread can finish
        await asyncio.gather(future, return_exceptions=True)

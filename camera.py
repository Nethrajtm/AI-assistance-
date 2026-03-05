"""
camera.py — OpenCV Camera Integration (MJPEG Streaming & Snapshots)
====================================================================
Provides:
  - ``CameraManager`` — thread-safe wrapper around ``cv2.VideoCapture``.
  - ``mjpeg_stream()`` — async generator yielding MJPEG frames for
    ``GET /video``.
  - ``capture_snapshot()`` — single JPEG frame for ``GET /snapshot``.

Gracefully handles missing cameras and releases resources on shutdown.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import AsyncGenerator, Optional

import cv2
import numpy as np

from config import settings

logger = logging.getLogger(__name__)


class CameraManager:
    """
    Thread-safe manager for a single video source.

    The camera can be a local device (by index) or a network stream (by URL).
    Frames are captured in a background thread so the async event loop
    is never blocked.
    """

    def __init__(self) -> None:
        self._cap: Optional[cv2.VideoCapture] = None
        self._lock = threading.Lock()
        self._running = False
        self._latest_frame: Optional[np.ndarray] = None
        self._thread: Optional[threading.Thread] = None

    # ----------------------------------------------------------
    # Lifecycle
    # ----------------------------------------------------------

    def start(self) -> bool:
        """
        Open the camera source and begin background frame capture.

        Returns True if the camera was successfully opened.
        """
        with self._lock:
            if self._running:
                return True

            source = settings.camera_url if settings.camera_url else settings.camera_index
            self._cap = cv2.VideoCapture(source)

            if not self._cap.isOpened():
                logger.warning(
                    "Camera source could not be opened: %s", source
                )
                self._cap.release()
                self._cap = None
                return False

            self._running = True
            self._thread = threading.Thread(target=self._capture_loop, daemon=True)
            self._thread.start()
            logger.info("Camera started on source=%s", source)
            return True

    def stop(self) -> None:
        """Release the camera and stop the background thread."""
        with self._lock:
            self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        with self._lock:
            if self._cap:
                self._cap.release()
                self._cap = None
            self._latest_frame = None
        logger.info("Camera stopped.")

    @property
    def is_running(self) -> bool:
        return self._running

    # ----------------------------------------------------------
    # Background thread
    # ----------------------------------------------------------

    def _capture_loop(self) -> None:
        """Continuously read frames in a background thread."""
        while self._running:
            with self._lock:
                if self._cap is None or not self._cap.isOpened():
                    break
                ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._latest_frame = frame
            else:
                # Short sleep to avoid busy-looping on read failure
                threading.Event().wait(0.01)

    # ----------------------------------------------------------
    # Frame access
    # ----------------------------------------------------------

    def get_frame_jpeg(self, quality: int = 80) -> Optional[bytes]:
        """
        Return the latest frame encoded as JPEG bytes.

        Parameters
        ----------
        quality : int
            JPEG quality (0–100).

        Returns None if no frame is available.
        """
        with self._lock:
            if self._latest_frame is None:
                return None
            encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
            success, buf = cv2.imencode(".jpg", self._latest_frame, encode_param)
            if not success:
                return None
            return buf.tobytes()


# ============================================================
# Module-level singleton
# ============================================================

camera_manager = CameraManager()


# ============================================================
# Streaming & Snapshot helpers (used by main.py routes)
# ============================================================

async def mjpeg_stream(
    fps: int = 15,
) -> AsyncGenerator[bytes, None]:
    """
    Async generator that yields multipart MJPEG frames.

    Each yielded chunk is a complete ``--frame`` boundary + JPEG payload
    ready to be sent as a ``StreamingResponse`` with
    ``media_type="multipart/x-mixed-replace; boundary=frame"``.
    """
    if not camera_manager.is_running:
        started = camera_manager.start()
        if not started:
            logger.error("Cannot start MJPEG stream — camera unavailable")
            return

    delay = 1.0 / fps
    while camera_manager.is_running:
        frame_bytes = camera_manager.get_frame_jpeg()
        if frame_bytes:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
            )
        await asyncio.sleep(delay)


async def capture_snapshot() -> Optional[bytes]:
    """
    Capture and return a single JPEG frame.

    Starts the camera if it isn't already running, waits briefly
    for a frame, then returns it.
    """
    if not camera_manager.is_running:
        started = camera_manager.start()
        if not started:
            logger.error("Cannot capture snapshot — camera unavailable")
            return None

    # Give the camera a moment to produce a frame
    for _ in range(30):
        frame = camera_manager.get_frame_jpeg(quality=90)
        if frame:
            return frame
        await asyncio.sleep(0.05)

    logger.warning("Snapshot timeout — no frame captured")
    return None

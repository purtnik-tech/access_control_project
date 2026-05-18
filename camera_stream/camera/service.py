import os
from abc import abstractmethod, ABC
from typing import Any

import cv2
import threading
import time
import logging

from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay"
EMPTY_FRAME_LIMIT = 5


class CameraABC(ABC):

    def __init__(self, url: str | Path, frame_width: int = 640, frame_height: int = 480, **kwargs):
        self.url = url
        self.frame_width = frame_width
        self.frame_height = frame_height
        self.cap = None
        self._frame = None
        self.running = True
        self.lock = threading.Lock()
        self.capture_lock = threading.RLock()
        self._connect()
        self.thread = threading.Thread(target=self._update, daemon=True, name="camera-stream-thread")
        self.thread.start()

    @property
    def frame(self) -> np.ndarray | None | bytes:
        with self.lock:
            if self._frame is None:
                return None
            try:
                return self._frame.copy()
            except AttributeError:
                return self._frame

    def stop(self):
        self.running = False
        if self.thread.is_alive():
            self.thread.join(timeout=2)
        with self.capture_lock:
            if self.cap:
                self.cap.release()

    def _connect(self):
        logger.warning("Подключение к камере...")
        with self.capture_lock:
            if self.cap:
                self.cap.release()
            cap = cv2.VideoCapture(self.url, cv2.CAP_FFMPEG)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
            self.cap = cap
        logger.warning("Камера подключена")

    @abstractmethod
    def _read_frame(self, cap: cv2.VideoCapture) -> tuple[bool, np.ndarray]:
        """

        :param cap:
        :return:
        """

    @classmethod
    def _preprocess_frame(cls, frame: np.ndarray) -> Any:
        """

        :param frame:
        :return:
        """
        return frame

    @classmethod
    def _set_frame(cls, frame: np.ndarray):
        """

        """
        return frame

    def _update(self):
        retry_delay = 0.2
        empty_frames = 0
        fps_counter = 0
        fps_start = time.time()

        while self.running:
            with self.capture_lock:
                cap = self.cap
            if cap is None or not cap.isOpened():
                logger.warning("Камера недоступна")
                self._connect()
                time.sleep(retry_delay)
                continue
            ret, frame = self._read_frame(cap)
            if not ret or frame is None:
                with self.lock:
                    self._frame = None
                    self._jpeg_frame = None
                empty_frames += 1
                logger.warning(f"Пустой кадр {empty_frames}/{EMPTY_FRAME_LIMIT}")
                if empty_frames >= EMPTY_FRAME_LIMIT:
                    logger.warning("Переподключение к камере")
                    empty_frames = 0
                    self._connect()
                time.sleep(retry_delay)
                continue
            empty_frames = 0
            frame = self._preprocess_frame(frame)
            with self.lock:
                self._frame = self._set_frame(frame)

            fps_counter += 1
            now = time.time()
            if now - fps_start >= 1:
                logger.info(f"Camera FPS: {fps_counter}")
                fps_counter = 0
                fps_start = now


class CameraStream(CameraABC):

    def _read_frame(self, cap: cv2.VideoCapture):
        return cap.read()

    def _preprocess_frame(self, frame: np.ndarray) -> bytes | None:
        ret_jpeg, jpeg = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if ret_jpeg:
            return jpeg.tobytes()
        return None


class CameraStreamOCR(CameraABC):

    def _read_frame(self, cap: cv2.VideoCapture):
        grabbed = False
        for _ in range(10):
            grabbed = cap.grab()
        if not grabbed:
            return False, None
        return cap.retrieve()

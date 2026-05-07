import logging
from time import sleep
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

import cv2
import numpy as np

from processing.utils import preprocess
from processing.utils.detectors.protocols import DetectorProtocol
from processing.utils.ocrs.protocols import OCRProtocol


logger = logging.getLogger(__name__)


@dataclass
class AnalyzerResult:
    value: Any
    status: bool = True


class FrameAnalyzerABC(ABC):
    """
    Извлекает результат из кадра
    """

    @abstractmethod
    def process(self, frame: np.ndarray) -> Optional[AnalyzerResult]:
        """

        :param frame:
        :return:
        """


class YoloFrameAnalyzer(FrameAnalyzerABC):
    """

    """

    def __init__(self, detector: DetectorProtocol, ocr: OCRProtocol):
        self.detector = detector
        self.ocr = ocr

    def process(self, frame: np.ndarray) -> Optional[AnalyzerResult]:
        sleep(3)
        if frame is None:
            logger.info(f'Не удалось получить кадр!')
            return AnalyzerResult(None, False)
        logger.info(f'Кадр получен. Ищу номер')
        if not (boxes := self.detector.detect(frame)):
            logger.info(f'Не удалось получить номер из кадра! {boxes}')
            return AnalyzerResult(None, False)
        logger.info(f'В кадре имеется номер!')
        for box in boxes:
            crop = self._crop(frame, box)
            if crop.size == 0:
                continue
            text = self.ocr.recognize(preprocess(crop))
            if text := self._normalize_text(text):
                logger.info(f'Удалось извлечь текст номера: {text}')
                return AnalyzerResult(text, True)
            logger.info(f'Не удалось извлечь текст номера: {text}')
        return AnalyzerResult(None, False)

    @classmethod
    def _crop(cls, frame: np.ndarray, box):
        h, w = frame.shape[:2]
        x1, y1, x2, y2 = box

        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(w, x2)
        y2 = min(h, y2)
        if x2 - x1 < 20 or y2 - y1 < 20:
            return np.ndarray([])
        return frame[y1:y2, x1:x2]

    @classmethod
    def _normalize_text(cls, text: str) -> str | None:
        if not text:
            return None
        text = text.strip().upper().replace(' ', '')
        return text

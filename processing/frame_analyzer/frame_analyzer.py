import logging
from datetime import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from processing.utils.detectors.protocols import DetectorProtocol
from processing.utils.ocrs.protocols import OCRProtocol


logger = logging.getLogger(__name__)


@dataclass
class AnalyzerResult:
    value: Any
    status: bool = True
    conf: float = None


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
        if frame is None:
            logger.debug(f'Не удалось получить кадр!')
            return AnalyzerResult(None, False)
        logger.debug(f'Приступаю к вычислению номера')
        frame_data = self.detector.detect(frame)
        if frame_data is None:
            logger.warning(f'Не нашёл номер на изображении вообще!')
            return AnalyzerResult(None, False)
        crop_frame, conf = frame_data
        if crop_frame is None:
            logger.warning(f'Не удалось найти номер на изображении!')
            return AnalyzerResult(None, False)
        logger.debug(f'В кадре имеется номер! Уверенность: {round(conf, 4)}')
        text = self.ocr.recognize(crop_frame)
        if text := self._normalize_text(text):
            logger.info(f'Удалось извлечь номер с изображения: `{text}` `{datetime.now()}`')
            return AnalyzerResult(text, True, conf)
        logger.warning(f'Не удалось извлечь текст номера: {text}')
        return AnalyzerResult(None, False)

    @classmethod
    def _normalize_text(cls, text: str) -> str | None:
        if not text:
            return None
        text = text.strip().upper().replace(' ', '')
        return text

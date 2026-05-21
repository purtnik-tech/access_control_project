import logging
import os
import re

import cv2
import numpy as np
from paddleocr import PaddleOCR

logger = logging.getLogger(__name__)


class LicensePlateOCR:

    def __init__(self):
        model_dir = os.getenv('PADDLE_OCR_REC_MODEL_DIR')
        if not model_dir:
            raise RuntimeError('PADDLE_OCR_REC_MODEL_DIR не задан в .env')
        device = os.getenv('PADDLE_OCR_DEVICE', 'gpu:0')

        self.ocr = PaddleOCR(
            text_recognition_model_dir=model_dir,
            device=device,
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
        )

        self.allowed_pattern = re.compile(r"[^A-Z0-9]")

    def preprocess(self, img: np.ndarray) -> np.ndarray:
        if img is None or img.size == 0:
            raise ValueError("Empty image crop")

        # resize
        img = cv2.resize(
            img,
            (320, 64),
            interpolation=cv2.INTER_CUBIC
        )

        # grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # denoise
        gray = cv2.bilateralFilter(gray, 9, 75, 75)

        # contrast enhancement
        clahe = cv2.createCLAHE(
            clipLimit=2.0,
            tileGridSize=(8, 8)
        )
        gray = clahe.apply(gray)

        return cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)

    def postprocess(self, text: str) -> str:
        text = text.upper()
        text = self.allowed_pattern.sub("", text)

        return text.strip()

    def recognize(self, crop: np.ndarray) -> str | None:
        if crop is None or crop.size == 0:
            logger.debug('OCR: пустой crop, выходим')
            return None

        # Препроцессинг даёт PaddleOCR нормальный 320x64 вход с поднятым
        # контрастом (CLAHE) и сглаживанием (bilateralFilter). На мелких
        # кропах (41x166 и подобных) без него confidence падает с ~0.43
        # до ~0.08 — модель просто не различает символы. Проверено логом.
        img = self.preprocess(crop)
        logger.debug('OCR: crop=%s preprocessed=%s', crop.shape, img.shape)

        result = self.ocr.ocr(img)
        logger.debug('OCR raw result type=%s, value=%r', type(result).__name__, result)

        if not result:
            logger.debug('OCR: пустой результат от PaddleOCR')
            return None

        data = result[0]
        rec_texts = data.get("rec_texts", []) if isinstance(data, dict) else []
        rec_scores = data.get("rec_scores", []) if isinstance(data, dict) else []
        logger.info('OCR: rec_texts=%r rec_scores=%r', rec_texts, rec_scores)

        if not rec_texts:
            logger.debug('OCR: rec_texts пуст')
            return None

        filtered = [t for t, c in zip(rec_texts, rec_scores) if c >= 0.3]
        logger.info('OCR: после фильтра conf>=0.3 -> %r', filtered)

        if not filtered:
            logger.debug('OCR: все confidence ниже порога 0.3')
            return None

        raw_text = "".join(filtered)
        result_text = self.postprocess(raw_text)
        logger.info('OCR: postprocess(%r) -> %r', raw_text, result_text)
        return result_text

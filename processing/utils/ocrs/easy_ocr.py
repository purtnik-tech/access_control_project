import os
import re

import cv2
import numpy as np
from paddleocr import PaddleOCR


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
            return None

        img = self.preprocess(crop)

        result = self.ocr.ocr(img)

        if not result:
            return None

        data = result[0]

        rec_texts = data.get("rec_texts", [])
        rec_scores = data.get("rec_scores", [])

        if not rec_texts:
            return None

        filtered = []

        for text, confidence in zip(rec_texts, rec_scores):
            if confidence >= 0.5:
                filtered.append(text)

        if not filtered:
            return None

        raw_text = "".join(filtered)

        return self.postprocess(raw_text)

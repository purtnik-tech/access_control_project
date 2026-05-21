import logging

import numpy as np

from ultralytics import YOLO


logger = logging.getLogger(__name__)


class YoloDetector:
    def __init__(self, name: str):
        self.model = YOLO(name)
        self.model.to('cuda')
        logger.info(f'Yolo модель: {self.model.names}')

    def detect(self, frame: np.ndarray) -> tuple[np.ndarray, float] | None:
        results = self.model(frame, conf=0.2)
        result = results[0]
        h, w = frame.shape[:2]
        for r in result:
            for box in r.boxes:
                if float(box.conf[0]) < 0.2:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                # Расширяем bbox на 15% по каждой стороне, чтобы OCR получил
                # номер с небольшими полями (модель часто обрезает по краям).
                pad_x = int((x2 - x1) * 0.15)
                pad_y = int((y2 - y1) * 0.15)
                x1 = max(0, x1 - pad_x)
                y1 = max(0, y1 - pad_y)
                x2 = min(w, x2 + pad_x)
                y2 = min(h, y2 + pad_y)
                return frame[y1:y2, x1:x2], float(box.conf[0])
        return None
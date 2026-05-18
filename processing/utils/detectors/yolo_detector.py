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
        results = self.model(frame, conf=0.4)
        result = results[0]
        for r in result:
            for box in r.boxes:
                if float(box.conf[0]) < 0.5:
                    continue
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                return frame[y1:y2, x1: x2], float(box.conf[0])
        return None
import numpy as np

from ultralytics import YOLO


class YoloDetector:
    def __init__(self, name: str):
        self.model = YOLO(name)

    def detect(self, frame: np.ndarray) -> list:
        result = self.model(frame)
        boxes = []
        
        for r in result:
            if r.boxes is None:
                continue
            for b in r.boxes:
                # if float(b.conf[0]) < 0.5:
                #     continue
                x1, y1, x2, y2 = map(int, b.xyxy[0])
                boxes.append([x1, y1, x2, y2])
        return boxes


import cv2
import numpy as np


def preprocess(image: np.ndarray) -> np.ndarray:
    # Цвет
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    # Увеличение
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    # Шум
    gray = cv2.bilateralFilter(gray, 11, 17, 17)
    # Бинаризаций
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU)
    return thresh
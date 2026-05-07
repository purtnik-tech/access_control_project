from typing import Protocol

import numpy as np


class DetectorProtocol(Protocol):

    def detect(self, frame: np.ndarray) -> list:
        ...
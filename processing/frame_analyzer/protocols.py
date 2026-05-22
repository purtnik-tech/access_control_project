from typing import Protocol

import numpy as np

from processing.frame_analyzer.frame_analyzer import AnalyzerResult


class FrameAnalyzerProtocol(Protocol):

    def process(self, frame: np.ndarray) -> AnalyzerResult:
        ...

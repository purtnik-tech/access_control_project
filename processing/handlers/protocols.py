from typing import Protocol

from processing.frame_analyzer.frame_analyzer import AnalyzerResult


class FrameHandlerProtocol(Protocol):

    def __call__(self, result: AnalyzerResult):
        ...
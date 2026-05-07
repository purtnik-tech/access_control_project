import threading
import logging

from enum import Enum
from time import sleep

from camera_stream.camera.service import CameraStream
from processing.frame_analyzer.protocols import FrameAnalyzerProtocol

logger = logging.getLogger(__name__)


class BaseFrameProcessor:
    """
    Получает кадр с изображения и вызывает метод для обработки для кадра
    """
    
    class Mode(Enum):
        """
        
        """
        ULTRA_SLOW = 5.0
        VERY_SLOW = 1.0
        SLOW = 0.75
        NORMAL = 0.5
        FAST = 0.25
        REALTIME = 0.1

    def __init__(self, camera: CameraStream, frame_analyzer: FrameAnalyzerProtocol, mode: Mode = Mode.REALTIME):
        self.camera = camera
        self.frame_analyzer = frame_analyzer
        self._mode = mode
        
        self._running = False
        self._thread = threading.Thread(target=self._handle, daemon=True)
        
    def run(self):
        if self._running:
            raise RuntimeError('Процесс обработки уже запущен!')
        self._running = True
        self._thread.start()
    
    def _get_frame(self):
        raise NotImplementedError
    
    def _handle(self):
        while True:
            result = self.frame_analyzer.process(self._get_frame())
            print(f'{self.frame_analyzer.__class__.__name__}: {result.value}')
            sleep(self._mode.value)

    def loop(self):
        self._running = True
        try:
            self._handle()
        except KeyboardInterrupt:
            self._running = False
            raise KeyboardInterrupt
           

class FrameProcessor(BaseFrameProcessor):
    """
    
    """
    
    def _get_frame(self):
        return self.camera.frame
    
            
class JPEGFrameProcessor(BaseFrameProcessor):
    """
    
    """
    
    def _get_frame(self):
        return self.camera.jpeg_frame
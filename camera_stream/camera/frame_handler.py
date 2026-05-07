import threading
from time import sleep

from .service import CameraStream


class FrameProcessor:
    def __init__(self, camera: CameraStream, pipeline_processor, interval: float = 0.9):
        self.camera = camera
        self.interval = interval
        self.pipeline_processor = pipeline_processor
        self._running = False
        self._thread = threading.Thread(target=self._handle, daemon=True)

    def run(self):
        if not self._running:
            self._running = True
            self._thread.start()
        else:
            raise RuntimeError('This thread is already running')

    def _handle(self):
        while True:
            if not (frame := self.camera.frame):
                sleep(self.interval)
                continue
            self.pipeline_processor.process(frame)
            sleep(self.interval)

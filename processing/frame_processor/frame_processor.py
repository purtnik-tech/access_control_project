import threading
import logging

from enum import Enum
from time import sleep

from camera_stream.camera.service import CameraStream
from processing.frame_analyzer.protocols import FrameAnalyzerProtocol
from processing.handlers.protocols import FrameHandlerProtocol

logger = logging.getLogger(__name__)


class BaseFrameProcessor:

    class Mode(Enum):
        ULTRA_SLOW = 5.0
        VERY_SLOW = 1.0
        SLOW = 0.75
        NORMAL = 0.5
        FAST = 0.25
        REALTIME = 0.1

    def __init__(
        self,
        camera: CameraStream,
        frame_analyzer: FrameAnalyzerProtocol,
        handler: FrameHandlerProtocol,
        mode: Mode = Mode.REALTIME,
    ):
        logger.info(f'Режим обработчика: {mode.name}. Интервал: {mode.value}')

        self._handler = handler
        self.camera = camera
        self.frame_analyzer = frame_analyzer
        self._mode = mode

        self._running = False

        self._thread = threading.Thread(
            target=self._handle,
            daemon=True,
            name="frame-processor-thread"
        )

    def run(self):
        if self._running:
            raise RuntimeError('Процесс уже запущен')

        self._running = True
        self._thread.start()

    def stop(self):
        self._running = False

    def _handle(self):

        while self._running:
            frame = self.camera.frame
            if frame is None:
                sleep(0.1)
                continue
            try:
                result = self.frame_analyzer.process(frame)
                if result is not None and result.status and result.value:
                    logger.debug('Plate -> camera.last_recognized_plate=%r', result.value)
                    self._handler(result)
            except Exception as e:
                logger.exception('Ошибка %s обработки кадра: %s', e.__class__.__name__, e)
            sleep(self._mode.value)

    def loop(self):
        self.run()
        self._thread.join()


class FrameProcessor(BaseFrameProcessor):
    """

    """

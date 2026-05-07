import cv2
import threading
import time
import logging


logger = logging.getLogger(__name__)


class CameraStream:
    """

    :ivar cap: Объект VideoCapture, клиент к видеопотоку
    :ivar _frame: Последний кадр
    :ivar lock: Блокировка
    :ivar running: Флаг, который используется для остановки потока 
    :ivar thread: Фоновый поток постоянного чтения кадров 
    """

    def __init__(self, url: str, frame_width: int = 640, frame_height: int = 480):
        """
        :param url: Адрес камеры (rtsp)
        """
        self.url = url
        self.cap = None
        self._frame = None
        self._jpeg_frame = None
        self.running = True
        self.frame_width = frame_width
        self.frame_height = frame_height
                
        self.lock = threading.Lock()
        self.thread = threading.Thread(target=self._update, daemon=True)
        
        self._connect()
        self.thread.start()

    @property
    def frame(self):
        """
        :return: Последний кадр
        """
        with self.lock:
            return self._frame

    @property
    def jpeg_frame(self):
        """
        :return: Последний кадр кодированный в JPEG
        """
        with self.lock:
            return self._jpeg_frame

    def stop(self):
        """
        Останавливает поток
        """
        self.running = False
        if self.cap:
            self.cap.release()
        
    def _connect(self):
        """
        Устанавливает первичное подключение или переподключение к камере
        """
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(self.url)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.frame_width)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.frame_height)
        
    def _update(self):
        """
        Фоновый цикл постоянного чтения кадров с камеры и помещения последнего кадра в self.frame
        :return:
        """
        retry_delay = 1
        while self.running:
            if not self.cap or not self.cap.isOpened():
                logger.warning(f'Произвожу повторное подключение к камере! cap={self.cap}, status={self.cap.isOpened()}')
                self._connect()
                time.sleep(retry_delay)
                continue
            ret, frame = self.cap.read() # Сырой кадр
            if not ret:
                logger.warning(f'Не удалось получить кадр! ret={ret}')
                time.sleep(retry_delay)
                continue
            ret, buffer = cv2.imencode('.jpg', frame)
            if not ret:
                time.sleep(retry_delay)
                continue
            with self.lock:
                logger.debug(f'Устанавливаю кадры self._frame & self._jpeg_frame')
                self._frame = frame
                self._jpeg_frame = buffer.tobytes()
            time.sleep(0.03)
            

import logging
import cv2

from django.test import SimpleTestCase
from ultralytics import YOLO

from camera_stream.camera.registry import get_camera
from processing.utils import preprocess

LICENSE_PLATE_DETECT_MODEL_PATH = 'C:\\Users\\localadmin\\PycharmProjects\\access_control_project\\tools\\train\\car_license\\best.pt'
logger = logging.getLogger(__name__)


class OneShotFrameTest(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        logger.info(f'Инициализация модели: {LICENSE_PLATE_DETECT_MODEL_PATH}')
        cls.model = YOLO(LICENSE_PLATE_DETECT_MODEL_PATH)
        logger.info(f'Инициализация модели успешна: {cls.model.names}')
        logger.info(f'Получаю объект подключения к камере')
        cls.camera = get_camera()
        logger.info(f'Камеру получил: {cls.camera}')

    def get_frame(self):
        while (frame := self.camera.frame) is None:
            pass
        return frame

    def test_one_shot(self):
        frame = self.get_frame()
        logger.warning(type(frame))
        results = self.model(frame,conf=0.4)
        result = results[0]

        cv2.imshow('Camera', result.plot())
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        for r in result:
            for box in r.boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                crop = frame[y1:y2, x1: x2]
                cv2.imshow('Camera', crop)
                cv2.waitKey(0)
                cv2.destroyAllWindows()

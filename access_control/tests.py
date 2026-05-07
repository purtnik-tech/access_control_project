import os
import re

from time import sleep

import cv2
import pytesseract
import torch
import logging

from django.test import SimpleTestCase


logger = logging.getLogger(__name__)
pytesseract.pytesseract.tesseract_cmd = os.environ.get('TESSERACT_PATH')
TEST_IMAGE = 'test_image.jpeg'


class CheckGPUTest(SimpleTestCase):
    """
    Проверка системы и библиотек на работу с CUDA ядрами
    """

    def test_cuda(self):
        """
        Проверка системы на работоспособность с CUDA.
        :raises AssertionError: CUDA ядра не доступны в системе.
        """
        self.assertTrue(torch.cuda.is_available(), 'CUDA НЕ доступна. GPU не будет использоваться.')
        logger.info(f'Количество GPU: {torch.cuda.device_count()}')
        logger.info(f'Имя GPU: {torch.cuda.get_device_name(0)}')
        logger.info(f'Текущее устройство: {torch.cuda.current_device()}')

    def test_torch_cuda(self):
        """
        Проверка версии CUDA в PyTorch
        :raises AssertionError: Не удалось обнаружить версию CUDA
        :raises AttributeError: Ошибка получения атрибутов PyTorch
        """
        self.assertTrue(torch.version.cuda, 'Не удалось обнаружить версию CUDA в PyTorch')
        logger.info(f'Версия CUDA в PyTorch: {torch.version.cuda}')

    def test_open_cv_cuda(self):
        """
        Проверка CUDA в OpenCV2
        :raises AssertionError: OpenCV работает не с CUDA
        :raises AttributeError: Ошибка получения атрибутов cv2
        """
        open_cv_cuda = cv2.cuda.getCudaEnabledDeviceCount()
        self.assertTrue(open_cv_cuda, 'OpenCV не собран с CUDA')
        logger.info(f'OpenCV собран с CUDA: {open_cv_cuda}')


class CameraSmallTest(SimpleTestCase):
    """
    Тест камеры
    """

    @classmethod
    def setUpClass(cls):
        """
        Инициализация объекта камеры
        """
        cls.cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) # 0 | 1

    def test_camera(self):
        """
        Проверка доступа к камере и получения кадров
        :raises AssertionError: Камера не открывается
        """
        self.assertTrue(self.cap.isOpened(), 'Камера не открывается')
        for i in range(30):  # попробуем получить 30 кадров
            ret, frame = self.cap.read()
            if ret:
                cv2.imwrite(f'test_frame_{i}.jpg', frame)
                logger.info(f"Кадр {i} сохранён")
            else:
                logger.warning(f"Кадр {i} не получен!")
            sleep(0.1)
        self.cap.release()


class OCRTest(SimpleTestCase):
    """
    Тестирует работу OCR Tesseract на специальном изображении гос.номера.
    """

    def test_ocr(self):
        image = cv2.cvtColor(cv2.imread(TEST_IMAGE), cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(image, 150, 255, cv2.THRESH_BINARY)
        raw_text = pytesseract.image_to_string(thresh, lang='rus', config='--psm 8')
        logger.info(f'Сырой текст изображения: {TEST_IMAGE}: {raw_text}')
        plate = re.sub(r'[^A-Z0-9А-Я]', '', raw_text).strip()
        logger.info(f'Обработанный изображения: {TEST_IMAGE}: {plate}')

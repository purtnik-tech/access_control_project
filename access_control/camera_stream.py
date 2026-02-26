import threading
import time
import cv2
import pytesseract
import re
from datetime import datetime
from django.core.cache import cache
from .models import LicensePlate, Pass

# Настройка пути к tesseract (если требуется)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'  # для Windows

class CameraStream:
    def __init__(self, camera_id=0):
        self.camera_id = camera_id
        self.cap = None
        self.stopped = False
        self.lock = threading.Lock()
        self.last_frame = None               # последний сырой кадр
        self.last_processed_frame = None     # кадр, на котором распознавали
        self.last_plate = ""                 # распознанный номер
        self.last_access_result = ""         # результат доступа
        self.last_access_code = ""            # код для css класса
        self.processing_interval = 2.0        # интервал распознавания (сек)
        self.last_process_time = 0

    def start(self):
        print(f"[DEBUG] Попытка открыть камеру {self.camera_id} с бэкендом DSHOW")
        self.cap = cv2.VideoCapture(self.camera_id, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            print("[DEBUG] Не удалось открыть камеру с DSHOW")
            # Не пробуем другие бэкенды – так мы точно узнаем, работает ли DSHOW
            raise RuntimeError("Камера не открывается с бэкендом DSHOW")
        print("[DEBUG] Камера успешно открыта с DSHOW")

        # Настройка параметров захвата (опционально)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        # Устанавливаем формат MJPG, если поддерживается
        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*'MJPG'))
        # Декодируем обратно в строку
        actual_fourcc = int(self.cap.get(cv2.CAP_PROP_FOURCC))
        fourcc_str = "".join([chr((actual_fourcc >> 8 * i) & 0xFF) for i in range(4)])
        print(f"Установленный FOURCC: {fourcc_str}")

        actual_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        actual_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        print(f"[DEBUG] Реальное разрешение: {actual_w} x {actual_h}")

        self.stopped = False
        self.thread = threading.Thread(target=self._update, args=())
        self.thread.daemon = True
        self.thread.start()
        print("[DEBUG] Фоновый поток запущен")
        return self

    def _update(self):
        print("[DEBUG] _update thread started")
        frame_count = 0
        while not self.stopped:
            try:
                if self.cap is None or not self.cap.isOpened():
                    print("[DEBUG] Camera not open, waiting...")
                    time.sleep(1)
                    continue

                ret, frame = self.cap.read()
                if not ret:
                    print("[DEBUG] Frame read failed")
                    time.sleep(0.1)
                    continue

                frame_count += 1
                if frame_count % 30 == 0:
                    print(f"[DEBUG] Frames captured: {frame_count}")

                with self.lock:
                    self.last_frame = frame.copy()

                # Если включено распознавание, добавьте его здесь (но пока отключите для теста)
                now = time.time()
                if now - self.last_process_time > self.processing_interval:
                    self.last_process_time = now
                    processed = frame.copy()
                    plate = self._recognize_plate(processed)
                    with self.lock:
                        self.last_processed_frame = processed
                        self.last_plate = plate
                        self.last_access_result, self.last_access_code = self._check_access(plate)

            except Exception as e:
                print(f"[DEBUG] Exception in _update: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

    def _recognize_plate(self, frame):
        try:
            # Область интереса (ROI) можно вырезать, если номер всегда в одной части кадра
            # Для теста обрабатываем весь кадр
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Уменьшаем шум
            gray = cv2.medianBlur(gray, 3)
            # Адаптивная бинаризация
            thresh = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                           cv2.THRESH_BINARY, 11, 2)
            # Можно инвертировать (белые буквы на чёрном)
            thresh = cv2.bitwise_not(thresh)

            # Конфигурация Tesseract: ожидаем один номер (--psm 8 - отдельное слово)
            # + русские и английские буквы, цифры
            custom_config = r'--psm 8 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789АВЕКМНОРСТУХ'
            text = pytesseract.image_to_string(thresh, lang='rus+eng', config=custom_config)
            plate = re.sub(r'[^A-Z0-9А-Я]', '', text).strip()
            return plate
        except Exception as e:
            print(f"OCR error: {e}")
            return ""

    def _check_access(self, plate):
        """Проверка доступа по номеру."""
        if not plate:
            return "Номер не распознан, ручной доступ", "unrecognized"
        try:
            lp = LicensePlate.objects.get(plate_number=plate)
        except LicensePlate.DoesNotExist:
            return "Доступ запрещён", "denied"

        # Ищем действующий пропуск для этого номера
        passes = Pass.objects.filter(license_plate=lp, start_date__lte=datetime.now().date())
        if not passes.exists():
            return "Доступ запрещён (нет пропуска)", "denied"

        p = passes.first()
        if p.pass_type == 'permanent':
            return "Постоянный, Въезд разрешён", "permanent"
        else:  # temporary
            # Проверка даты окончания
            if p.end_date and p.end_date >= datetime.now().date():
                return "Временный, ручной контроль", "temporary"
            else:
                return "Доступ запрещён (просрочен)", "denied"

    def get_frame(self):
        with self.lock:
            if self.last_frame is None:
                # print("[DEBUG] get_frame: last_frame is None")  # можно раскомментировать
                return None
            ret, jpeg = cv2.imencode('.jpg', self.last_frame)
            if not ret:
                print("[DEBUG] JPEG encoding failed")
                return None
            return jpeg.tobytes()

    def get_processed_frame(self):
        with self.lock:
            if self.last_processed_frame is None:
                return None
            ret, jpeg = cv2.imencode('.jpg', self.last_processed_frame)
            return jpeg.tobytes()

    def get_status(self):
        with self.lock:
            return {
                'plate': self.last_plate,
                'access': self.last_access_result,
                'code': self.last_access_code
            }

    def stop(self):
        self.stopped = True
        if self.cap:
            self.cap.release()
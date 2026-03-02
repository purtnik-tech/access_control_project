import threading
import time
import cv2
import re
import easyocr
from datetime import datetime
from .models import LicensePlate, Pass

# Инициализация EasyOCR (один раз для всего приложения)
# reader будет создан при первом вызове
_ocr_reader = None


def get_ocr_reader():
    """Создает или возвращает существующий экземпляр EasyOCR"""
    global _ocr_reader
    if _ocr_reader is None:
        print("[DEBUG] Инициализация EasyOCR (может занять несколько секунд)...")
        # Создаем ридер для русского и английского языков
        _ocr_reader = easyocr.Reader(['ru', 'en'], gpu=False)  # gpu=True если есть CUDA
        print("[DEBUG] EasyOCR инициализирован")
    return _ocr_reader


class CameraStream:
    def __init__(self, camera_source=0, use_network=False, camera_id=None):
        """
        camera_source: для локальной камеры - индекс (0, 1...)
                      для сетевой камеры - URL (строка)
        use_network: True для сетевой камеры, False для локальной
        camera_id: для обратной совместимости
        """
        # Для обратной совместимости
        if camera_id is not None:
            self.camera_source = camera_id
            self.use_network = False
            print(f"[DEBUG] Используется устаревший параметр camera_id={camera_id}")
        else:
            self.camera_source = camera_source
            self.use_network = use_network

        self.cap = None
        self.stopped = False
        self.lock = threading.Lock()
        self.last_frame = None
        self.last_processed_frame = None
        self.last_plate = ""
        self.last_access_result = ""
        self.last_access_code = ""
        self.processing_interval = 2.0
        self.last_process_time = 0
        self.reconnect_delay = 5
        self.frame_count = 0

        # Инициализируем EasyOCR при создании объекта
        self.reader = get_ocr_reader()

        # Новые атрибуты для истории успешного распознавания
        self.last_successful_plate = ""
        self.last_successful_access = ""
        self.last_successful_code = ""
        self.last_successful_frame = None
        self.last_successful_time = None

        # Для хранения истории последних распознаваний
        self.recognition_history = []  # список последних 10 записей
        self.max_history = 10

    def start(self):
        """Запуск захвата видео с камеры"""
        print(f"[DEBUG] Попытка открыть камеру: {self.camera_source}")
        print(f"[DEBUG] Тип подключения: {'Сетевая' if self.use_network else 'Локальная'}")

        try:
            if self.use_network:
                # Для сетевой камеры используем URL
                self.cap = cv2.VideoCapture(self.camera_source)
            else:
                # Для локальной камеры пробуем DSHOW
                self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    print("[DEBUG] DSHOW не сработал, пробую стандартный бэкенд")
                    self.cap = cv2.VideoCapture(self.camera_source)

            if not self.cap.isOpened():
                raise RuntimeError(f"Не удалось открыть камеру: {self.camera_source}")

            print("[DEBUG] Камера успешно открыта")

            # Настройка параметров захвата
            if not self.use_network:
                self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                self.cap.set(cv2.CAP_PROP_FPS, 30)

                # Попробуем установить MJPG формат
                fourcc = cv2.VideoWriter_fourcc(*'MJPG')
                self.cap.set(cv2.CAP_PROP_FOURCC, fourcc)

            # Получаем реальные параметры
            actual_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
            print(f"[DEBUG] Реальное разрешение: {actual_w} x {actual_h}, FPS: {actual_fps}")

            self.stopped = False
            self.thread = threading.Thread(target=self._update, args=())
            self.thread.daemon = True
            self.thread.start()
            print("[DEBUG] Фоновый поток запущен")

        except Exception as e:
            print(f"[DEBUG] Ошибка при открытии камеры: {e}")
            raise

        return self

    def _update(self):
        """Фоновый поток захвата и обработки кадров"""
        print("[DEBUG] _update thread started")
        reconnect_attempts = 0

        while not self.stopped:
            try:
                if self.cap is None or not self.cap.isOpened():
                    print(f"[DEBUG] Камера не открыта, попытка переподключения {reconnect_attempts + 1}")
                    time.sleep(self.reconnect_delay)
                    self.cap = cv2.VideoCapture(self.camera_source)
                    reconnect_attempts += 1
                    continue

                ret, frame = self.cap.read()
                if not ret:
                    print("[DEBUG] Не удалось прочитать кадр")
                    time.sleep(0.1)
                    continue

                reconnect_attempts = 0
                self.frame_count += 1

                if self.frame_count % 30 == 0:
                    print(f"[DEBUG] Получено кадров: {self.frame_count}")

                # Сохраняем текущий кадр для live просмотра
                with self.lock:
                    self.last_frame = frame.copy()

                # Периодическое распознавание номеров
                current_time = time.time()
                if current_time - self.last_process_time > self.processing_interval:
                    self.last_process_time = current_time

                    # Создаем копию для обработки
                    processed_frame = frame.copy()

                    # Каждые 30 кадров запускаем тест OCR
                    if self.frame_count % 30 == 0:
                        self._test_ocr_on_frame(frame)

                    # Распознаем номер с EasyOCR
                    plate, plate_rect = self._recognize_plate_easyocr(processed_frame)

                    # Рисуем прямоугольник вокруг номера
                    if plate_rect:
                        x, y, w, h = plate_rect
                        cv2.rectangle(processed_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
                        cv2.putText(processed_frame, plate, (x, y - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                    # Добавляем информацию о распознавании на кадр
                    cv2.putText(processed_frame, f"Plate: {plate}", (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

                    # Проверяем доступ
                    access_result, access_code = self._check_access(plate)

                    # Добавляем статус доступа на кадр
                    cv2.putText(processed_frame, f"Access: {access_result}", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, self._get_color_for_code(access_code), 2)

                    # Сохраняем результаты
                    with self.lock:
                        self.last_processed_frame = processed_frame
                        self.last_plate = plate
                        self.last_access_result = access_result
                        self.last_access_code = access_code

                        # Если номер успешно распознан (не пустой)
                        if plate and access_code not in ['unrecognized', 'error']:
                            self.last_successful_plate = plate
                            self.last_successful_access = access_result
                            self.last_successful_code = access_code
                            self.last_successful_frame = processed_frame.copy()
                            self.last_successful_time = datetime.now()

                            # Добавляем в историю
                            history_entry = {
                                'plate': plate,
                                'access': access_result,
                                'code': access_code,
                                'time': datetime.now().strftime('%H:%M:%S'),
                                'date': datetime.now().strftime('%d.%m.%Y')
                            }
                            self.recognition_history.append(history_entry)
                            # Оставляем только последние max_history записей
                            if len(self.recognition_history) > self.max_history:
                                self.recognition_history = self.recognition_history[-self.max_history:]

                    print(f"[DEBUG] Распознано EasyOCR: '{plate}', Статус: {access_result}")

            except Exception as e:
                print(f"[DEBUG] Исключение в _update: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

    def _get_color_for_code(self, code):
        """Возвращает цвет BGR для статуса доступа"""
        colors = {
            'permanent': (0, 255, 0),  # зеленый
            'temporary': (0, 255, 255),  # желтый
            'denied': (0, 0, 255),  # красный
            'unrecognized': (128, 128, 128),  # серый
            'error': (255, 0, 255)  # фиолетовый
        }
        return colors.get(code, (255, 255, 255))  # белый по умолчанию

    def _test_ocr_on_frame(self, frame):
        """Тестовая функция для проверки работы EasyOCR на всём кадре"""
        try:
            # Сохраняем оригинальный кадр
            #cv2.imwrite(f'debug_full_frame_{self.frame_count}.jpg', frame)
            print(f"[DEBUG] Полный кадр {self.frame_count} сохранён")

            # Пробуем распознать текст на всём кадре
            results = self.reader.readtext(frame,
                                           allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789АВЕКМНОРСТУХ',
                                           paragraph=False)

            print(f"[DEBUG] EasyOCR тест {self.frame_count}:")
            if results:
                for bbox, text, confidence in results:
                    print(f"  Текст: '{text}', Уверенность: {confidence:.2f}")
            else:
                print("  Текст не найден")

        except Exception as e:
            print(f"[DEBUG] Ошибка в тесте OCR: {e}")

    def _find_plate_roi(self, frame):
        """Улучшенный поиск области с номером"""
        try:
            debug_frame = frame.copy()
            height, width = frame.shape[:2]

            # Конвертируем в серый
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            # Улучшаем контраст
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            gray = clahe.apply(gray)

            # Ищем градиенты
            grad_x = cv2.Sobel(gray, cv2.CV_32F, 1, 0, ksize=3)
            grad_y = cv2.Sobel(gray, cv2.CV_32F, 0, 1, ksize=3)

            # Комбинируем градиенты
            gradient = cv2.subtract(grad_x, grad_y)
            gradient = cv2.convertScaleAbs(gradient)

            # Бинаризация
            _, thresh = cv2.threshold(gradient, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

            # Морфологические операции для соединения букв
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (13, 3))
            closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)

            # Поиск контуров
            contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            # Сортируем по площади
            contours = sorted(contours, key=cv2.contourArea, reverse=True)[:20]

            candidates = []

            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)

                # Проверяем размеры
                if w < 80 or h < 20 or w > width / 2 or h > height / 3:
                    continue

                # Проверяем соотношение сторон
                aspect_ratio = w / float(h)
                if 2.0 < aspect_ratio < 5.5:
                    # Проверяем площадь
                    area_ratio = (w * h) / (width * height)
                    if 0.01 < area_ratio < 0.2:
                        candidates.append((x, y, w, h))
                        cv2.rectangle(debug_frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

            # Если нашли кандидатов, выбираем наиболее вероятный
            if candidates:
                #cv2.imwrite(f'debug_candidates_{self.frame_count}.jpg', debug_frame)
                print(f"[DEBUG] Найдено кандидатов: {len(candidates)}")

                # Берём первый (самый большой)
                x, y, w, h = candidates[0]

                # Добавляем отступ
                padding = 10
                x = max(0, x - padding)
                y = max(0, y - padding)
                w = min(width - x, w + 2 * padding)
                h = min(height - y, h + 2 * padding)

                # Вырезаем область
                roi = frame[y:y + h, x:x + w]

                return roi, (x, y, w, h)

            # Если не нашли кандидатов, берём нижнюю половину кадра
            roi_y = int(height * 0.6)
            roi_h = int(height * 0.3)
            roi = frame[roi_y:roi_y + roi_h, :]

            cv2.rectangle(debug_frame, (0, roi_y), (width, roi_y + roi_h), (255, 0, 0), 2)
            #cv2.imwrite(f'debug_fallback_{self.frame_count}.jpg', debug_frame)

            return roi, (0, roi_y, width, roi_h)

        except Exception as e:
            print(f"[DEBUG] Ошибка поиска номера: {e}")
            return None, None

    def _recognize_plate_easyocr(self, frame):
        """Распознавание номера с помощью EasyOCR"""
        try:
            # Сначала ищем область с номером
            roi, plate_rect = self._find_plate_roi(frame)

            if roi is None:
                print("[DEBUG] Область номера не найдена")
                return "", None

            # Сохраняем ROI для отладки
            #cv2.imwrite(f'debug_roi_{self.frame_count}.jpg', roi)

            # Увеличиваем ROI для лучшего распознавания
            roi = cv2.resize(roi, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

            # Улучшаем контраст
            roi_gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            roi_enhanced = clahe.apply(roi_gray)
            roi_enhanced = cv2.cvtColor(roi_enhanced, cv2.COLOR_GRAY2BGR)

            # Распознаем текст с помощью EasyOCR
            # Разрешенные символы: буквы и цифры, используемые в номерах
            results = self.reader.readtext(roi_enhanced,
                                           allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                                           paragraph=False,
                                           width_ths=0.7,
                                           height_ths=0.5)

            if results:
                # Сортируем по уверенности и берем лучший результат
                results.sort(key=lambda x: x[2], reverse=True)
                best_text = results[0][1]
                confidence = results[0][2]

                # Очищаем результат
                plate = re.sub(r'[^A-Z0-9А-Я]', '', best_text).strip()

                print(f"[DEBUG] EasyOCR: '{plate}' (уверенность: {confidence:.2f})")
                return plate, plate_rect
            else:
                print("[DEBUG] EasyOCR: текст не найден")
                return "", plate_rect

        except Exception as e:
            print(f"[DEBUG] Ошибка распознавания EasyOCR: {e}")
            import traceback
            traceback.print_exc()
            return "", None

    def _check_access(self, plate):
        """Проверка доступа по номеру с обработкой ошибок БД"""
        if not plate:
            return "Номер не распознан, ручной доступ", "unrecognized"

        try:
            try:
                lp = LicensePlate.objects.get(plate_number=plate)
            except LicensePlate.DoesNotExist:
                return "Доступ запрещён", "denied"
            except Exception as db_error:
                print(f"[DEBUG] Ошибка БД при поиске номера: {db_error}")
                return "Ошибка базы данных", "error"

            # Ищем действующий пропуск
            try:
                passes = Pass.objects.filter(
                    license_plate=lp,
                    start_date__lte=datetime.now().date()
                )
            except Exception as db_error:
                print(f"[DEBUG] Ошибка БД при поиске пропуска: {db_error}")
                return "Ошибка базы данных", "error"

            if not passes.exists():
                return "Доступ запрещён (нет пропуска)", "denied"

            p = passes.first()
            if p.pass_type == 'permanent':
                return "Постоянный, Въезд разрешён", "permanent"
            else:  # temporary
                if p.end_date and p.end_date >= datetime.now().date():
                    return "Временный, ручной контроль", "temporary"
                else:
                    return "Доступ запрещён (просрочен)", "denied"

        except Exception as e:
            print(f"[DEBUG] Непредвиденная ошибка в _check_access: {e}")
            import traceback
            traceback.print_exc()
            return "Ошибка проверки доступа", "error"

    def get_frame(self):
        """Получение текущего кадра для live просмотра"""
        with self.lock:
            if self.last_frame is None:
                return None
            ret, jpeg = cv2.imencode('.jpg', self.last_frame)
            if not ret:
                print("[DEBUG] Ошибка кодирования JPEG")
                return None
            return jpeg.tobytes()

    def get_processed_frame(self):
        """Получение последнего обработанного кадра"""
        with self.lock:
            if self.last_processed_frame is None:
                return None
            ret, jpeg = cv2.imencode('.jpg', self.last_processed_frame)
            return jpeg.tobytes()

    def get_status(self):
        """Получение статуса последнего распознавания"""
        with self.lock:
            return {
                'plate': self.last_plate,
                'access': self.last_access_result,
                'code': self.last_access_code
            }

    def get_last_successful(self):
        """Получить данные последнего успешного распознавания"""
        with self.lock:
            if self.last_successful_frame is None:
                return None
            ret, jpeg = cv2.imencode('.jpg', self.last_successful_frame)
            if not ret:
                return None
            return {
                'frame': jpeg.tobytes(),
                'plate': self.last_successful_plate,
                'access': self.last_successful_access,
                'code': self.last_successful_code,
                'time': self.last_successful_time.strftime('%H:%M:%S') if self.last_successful_time else None
            }

    def get_recognition_history(self):
        """Получить историю распознаваний"""
        with self.lock:
            return self.recognition_history.copy()

    def stop(self):
        """Остановка захвата видео"""
        self.stopped = True
        if self.cap:
            self.cap.release()
        print("[DEBUG] Камера остановлена")
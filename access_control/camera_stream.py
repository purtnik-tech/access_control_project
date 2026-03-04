import threading
import time
import cv2
import re
import easyocr
import torch
import os
from datetime import datetime
from ultralytics import YOLO
from huggingface_hub import hf_hub_download
from .models import LicensePlate, Pass

# Константы для российских номеров
RUSSIAN_LETTERS = 'АВЕКМНОРСТУХ'  # Буквы, используемые в российских номерах
ALLOWED_CHARS = RUSSIAN_LETTERS + '0123456789'


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
        self.last_plate_full = ""  # Полный номер с регионом
        self.last_plate_main = ""  # Основная часть номера (без региона)
        self.last_plate_region = ""  # Только регион
        self.last_access_result = ""
        self.last_access_code = ""
        self.processing_interval = 2.0  # Интервал распознавания (секунды)
        self.last_process_time = 0
        self.reconnect_delay = 5
        self.frame_count = 0

        # Порог уверенности для записи в историю
        self.confidence_threshold = 0.7  # Номера с уверенностью ниже этого не записываются
        self.min_plate_length = 6  # Минимальная длина номера (A123BC = 6 символов)
        self.max_plate_length = 9  # Максимальная длина (A123BC45 = 8, A123BC456 = 9)

        # Инициализация YOLO для детекции номеров
        self._init_yolo_model()

        # Инициализация EasyOCR для распознавания
        self._init_easyocr()

        # Атрибуты для истории успешного распознавания
        self.last_successful_plate = ""
        self.last_successful_plate_full = ""
        self.last_successful_access = ""
        self.last_successful_code = ""
        self.last_successful_frame = None
        self.last_successful_time = None

        # Для хранения истории последних распознаваний
        self.recognition_history = []  # список последних 10 записей
        self.max_history = 10

    def _init_yolo_model(self):
        """Инициализация YOLO модели для детекции номеров"""
        try:
            print("[DEBUG] Загрузка YOLO модели для детекции номеров...")

            # Скачиваем специализированную модель для номеров с Hugging Face
            model_path = hf_hub_download(
                repo_id="0xnu/european-license-plate-recognition",
                filename="yolov12n_plate_detection.pt",
                repo_type="model"
            )

            # Загружаем модель YOLO
            self.detector = YOLO(model_path)

            # Определяем устройство (GPU если доступно)
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            print(f"[DEBUG] YOLO модель загружена. Устройство: {self.device}")

            if self.device == 'cuda':
                self.detector.to('cuda')

        except Exception as e:
            print(f"[DEBUG] Ошибка загрузки YOLO модели: {e}")
            print("[DEBUG] Загружаю стандартную модель YOLOv8n...")
            self.detector = YOLO('yolov8n.pt')
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

    def _init_easyocr(self):
        """Инициализация EasyOCR для распознавания текста"""
        try:
            print("[DEBUG] Инициализация EasyOCR...")
            gpu = True if torch.cuda.is_available() else False
            self.reader = easyocr.Reader(
                ['ru', 'en'],
                gpu=gpu,
                model_storage_directory='~/.easyocr/model',
                download_enabled=True
            )
            print(f"[DEBUG] EasyOCR инициализирован. GPU: {gpu}")
        except Exception as e:
            print(f"[DEBUG] Ошибка инициализации EasyOCR: {e}")
            self.reader = None

    def start(self):
        """Запуск захвата видео с камеры с улучшенной обработкой RTSP"""
        print(f"[DEBUG] Попытка открыть камеру: {self.camera_source}")
        print(f"[DEBUG] Тип подключения: {'Сетевая' if self.use_network else 'Локальная'}")

        try:
            if self.use_network:
                # Расширенные параметры для RTSP
                rtsp_params = (
                    "rtsp_transport;tcp|"  # TCP надежнее UDP
                    "max_delay;0|"  # Минимальная задержка
                    "buffer_size;1024000|"  # Буфер 1MB
                    "reorder_queue_size;0|"  # Не переупорядочивать кадры
                    "fflags;nobuffer|"  # Отключить буферизацию
                    "flags;low_delay|"  # Низкая задержка
                    "timeout;5000000|"  # Таймаут 5 секунд (в микросекундах)
                    "stimeout;5000000"  # Таймаут сокета 5 секунд
                )
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = rtsp_params

                # Пробуем разные бэкенды
                backends = [
                    (cv2.CAP_FFMPEG, "FFMPEG"),
                    (cv2.CAP_ANY, "ANY"),
                    (None, "DEFAULT")
                ]

                for backend, name in backends:
                    try:
                        if backend is not None:
                            print(f"[DEBUG] Пробую бэкенд: {name}")
                            self.cap = cv2.VideoCapture(self.camera_source, backend)
                        else:
                            print(f"[DEBUG] Пробую бэкенд: DEFAULT")
                            self.cap = cv2.VideoCapture(self.camera_source)

                        if self.cap.isOpened():
                            print(f"[DEBUG] Бэкенд {name} успешно открыл камеру")
                            break
                    except Exception as e:
                        print(f"[DEBUG] Бэкенд {name} не сработал: {e}")
                        continue

                if not self.cap or not self.cap.isOpened():
                    raise RuntimeError("Не удалось открыть камеру ни одним бэкендом")

                # Устанавливаем параметры для стабильной работы
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Минимальный буфер
                self.cap.set(cv2.CAP_PROP_FPS, 15)  # Ограничиваем FPS для стабильности

                # Устанавливаем таймаут чтения
                self.cap.set(cv2.CAP_PROP_OPEN_TIMEOUT_MSEC, 5000)  # 5 секунд
                self.cap.set(cv2.CAP_PROP_READ_TIMEOUT_MSEC, 5000)  # 5 секунд

            else:
                # Для локальной камеры
                self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    print("[DEBUG] DSHOW не сработал, пробую стандартный бэкенд")
                    self.cap = cv2.VideoCapture(self.camera_source)

            if not self.cap.isOpened():
                raise RuntimeError(f"Не удалось открыть камеру: {self.camera_source}")

            print("[DEBUG] Камера успешно открыта")

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
        """Фоновый поток захвата и обработки кадров с улучшенной обработкой RTSP"""
        print("[DEBUG] _update thread started")
        reconnect_attempts = 0
        consecutive_errors = 0
        max_consecutive_errors = 5
        last_reconnect_time = 0
        reconnect_cooldown = 10  # Минимальное время между переподключениями (секунд)

        while not self.stopped:
            try:
                current_time = time.time()

                # Проверка состояния камеры
                if self.cap is None or not self.cap.isOpened():
                    # Проверяем, не слишком ли часто пытаемся переподключиться
                    if current_time - last_reconnect_time < reconnect_cooldown:
                        time.sleep(1)
                        continue

                    print(f"[DEBUG] Камера не открыта, попытка переподключения {reconnect_attempts + 1}")
                    last_reconnect_time = current_time

                    # Экспоненциальная задержка между попытками
                    delay = min(30, 5 * (reconnect_attempts + 1))
                    print(f"[DEBUG] Ожидание {delay} секунд перед переподключением...")
                    time.sleep(delay)

                    # Пробуем переподключиться
                    if self.use_network:
                        # Восстанавливаем параметры RTSP
                        rtsp_params = (
                            "rtsp_transport;tcp|"
                            "max_delay;0|"
                            "buffer_size;1024000|"
                            "reorder_queue_size;0|"
                            "fflags;nobuffer|"
                            "flags;low_delay|"
                            "timeout;5000000|"
                            "stimeout;5000000"
                        )
                        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = rtsp_params

                        self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_FFMPEG)
                        if self.cap.isOpened():
                            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                            self.cap.set(cv2.CAP_PROP_FPS, 15)
                            print("[DEBUG] Переподключение успешно")
                            reconnect_attempts = 0
                        else:
                            reconnect_attempts += 1
                    else:
                        self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
                        if self.cap.isOpened():
                            print("[DEBUG] Переподключение успешно")
                            reconnect_attempts = 0
                        else:
                            reconnect_attempts += 1

                    continue

                # Читаем кадр с таймаутом
                ret, frame = self.cap.read()

                if not ret:
                    consecutive_errors += 1
                    print(f"[DEBUG] Не удалось прочитать кадр (ошибка #{consecutive_errors})")

                    if consecutive_errors > max_consecutive_errors:
                        print("[DEBUG] Слишком много ошибок, переподключаюсь...")
                        self.cap.release()
                        self.cap = None
                        consecutive_errors = 0

                    time.sleep(0.5)
                    continue

                # Сброс счетчиков при успешном чтении
                consecutive_errors = 0
                self.frame_count += 1

                if self.frame_count % 30 == 0:
                    print(f"[DEBUG] Получено кадров: {self.frame_count}")

                # Сохраняем текущий кадр для live просмотра
                with self.lock:
                    self.last_frame = frame.copy()

                # Периодическое распознавание номеров
                if current_time - self.last_process_time > self.processing_interval:
                    self.last_process_time = current_time

                    # Создаем копию для обработки
                    processed_frame = frame.copy()

                    # Распознаем номер с помощью YOLO + EasyOCR
                    plate_info = self._recognize_plate_yolo_easyocr(processed_frame)

                    # Извлекаем компоненты номера
                    plate_full = plate_info.get('full', '')
                    plate_main = plate_info.get('main', '')
                    plate_region = plate_info.get('region', '')
                    confidence = plate_info.get('confidence', 0.0)
                    plate_rect = plate_info.get('bbox', None)

                    # Проверяем доступ
                    access_result, access_code = self._check_access(plate_full, plate_main)

                    # Определяем, нужно ли записывать в историю
                    record_to_history = self._should_record_to_history(
                        plate_info, confidence, access_code
                    )

                    # Рисуем прямоугольник вокруг номера и информацию
                    if plate_rect:
                        x1, y1, x2, y2 = plate_rect
                        # Рисуем прямоугольник (зеленый если доступ разрешен, красный если запрещен)
                        rect_color = (0, 255, 0) if access_code in ['permanent', 'temporary'] else (0, 0, 255)
                        cv2.rectangle(processed_frame, (x1, y1), (x2, y2), rect_color, 3)

                        # Добавляем информацию о номере
                        if plate_full:
                            # Показываем уверенность и статус записи
                            record_flag = "✓" if record_to_history else "✗"
                            info_text = f"Plate: {plate_full} ({confidence:.2f}) {record_flag}"
                            cv2.putText(processed_frame, info_text, (x1, y1 - 10),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, rect_color, 2)

                            # Добавляем основную часть и регион отдельно
                            debug_text = f"Main: {plate_main}, Region: {plate_region}"
                            cv2.putText(processed_frame, debug_text, (x1, y2 + 20),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 0), 1)

                    # Добавляем статус доступа на кадр
                    status_color = self._get_color_for_code(access_code)
                    cv2.putText(processed_frame, f"Access: {access_result}", (10, 60),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, status_color, 2)

                    # Добавляем время распознавания
                    cv2.putText(processed_frame, datetime.now().strftime('%H:%M:%S'), (10, 30),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)

                    # Добавляем информацию о записи в историю
                    if record_to_history:
                        cv2.putText(processed_frame, "✓ Saved to history", (10, 90),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

                    # Сохраняем результаты
                    with self.lock:
                        self.last_processed_frame = processed_frame
                        self.last_plate_full = plate_full
                        self.last_plate_main = plate_main
                        self.last_plate_region = plate_region
                        self.last_plate = plate_full
                        self.last_access_result = access_result
                        self.last_access_code = access_code

                        # Если номер успешно распознан И должен быть записан в историю
                        if plate_full and record_to_history:
                            # Обновляем последний успешный
                            self.last_successful_plate = plate_full
                            self.last_successful_plate_full = plate_full
                            self.last_successful_access = access_result
                            self.last_successful_code = access_code
                            self.last_successful_frame = processed_frame.copy()
                            self.last_successful_time = datetime.now()

                            # Добавляем в историю
                            history_entry = {
                                'plate': plate_full,
                                'plate_main': plate_main,
                                'plate_region': plate_region,
                                'access': access_result,
                                'code': access_code,
                                'confidence': round(confidence, 2),
                                'time': datetime.now().strftime('%H:%M:%S'),
                                'date': datetime.now().strftime('%d.%m.%Y')
                            }
                            self.recognition_history.append(history_entry)
                            # Оставляем только последние max_history записей
                            if len(self.recognition_history) > self.max_history:
                                self.recognition_history = self.recognition_history[-self.max_history:]

                            print(f"[DEBUG] ✅ ЗАПИСАН: {plate_full} (увер:{confidence:.2f}, стат:{access_code})")
                        else:
                            if plate_full:
                                print(f"[DEBUG] ❌ НЕ ЗАПИСАН: {plate_full} (увер:{confidence:.2f}, стат:{access_code})")

            except Exception as e:
                print(f"[DEBUG] Исключение в _update: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(1)

    def _get_color_for_code(self, code):
        """Возвращает цвет BGR для статуса доступа"""
        colors = {
            'permanent': (0, 255, 0),
            'temporary': (0, 255, 255),
            'denied': (0, 0, 255),
            'unrecognized': (128, 128, 128),
            'error': (255, 0, 255)
        }
        return colors.get(code, (255, 255, 255))

    def _is_valid_russian_plate(self, plate_info):
        """Проверяет валидность российского номера"""
        main_part = plate_info.get('main', '')
        region = plate_info.get('region', '')
        full = plate_info.get('full', '')

        # Проверка длины
        if len(full) < self.min_plate_length or len(full) > self.max_plate_length:
            return False

        # Проверка формата основной части (буква + 3 цифры + 2 буквы)
        main_pattern = r'^([' + RUSSIAN_LETTERS + r'])(\d{3})([' + RUSSIAN_LETTERS + r']{2})$'
        if not re.match(main_pattern, main_part):
            return False

        # Проверка региона (2 или 3 цифры)
        if region and not re.match(r'^\d{2,3}$', region):
            return False

        # Проверка, что основная часть не содержит только цифр или только букв
        if main_part.isdigit() or main_part.isalpha():
            return False

        return True

    def _should_record_to_history(self, plate_info, confidence, access_code):
        """Определяет, нужно ли записывать номер в историю"""
        # Не записываем если уверенность ниже порога
        if confidence < self.confidence_threshold:
            return False

        # Не записываем если доступ запрещён
        if access_code in ['denied', 'unrecognized', 'error']:
            return False

        # Проверяем валидность номера
        if not self._is_valid_russian_plate(plate_info):
            return False

        return True

    def _parse_russian_plate(self, text):
        """
        Парсит российский номер формата:
        - A123BC45 (2-значный регион)
        - A123BC456 (3-значный регион)
        - А798АР177 (пример из лога)
        """
        # Удаляем все пробелы и спецсимволы
        clean_text = re.sub(r'[^A-Z0-9А-Я]', '', text).upper()

        if not clean_text or len(clean_text) < 6:
            return {'full': '', 'main': '', 'region': ''}

        print(f"[DEBUG] Парсинг текста: '{clean_text}'")

        # Паттерн для основной части номера (буква + 3 цифры + 2 буквы)
        # Буквы только из разрешённого набора АВЕКМНОРСТУХ
        main_pattern = r'([' + RUSSIAN_LETTERS + r'])(\d{3})([' + RUSSIAN_LETTERS + r']{2})'
        main_match = re.search(main_pattern, clean_text)

        if main_match:
            main_part = main_match.group(0)  # A123BC
            main_start = main_match.start()
            main_end = main_match.end()

            print(f"[DEBUG] Найдена основная часть: '{main_part}' (позиция {main_start}-{main_end})")

            # Ищем регион после основной части (2 или 3 цифры)
            remaining = clean_text[main_end:]
            region_match = re.search(r'(\d{2,3})', remaining)

            if region_match:
                region = region_match.group(0)
                full_plate = main_part + region
                print(f"[DEBUG] Найден регион: '{region}', полный номер: '{full_plate}'")
                return {
                    'full': full_plate,
                    'main': main_part,
                    'region': region
                }
            else:
                # Если регион не найден отдельно, пробуем извлечь из конца всей строки
                # Ищем 2-3 цифры в конце
                full_pattern = r'(' + main_pattern + r')(\d{2,3})$'
                full_match = re.search(full_pattern, clean_text)
                if full_match:
                    result = {
                        'full': full_match.group(0),
                        'main': full_match.group(1),
                        'region': full_match.group(5)
                    }
                    print(f"[DEBUG] Найден полный номер (из конца): '{result['full']}'")
                    return result
                else:
                    # Только основная часть без региона
                    print(f"[DEBUG] Только основная часть без региона: '{main_part}'")
                    return {
                        'full': main_part,
                        'main': main_part,
                        'region': ''
                    }

        # Если не нашли по паттерну, пробуем альтернативный подход
        # Например, если текст содержит буквы и цифры в правильном порядке
        # Извлекаем все буквы и цифры
        letters = re.findall(r'[' + RUSSIAN_LETTERS + r']', clean_text)
        digits = re.findall(r'\d', clean_text)

        print(f"[DEBUG] Альтернативный парсинг - буквы: {letters}, цифры: {digits}")

        # Для российского номера нужно: 3 буквы и 3-6 цифр (3 в основной + 2-3 регион)
        if len(letters) >= 3 and len(digits) >= 5:
            # Пробуем собрать номер вручную
            # Первая буква, 3 цифры, 2 буквы, 2-3 цифры региона
            potential_main = letters[0] + ''.join(digits[:3]) + ''.join(letters[1:3])
            potential_region = ''.join(digits[3:5]) if len(digits) >= 5 else ''

            if len(digits) >= 6:
                potential_region = ''.join(digits[3:6])

            if re.match(main_pattern, potential_main):
                result = {
                    'full': potential_main + potential_region,
                    'main': potential_main,
                    'region': potential_region
                }
                print(f"[DEBUG] Собран номер вручную: '{result['full']}'")
                return result

        # Если ничего не нашли, возвращаем как есть
        print(f"[DEBUG] Не удалось распарсить, возвращаю как есть: '{clean_text}'")
        return {
            'full': clean_text,
            'main': clean_text,
            'region': ''
        }

    def _recognize_plate_yolo_easyocr(self, frame):
        """
        Детекция номера с помощью YOLO и распознавание с помощью EasyOCR
        Улучшенная версия с более агрессивной предобработкой
        """
        result = {
            'full': '',
            'main': '',
            'region': '',
            'confidence': 0.0,
            'bbox': None
        }

        try:
            # 1. Детекция номера с помощью YOLO
            results = self.detector(frame, conf=0.3, verbose=False)

            best_plate_info = None
            best_bbox = None
            best_confidence = 0.0

            for result_item in results:
                boxes = result_item.boxes
                if boxes is not None and len(boxes) > 0:
                    for box in boxes:
                        # Координаты bounding box
                        x1, y1, x2, y2 = map(int, box.xyxy[0])

                        # Уверенность детекции
                        detection_conf = float(box.conf[0])

                        # Вырезаем область с номером
                        plate_crop = frame[y1:y2, x1:x2]

                        if plate_crop.size == 0:
                            continue

                        # Сохраняем оригинал для отладки
                        #cv2.imwrite(f'debug_plate_orig_{self.frame_count}.jpg', plate_crop)

                        # Улучшенная предобработка для распознавания

                        # 1. Увеличиваем размер
                        plate_crop = cv2.resize(plate_crop, None, fx=3, fy=3,
                                                interpolation=cv2.INTER_CUBIC)

                        # 2. Конвертируем в灰度
                        plate_gray = cv2.cvtColor(plate_crop,
                                                  cv2.COLOR_BGR2GRAY)

                        # 3. Улучшаем контраст (CLAHE)
                        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
                        plate_enhanced = clahe.apply(plate_gray)

                        # 4. Применяем бинаризацию
                        _, plate_binary = cv2.threshold(plate_enhanced, 0, 255,
                                                        cv2.THRESH_BINARY + cv2.THRESH_OTSU)

                        # 5. Убираем шум
                        plate_denoised = cv2.medianBlur(plate_binary, 3)

                        # Сохраняем обработанное изображение для отладки
                        #cv2.imwrite(f'debug_plate_processed_{self.frame_count}.jpg', plate_denoised)

                        # 2. Распознавание текста EasyOCR
                        if self.reader:
                            # Пробуем распознать на оригинальном изображении
                            results_orig = self.reader.readtext(
                                plate_crop,
                                allowlist=ALLOWED_CHARS,
                                paragraph=False,
                                width_ths=0.7,
                                height_ths=0.5,
                                low_text=0.3,  # Уменьшаем порог для поиска текста
                                text_threshold=0.5  # Уменьшаем порог уверенности
                            )

                            # Пробуем распознать на обработанном изображении
                            results_processed = self.reader.readtext(
                                plate_denoised,
                                allowlist=ALLOWED_CHARS,
                                paragraph=False,
                                width_ths=0.7,
                                height_ths=0.5,
                                low_text=0.3,
                                text_threshold=0.5
                            )

                            # Объединяем результаты
                            all_results = results_orig + results_processed

                            if all_results:
                                # Группируем результаты по позициям
                                all_results.sort(key=lambda x: x[0][0][0])  # Сортируем по x координате

                                full_text = ""
                                total_conf = 0
                                valid_results = []

                                for ocr_item in all_results:
                                    text = ocr_item[1]
                                    conf = ocr_item[2]

                                    # Фильтруем по длине и содержанию
                                    if len(text) >= 2 and any(c.isdigit() for c in text):
                                        valid_results.append(ocr_item)
                                        full_text += text
                                        total_conf += conf

                                if valid_results:
                                    avg_conf = total_conf / len(valid_results)

                                    # Парсим российский номер
                                    plate_info = self._parse_russian_plate(full_text)

                                    # Комбинированная уверенность
                                    combined_conf = detection_conf * avg_conf

                                    # Бонус за наличие и основной части, и региона
                                    if plate_info['main'] and plate_info['region']:
                                        combined_conf *= 1.2  # Увеличиваем уверенность
                                        combined_conf = min(combined_conf, 1.0)  # Но не больше 1.0

                                    if plate_info['full'] and combined_conf > best_confidence:
                                        best_confidence = combined_conf
                                        best_bbox = (x1, y1, x2, y2)
                                        best_plate_info = plate_info

                                        print(f"[DEBUG] Кандидат: {plate_info['full']} "
                                              f"(увер:{combined_conf:.2f}, "
                                              f"детекция:{detection_conf:.2f}, "
                                              f"распознавание:{avg_conf:.2f})")

            if best_plate_info and best_confidence > 0:
                result.update({
                    'full': best_plate_info['full'],
                    'main': best_plate_info['main'],
                    'region': best_plate_info['region'],
                    'confidence': best_confidence,
                    'bbox': best_bbox
                })
                print(f"[DEBUG] Лучший результат: {best_plate_info['full']} "
                      f"(увер:{best_confidence:.2f})")

            return result

        except Exception as e:
            print(f"[DEBUG] Ошибка в YOLO+EasyOCR: {e}")
            import traceback
            traceback.print_exc()
            return result

    def _check_access(self, plate_full, plate_main):
        """
        Проверка доступа по номеру
        Сначала проверяет полный номер (с регионом), затем только основную часть
        """
        if not plate_full and not plate_main:
            return "Номер не распознан, ручной доступ", "unrecognized"

        print(f"[DEBUG] Проверка доступа: полный='{plate_full}', основная='{plate_main}'")

        # Функция для нормализации номера (удаление лишних символов)
        def normalize_plate(plate):
            if not plate:
                return ""
            return re.sub(r'[^A-Z0-9А-Я]', '', plate).upper()

        # Сначала проверяем полный номер (с регионом)
        if plate_full:
            normalized_full = normalize_plate(plate_full)
            print(f"[DEBUG] Поиск полного номера: '{normalized_full}'")

            try:
                # Ищем точное совпадение
                lp = LicensePlate.objects.get(plate_number=normalized_full)
                print(f"[DEBUG] Найден полный номер в БД: {lp.plate_number}")
                return self._check_pass_for_plate(lp)
            except LicensePlate.DoesNotExist:
                print(f"[DEBUG] Полный номер '{normalized_full}' не найден в БД")

                # Если полный номер не найден, пробуем только основную часть
                if plate_main and plate_main != plate_full:
                    normalized_main = normalize_plate(plate_main)
                    print(f"[DEBUG] Поиск основной части: '{normalized_main}'")

                    try:
                        lp = LicensePlate.objects.get(plate_number=normalized_main)
                        print(f"[DEBUG] Найдена основная часть в БД: {lp.plate_number}")
                        return self._check_pass_for_plate(lp)
                    except LicensePlate.DoesNotExist:
                        print(f"[DEBUG] Основная часть '{normalized_main}' не найдена в БД")
                        return "Доступ запрещён", "denied"
                return "Доступ запрещён", "denied"
            except Exception as db_error:
                print(f"[DEBUG] Ошибка БД при поиске полного номера: {db_error}")
                return "Ошибка базы данных", "error"

        # Проверяем только основную часть
        if plate_main:
            normalized_main = normalize_plate(plate_main)
            print(f"[DEBUG] Поиск только основной части: '{normalized_main}'")

            try:
                lp = LicensePlate.objects.get(plate_number=normalized_main)
                print(f"[DEBUG] Найдена основная часть в БД: {lp.plate_number}")
                return self._check_pass_for_plate(lp)
            except LicensePlate.DoesNotExist:
                print(f"[DEBUG] Основная часть '{normalized_main}' не найдена в БД")
                return "Доступ запрещён", "denied"
            except Exception as db_error:
                print(f"[DEBUG] Ошибка БД при поиске основной части: {db_error}")
                return "Ошибка базы данных", "error"

        return "Доступ запрещён", "denied"

    def _check_pass_for_plate(self, license_plate):
        """Проверяет наличие действующего пропуска для данного номерного знака"""
        try:
            passes = Pass.objects.filter(
                license_plate=license_plate,
                start_date__lte=datetime.now().date()
            )

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
            print(f"[DEBUG] Ошибка при проверке пропуска: {e}")
            return "Ошибка проверки доступа", "error"

    def get_frame(self):
        """Получение текущего кадра для live просмотра"""
        with self.lock:
            if self.last_frame is None:
                return None
            ret, jpeg = cv2.imencode('.jpg', self.last_frame)
            if not ret:
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
                'plate': self.last_plate_full,
                'plate_main': self.last_plate_main,
                'plate_region': self.last_plate_region,
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
                'plate': self.last_successful_plate_full,
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
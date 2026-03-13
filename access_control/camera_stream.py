"""
Модуль для потоковой обработки видео с камеры и распознавания автомобильных номеров.
Реализует многопоточный захват кадров, их обработку с помощью YOLO и EasyOCR,
а также проверку доступа по базе данных.
"""

import threading
import time
import cv2
import re
import easyocr
import torch
import os
import numpy as np
import queue
import gc
from datetime import datetime
from typing import Optional, Dict, List, Tuple, Any, Union
from ultralytics import YOLO
from .models import LicensePlate, Pass

# Константы для российских номеров
RUSSIAN_LETTERS: str = 'АВЕКМНОРСТУХ'  # Допустимые буквы в российских номерах
ALLOWED_CHARS: str = RUSSIAN_LETTERS + '0123456789'  # Все допустимые символы


class CameraStream:
    """
    Класс для управления видеопотоком с камеры и распознавания номеров.
    Реализует многопоточную обработку с ограничением количества потоков.
    """

    def __init__(self, camera_source: Union[int, str] = 0, use_network: bool = False,
                 camera_id: Optional[int] = None) -> None:
        """
        Инициализация потока камеры.

        Args:
            camera_source: Источник видео (индекс для USB камеры или URL для сетевой)
            use_network: True если используется сетевая камера (RTSP)
            camera_id: Устаревший параметр для обратной совместимости
        """
        # Определяем источник камеры (для обратной совместимости)
        if camera_id is not None:
            self.camera_source: Union[int, str] = camera_id
            self.use_network: bool = False
        else:
            self.camera_source = camera_source
            self.use_network = use_network

        # Состояние камеры и потока
        self.cap: Optional[cv2.VideoCapture] = None  # Объект захвата видео
        self.stopped: bool = False  # Флаг остановки потока
        self.lock: threading.Lock = threading.Lock()  # Блокировка для потокобезопасности

        # Хранение кадров
        self.last_frame: Optional[np.ndarray] = None  # Последний сырой кадр
        self.last_processed_frame: Optional[np.ndarray] = None  # Последний обработанный кадр

        # Результаты последнего распознавания
        self.last_plate_full: str = ""  # Полный номер с регионом
        self.last_plate_main: str = ""  # Основная часть номера
        self.last_plate_region: str = ""  # Код региона
        self.last_access_result: str = ""  # Текстовый результат доступа
        self.last_access_code: str = ""  # Код доступа (permanent/temporary/denied)

        # Параметры обработки
        self.processing_interval: float = 3.0  # Интервал между обработками (сек)
        self.last_process_time: float = 0  # Время последней обработки
        self.reconnect_delay: int = 3  # Задержка перед переподключением (сек)
        self.frame_count: int = 0  # Счетчик кадров

        # Параметры распознавания
        self.confidence_threshold: float = 0.05  # Минимальная уверенность для записи
        self.min_plate_length: int = 6  # Минимальная длина номера
        self.max_plate_length: int = 9  # Максимальная длина номера

        # === Управление потоками ===
        self.max_workers: int = 6  # Максимальное количество параллельных потоков
        self.active_workers: int = 0  # Текущее количество активных воркеров
        self.worker_lock: threading.Lock = threading.Lock()  # Блокировка для счетчика воркеров
        self.worker_semaphore: threading.Semaphore = threading.Semaphore(self.max_workers)  # Семафор для ограничения

        # Очередь задач для воркеров
        self.task_queue: queue.Queue = queue.Queue(maxsize=20)  # Очередь кадров на обработку
        self.worker_threads: List[threading.Thread] = []  # Список потоков-воркеров

        # Инициализация моделей
        self._init_yolo_model()
        self._init_easyocr()

        # Данные для успешных распознаваний
        self.last_successful_plate: str = ""  # Последний успешный номер
        self.last_successful_plate_full: str = ""  # Полный последний успешный номер
        self.last_successful_access: str = ""  # Статус последнего успешного доступа
        self.last_successful_code: str = ""  # Код последнего успешного доступа
        self.last_successful_frame: Optional[np.ndarray] = None  # Кадр с последним успешным распознаванием
        self.last_successful_time: Optional[datetime] = None  # Время последнего успешного распознавания

        # История распознаваний
        self.recognition_history: List[Dict[str, Any]] = []  # История всех распознаваний
        self.max_history: int = 20  # Максимальный размер истории

        # Очередь обработанных кадров для отображения
        self.processing_queue: List[Dict[str, Any]] = []  # Очередь последних обработанных кадров
        self.max_queue_size: int = 20  # Максимальный размер очереди

        # Текущий обрабатываемый кадр
        self.current_processing_frame: Optional[np.ndarray] = None  # Кадр в обработке
        self.current_processing_plate: str = ""  # Номер на текущем кадре
        self.current_processing_access: str = ""  # Статус текущего кадра
        self.current_processing_code: str = "processing"  # Код статуса текущего кадра

        # Статус камеры
        self.camera_status: str = "initializing"  # Статус: initializing/ok/error/reconnecting
        self.last_frame_time: float = 0  # Время последнего полученного кадра
        self.frame_timeout: int = 10  # Таймаут без кадров (сек)

        # Статистика
        self.stats: Dict[str, int] = {
            'total_processed': 0,  # Всего обработано кадров
            'successful': 0,  # Успешных распознаваний
            'permanent': 0,  # Постоянный доступ
            'temporary': 0,  # Временный доступ
            'denied': 0  # Отказов в доступе
        }

    def _init_yolo_model(self) -> None:
        """
        Инициализация модели YOLO для детекции номеров.
        Загружает YOLOv8m или fallback на YOLOv8n при ошибке.
        """
        try:
            model_name: str = 'yolov8m.pt'
            print(f"[INFO] Загрузка модели {model_name}...")
            self.detector: YOLO = YOLO(model_name)
            self.device: str = 'cuda' if torch.cuda.is_available() else 'cpu'

            if self.device == 'cuda':
                self.detector.to('cuda')
                print(f"[INFO] Модель загружена на GPU")
                torch.cuda.empty_cache()  # Очищаем кэш после загрузки
            else:
                print(f"[INFO] Модель загружена на CPU")

        except Exception as e:
            print(f"[ERROR] Ошибка загрузки YOLO: {e}")
            print(f"[INFO] Загружаю fallback модель YOLOv8n")
            self.detector = YOLO('yolov8n.pt')
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'

    def _init_easyocr(self) -> None:
        """
        Инициализация EasyOCR для распознавания текста на номерах.
        Поддерживает русский и английский языки.
        """
        try:
            gpu: bool = True if torch.cuda.is_available() else False
            self.reader: easyocr.Reader = easyocr.Reader(
                ['ru', 'en'],
                gpu=gpu,
                model_storage_directory='~/.easyocr/model',
                download_enabled=True,
                verbose=False
            )
            print(f"[INFO] EasyOCR инициализирован ({'GPU' if gpu else 'CPU'})")
        except Exception as e:
            print(f"[ERROR] Ошибка инициализации EasyOCR: {e}")
            self.reader = None

    def start(self) -> 'CameraStream':
        """
        Запуск захвата видео с камеры и потоков обработки.

        Returns:
            CameraStream: Ссылка на себя для цепочки вызовов

        Raises:
            RuntimeError: Если не удалось открыть камеру
        """
        try:
            if self.use_network:
                # Для сетевой камеры пробуем разные параметры подключения
                if 'OPENCV_FFMPEG_CAPTURE_OPTIONS' in os.environ:
                    del os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS']

                print(f"[INFO] Попытка открыть камеру: {self.camera_source}")

                # Попытка 1: Без параметров
                print(f"[INFO] Пробую: Без параметров")
                self.cap = cv2.VideoCapture(self.camera_source)

                # Попытка 2: TCP транспорт
                if not self.cap.isOpened():
                    print(f"[INFO] Пробую: TCP")
                    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;5000000|stimeout;5000000"
                    self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_FFMPEG)

                # Попытка 3: UDP транспорт
                if not self.cap.isOpened():
                    print(f"[INFO] Пробую: UDP")
                    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp|timeout;5000000|stimeout;5000000"
                    self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_FFMPEG)
            else:
                # Для локальной USB камеры
                self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
                if not self.cap.isOpened():
                    self.cap = cv2.VideoCapture(self.camera_source)

            if not self.cap.isOpened():
                self.camera_status = "error"
                raise RuntimeError("Не удалось открыть камеру")

            # Настройка параметров захвата для стабильности
            self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # Минимальный буфер
            self.cap.set(cv2.CAP_PROP_FPS, 10)  # Ограничиваем FPS

            # Получаем реальные параметры камеры
            actual_w: float = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            actual_h: float = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            actual_fps: float = self.cap.get(cv2.CAP_PROP_FPS)

            print(f"[INFO] ✅ Камера успешно открыта")
            print(f"[INFO] Разрешение: {actual_w} x {actual_h}, FPS: {actual_fps}")

            self.camera_status = "ok"
            self.stopped = False

            # Запускаем пул воркеров для обработки кадров
            self.worker_threads = []
            for i in range(self.max_workers):
                worker = threading.Thread(target=self._worker_loop, args=(i,), daemon=True)
                worker.start()
                self.worker_threads.append(worker)
            print(f"[INFO] Запущено {self.max_workers} воркеров обработки")

            # Запускаем основной поток захвата
            self.thread = threading.Thread(target=self._update, daemon=True)
            self.thread.start()
            print(f"[INFO] Поток захвата запущен")

            # Принудительный запуск обработки через 2 секунды
            def force_processing() -> None:
                time.sleep(2)
                print("[INFO] Принудительный запуск обработки...")
                self.last_process_time = 0

            force_thread = threading.Thread(target=force_processing, daemon=True)
            force_thread.start()

        except Exception as e:
            print(f"[ERROR] Ошибка при открытии камеры: {e}")
            self.camera_status = "error"
            raise

        return self

    def _worker_loop(self, worker_id: int) -> None:
        """
        Основной цикл воркера для обработки кадров из очереди.

        Args:
            worker_id: Идентификатор воркера для отладки
        """
        while not self.stopped:
            try:
                # Получаем задачу из очереди с таймаутом
                task: Optional[Tuple[np.ndarray, int]] = self.task_queue.get(timeout=1)
                if task is None:
                    continue

                frame, frame_counter = task

                # Увеличиваем счетчик активных воркеров
                with self.worker_lock:
                    self.active_workers += 1

                # Обрабатываем кадр
                self._process_frame_async(frame, frame_counter, worker_id)

                # Уменьшаем счетчик
                with self.worker_lock:
                    self.active_workers -= 1

            except queue.Empty:
                continue  # Очередь пуста, продолжаем ожидание
            except Exception as e:
                print(f"[ERROR] Ошибка в воркере {worker_id}: {e}")
                with self.worker_lock:
                    self.active_workers -= 1

    def _update(self) -> None:
        """
        Основной поток захвата видео.
        Постоянно читает кадры с камеры и добавляет их в очередь на обработку.
        """
        reconnect_attempts: int = 0
        max_reconnect_attempts: int = 5
        consecutive_errors: int = 0
        max_consecutive_errors: int = 5
        frame_counter: int = 0
        last_processing_time: float = 0
        last_frame_time: float = time.time()
        frame_timeout: int = 10

        print("[INFO] _update поток запущен")

        while not self.stopped:
            try:
                current_time: float = time.time()

                # Проверка состояния камеры
                if self.cap is None or not self.cap.isOpened():
                    self.camera_status = "reconnecting"

                    if reconnect_attempts >= max_reconnect_attempts:
                        print(f"[ERROR] Превышено число попыток переподключения")
                        time.sleep(30)
                        reconnect_attempts = 0
                        continue

                    reconnect_attempts += 1
                    print(f"[WARN] Переподключение {reconnect_attempts}/{max_reconnect_attempts}")
                    time.sleep(min(10, reconnect_attempts * 2))

                    # Попытка переподключения
                    if self.use_network:
                        if 'OPENCV_FFMPEG_CAPTURE_OPTIONS' in os.environ:
                            del os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS']
                        self.cap = cv2.VideoCapture(self.camera_source)
                    else:
                        self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)

                    if self.cap and self.cap.isOpened():
                        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        self.cap.set(cv2.CAP_PROP_FPS, 10)
                        print(f"[INFO] ✅ Переподключение успешно")
                        self.camera_status = "ok"
                        reconnect_attempts = 0
                        consecutive_errors = 0
                        last_frame_time = time.time()

                    continue

                # Чтение кадра
                ret: bool
                frame: Optional[np.ndarray]
                ret, frame = self.cap.read()

                if not ret:
                    consecutive_errors += 1
                    print(f"[WARN] Ошибка чтения кадра #{consecutive_errors}")

                    if consecutive_errors >= max_consecutive_errors:
                        print(f"[WARN] Слишком много ошибок, переподключаюсь...")
                        self.cap.release()
                        self.cap = None
                        consecutive_errors = 0

                    time.sleep(0.1)
                    continue

                # Успешное чтение кадра
                consecutive_errors = 0
                reconnect_attempts = 0
                frame_counter += 1
                self.frame_count = frame_counter
                last_frame_time = current_time

                # Сохраняем кадр для live просмотра
                with self.lock:
                    self.last_frame = frame.copy()

                # Проверка таймаута
                if current_time - last_frame_time > frame_timeout:
                    print(f"[WARN] Нет кадров {frame_timeout} сек, переподключаюсь...")
                    self.cap.release()
                    self.cap = None
                    continue

                time_since_last: float = current_time - last_processing_time

                # Определяем, нужно ли обрабатывать этот кадр
                should_process: bool = (
                        frame_counter <= 10 or  # Первые 10 кадров обязательно
                        frame_counter % 5 == 0 or  # Каждый 5-й кадр
                        time_since_last > self.processing_interval or  # Интервал обработки
                        (frame_counter > 10 and time_since_last > 3)  # Принудительно каждые 3 сек
                )

                if should_process:
                    last_processing_time = current_time

                    # Добавляем задачу в очередь для воркеров
                    try:
                        self.task_queue.put_nowait((frame.copy(), frame_counter))

                        # Периодический вывод статистики очереди
                        if frame_counter % 10 == 0:
                            queue_size: int = self.task_queue.qsize()
                            with self.worker_lock:
                                print(
                                    f"[INFO] Кадр #{frame_counter} в очередь. "
                                    f"Очередь: {queue_size}, Активных воркеров: {self.active_workers}/{self.max_workers}"
                                )
                    except queue.Full:
                        if frame_counter % 10 == 0:
                            print(f"[WARN] Очередь переполнена, кадр #{frame_counter} пропущен")

            except Exception as e:
                print(f"[ERROR] Исключение в _update: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(0.5)

    def _process_frame_async(self, frame: np.ndarray, frame_counter: int, worker_id: int) -> None:
        """
        Асинхронная обработка одного кадра (выполняется в воркере).

        Args:
            frame: Кадр для обработки
            frame_counter: Номер кадра
            worker_id: ID воркера для отладки
        """
        try:
            # Уменьшаем разрешение для ускорения обработки
            h: int
            w: int
            h, w = frame.shape[:2]
            small_frame: np.ndarray = cv2.resize(frame, (w // 2, h // 2))

            # Обновляем статус "в обработке"
            with self.lock:
                self.current_processing_frame = frame.copy()
                self.current_processing_plate = "обработка..."
                self.current_processing_access = "..."
                self.current_processing_code = "processing"

            # Распознаем номер на уменьшенном кадре
            plate_info: Dict[str, Any] = self._recognize_plate_yolo_easyocr(small_frame)

            # Масштабируем координаты обратно к оригинальному размеру
            if plate_info.get('bbox'):
                x1: int
                y1: int
                x2: int
                y2: int
                x1, y1, x2, y2 = plate_info['bbox']
                plate_info['bbox'] = (x1 * 2, y1 * 2, x2 * 2, y2 * 2)

            # Извлекаем результаты распознавания
            plate_full: str = plate_info.get('full', '')
            plate_main: str = plate_info.get('main', '')
            plate_region: str = plate_info.get('region', '')
            confidence: float = plate_info.get('confidence', 0.0)
            plate_rect: Optional[Tuple[int, int, int, int]] = plate_info.get('bbox', None)

            # Проверяем доступ по номеру
            access_result: str
            access_code: str
            access_result, access_code = self._check_access(plate_full, plate_main)

            # Обновляем статистику
            with self.lock:
                self.stats['total_processed'] += 1

                if access_code == 'permanent':
                    self.stats['permanent'] += 1
                    self.stats['successful'] += 1
                elif access_code == 'temporary':
                    self.stats['temporary'] += 1
                    self.stats['successful'] += 1
                elif access_code == 'denied':
                    self.stats['denied'] += 1

            # Создаем кадр с отрисованными результатами
            processed_frame: np.ndarray = frame.copy()

            if plate_rect:
                x1, y1, x2, y2 = plate_rect
                color: Tuple[int, int, int] = (0, 255, 0) if access_code in ['permanent', 'temporary'] else (0, 0, 255)

                # Рисуем прямоугольник вокруг номера
                cv2.rectangle(processed_frame, (x1, y1), (x2, y2), color, 2)

                # Добавляем текст с номером
                if plate_full:
                    text: str = f"{plate_full}"
                    cv2.putText(processed_frame, text, (x1, y1 - 5),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            # Добавляем статус доступа
            status_color: Tuple[int, int, int] = self._get_color_for_code(access_code)
            cv2.putText(processed_frame, f"{access_result[:15]}", (5, 25),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, status_color, 1)

            # Добавляем время
            cv2.putText(processed_frame, datetime.now().strftime('%H:%M:%S'), (5, 45),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)

            # Добавляем ID воркера для отладки (каждые 20 кадров)
            if frame_counter % 20 == 0:
                cv2.putText(processed_frame, f"W:{worker_id}", (5, 65),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, (200, 200, 200), 1)

            # Сохраняем результаты
            with self.lock:
                self.last_processed_frame = processed_frame
                self.last_plate_full = plate_full
                self.last_plate_main = plate_main
                self.last_plate_region = plate_region
                self.last_access_result = access_result
                self.last_access_code = access_code

                # Добавляем в очередь обработанных кадров (каждый 2-й)
                if frame_counter % 2 == 0:
                    queue_entry: Dict[str, Any] = {
                        'plate': plate_full,
                        'plate_main': plate_main,
                        'plate_region': plate_region,
                        'access': access_result,
                        'code': access_code,
                        'confidence': round(confidence, 2),
                        'timestamp': datetime.now().strftime('%H:%M:%S'),
                    }

                    self.processing_queue.append(queue_entry)
                    if len(self.processing_queue) > self.max_queue_size:
                        self.processing_queue.pop(0)

                # Добавляем в историю (все распознанные номера)
                if plate_full:
                    history_entry: Dict[str, Any] = {
                        'plate': plate_full,
                        'plate_main': plate_main,
                        'plate_region': plate_region,
                        'access': access_result,
                        'code': access_code,
                        'confidence': round(confidence, 2),
                        'time': datetime.now().strftime('%H:%M:%S'),
                    }

                    self.recognition_history.append(history_entry)
                    if len(self.recognition_history) > self.max_history:
                        self.recognition_history.pop(0)

            # Логируем результат (только если уверенность > 0.2)
            if plate_full and confidence > 0.2:
                print(
                    f"[INFO] Воркер {worker_id}: Кадр #{frame_counter}: "
                    f"{plate_full} (увер:{confidence:.2f}, стат:{access_code})"
                )

        except Exception as e:
            print(f"[ERROR] Ошибка в _process_frame_async: {e}")
            import traceback
            traceback.print_exc()

    def _recognize_plate_yolo_easyocr(self, frame: np.ndarray) -> Dict[str, Any]:
        """
        Оптимизированное распознавание номера с помощью YOLO и EasyOCR.

        Args:
            frame: Кадр для распознавания

        Returns:
            Dict с ключами: full, main, region, confidence, bbox
        """
        result: Dict[str, Any] = {
            'full': '', 'main': '', 'region': '',
            'confidence': 0.0, 'bbox': None
        }

        try:
            if frame is None or self.detector is None:
                return result

            # Масштабирование для ускорения
            h: int
            w: int
            h, w = frame.shape[:2]
            if w > 640 or h > 480:
                scale: float = min(640 / w, 480 / h)
                new_w: int = int(w * scale)
                new_h: int = int(h * scale)
                processed_frame: np.ndarray = cv2.resize(frame, (new_w, new_h))
                scale_factor: float = scale
            else:
                processed_frame = frame
                scale_factor = 1.0

            # Детекция номеров YOLO
            results = self.detector(
                processed_frame,
                conf=0.2,  # Порог уверенности
                iou=0.3,  # Порог пересечения
                max_det=5,  # Максимум 5 объектов
                verbose=False
            )

            best_plate: Optional[Dict[str, str]] = None
            best_bbox: Optional[Tuple[int, int, int, int]] = None
            best_confidence: float = 0.0

            for r in results:
                if r.boxes is None:
                    continue

                for box in r.boxes:
                    # Координаты bounding box
                    x1: int
                    y1: int
                    x2: int
                    y2: int
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    det_conf: float = float(box.conf[0])

                    # Масштабируем координаты обратно
                    if scale_factor != 1.0:
                        x1 = int(x1 / scale_factor)
                        y1 = int(y1 / scale_factor)
                        x2 = int(x2 / scale_factor)
                        y2 = int(y2 / scale_factor)

                    # Добавляем отступ
                    padding: int = 5
                    h_orig, w_orig = frame.shape[:2]
                    x1 = max(0, x1 - padding)
                    y1 = max(0, y1 - padding)
                    x2 = min(w_orig, x2 + padding)
                    y2 = min(h_orig, y2 + padding)

                    # Вырезаем область с номером
                    plate_crop: np.ndarray = frame[y1:y2, x1:x2]
                    if plate_crop.size == 0:
                        continue

                    # Несколько методов предобработки для OCR
                    ocr_results: List[Dict[str, Any]] = []

                    # Метод 1: Увеличение + CLAHE
                    enlarged: np.ndarray = cv2.resize(plate_crop, None, fx=2, fy=2)
                    gray: np.ndarray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
                    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                    enhanced: np.ndarray = clahe.apply(gray)

                    res1: Optional[Dict[str, Any]] = self._fast_ocr(enhanced)
                    if res1:
                        ocr_results.append(res1)

                    # Метод 2: Бинаризация
                    binary: np.ndarray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                    res2: Optional[Dict[str, Any]] = self._fast_ocr(binary)
                    if res2:
                        ocr_results.append(res2)

                    # Метод 3: Только увеличение (fallback)
                    if not ocr_results:
                        res3: Optional[Dict[str, Any]] = self._fast_ocr(gray)
                        if res3:
                            ocr_results.append(res3)

                    if ocr_results:
                        # Выбираем лучший результат по уверенности
                        best_ocr: Dict[str, Any] = max(ocr_results, key=lambda x: x['confidence'])

                        text: str = best_ocr['text']
                        ocr_conf: float = best_ocr['confidence']

                        # Парсим номер
                        parsed: Dict[str, str] = self._parse_russian_plate(text)

                        if parsed['full']:
                            # Комбинированная уверенность
                            combined_conf: float = det_conf * ocr_conf

                            # Бонус за наличие региона
                            if parsed['region']:
                                combined_conf *= 1.2
                                combined_conf = min(combined_conf, 1.0)

                            # Бонус за длину номера
                            length_bonus: float = min(1.3, 1.0 + len(parsed['full']) * 0.05)
                            combined_conf *= length_bonus
                            combined_conf = min(combined_conf, 1.0)

                            if combined_conf > best_confidence:
                                best_confidence = combined_conf
                                best_bbox = (x1, y1, x2, y2)
                                best_plate = parsed

            if best_plate and best_confidence > 0:
                result.update({
                    'full': best_plate['full'],
                    'main': best_plate['main'],
                    'region': best_plate['region'],
                    'confidence': best_confidence,
                    'bbox': best_bbox
                })

            return result

        except Exception as e:
            return result

    def _fast_ocr(self, img: np.ndarray) -> Optional[Dict[str, Any]]:
        """
        Быстрое OCR для одного изображения с оптимизированными параметрами.

        Args:
            img: Изображение для распознавания (grayscale)

        Returns:
            Dict с ключами 'text' и 'confidence' или None
        """
        try:
            if self.reader is None:
                return None

            results = self.reader.readtext(
                img,
                allowlist=ALLOWED_CHARS,  # Только разрешенные символы
                paragraph=False,
                low_text=0.3,  # Низкий порог для поиска текста
                text_threshold=0.5,  # Порог уверенности
                width_ths=0.5,  # Ширина для объединения
                height_ths=0.3,  # Высота для объединения
                ycenter_ths=0.3,  # Центр по Y для объединения
                decoder='greedy',  # Жадный декодер (быстрее)
                beamWidth=5,  # Ширина луча
                batch_size=1,
                workers=1
            )

            if results:
                # Объединяем все найденные фрагменты
                full_text: str = ''.join([r[1] for r in results])
                avg_conf: float = sum([r[2] for r in results]) / len(results)

                # Очищаем текст от лишних символов
                clean_text: str = re.sub(r'[^A-Z0-9А-Я]', '', full_text).upper()

                if clean_text:
                    return {
                        'text': clean_text,
                        'confidence': avg_conf
                    }

            return None

        except Exception as e:
            return None

    def _parse_russian_plate(self, text: str) -> Dict[str, str]:
        """
        Парсинг российского автомобильного номера.
        Поддерживает форматы: A123BC, A123BC45, A123BC456.

        Args:
            text: Распознанный текст

        Returns:
            Dict с ключами 'full', 'main', 'region'
        """
        if not text or len(text) < 6:
            return {'full': '', 'main': '', 'region': ''}

        # Очищаем текст
        clean_text: str = re.sub(r'[^A-Z0-9А-Я]', '', text).upper()

        # Паттерн для основной части (буква + 3 цифры + 2 буквы)
        main_pattern: str = r'([' + RUSSIAN_LETTERS + r'])(\d{3})([' + RUSSIAN_LETTERS + r']{2})'
        main_match: Optional[re.Match] = re.search(main_pattern, clean_text)

        if main_match:
            main_part: str = main_match.group(0)
            remaining: str = clean_text[main_match.end():]

            # Ищем регион (2 или 3 цифры)
            region_match: Optional[re.Match] = re.search(r'(\d{2,3})', remaining)

            if region_match:
                region: str = region_match.group(0)
                try:
                    region_int: int = int(region)
                    if 1 <= region_int <= 999:
                        return {
                            'full': main_part + region,
                            'main': main_part,
                            'region': region
                        }
                except ValueError:
                    pass

            # Если регион не найден, возвращаем только основную часть
            return {
                'full': main_part,
                'main': main_part,
                'region': ''
            }

        # Альтернативный парсинг для сложных случаев
        letters: List[str] = [c for c in clean_text if c in RUSSIAN_LETTERS]
        digits: List[str] = [c for c in clean_text if c.isdigit()]

        if len(letters) >= 3 and len(digits) >= 5:
            main_letters: List[str] = letters[:3]
            main_digits: List[str] = digits[:3]
            region_digits: List[str] = digits[3:6] if len(digits) >= 6 else digits[3:5]

            if len(main_letters) == 3 and len(main_digits) == 3:
                main_part = main_letters[0] + ''.join(main_digits) + ''.join(main_letters[1:3])
                region = ''.join(region_digits) if region_digits else ''

                if re.match(main_pattern, main_part):
                    return {
                        'full': main_part + region,
                        'main': main_part,
                        'region': region
                    }

        return {'full': '', 'main': '', 'region': ''}

    def _check_access(self, plate_full: str, plate_main: str) -> Tuple[str, str]:
        """
        Проверка доступа по номеру в базе данных.

        Args:
            plate_full: Полный номер с регионом
            plate_main: Основная часть номера

        Returns:
            Tuple[str, str]: (Текст статуса, Код статуса)
        """
        if not plate_full and not plate_main:
            return "Номер не распознан", "unrecognized"

        def normalize(p: str) -> str:
            """Нормализация номера для поиска в БД"""
            return re.sub(r'[^A-Z0-9А-Я]', '', p).upper() if p else ""

        # Сначала проверяем полный номер
        if plate_full:
            try:
                lp: LicensePlate = LicensePlate.objects.get(plate_number=normalize(plate_full))
                return self._check_pass(lp)
            except LicensePlate.DoesNotExist:
                pass
            except Exception:
                pass

        # Затем проверяем основную часть
        if plate_main:
            try:
                lp = LicensePlate.objects.get(plate_number=normalize(plate_main))
                return self._check_pass(lp)
            except LicensePlate.DoesNotExist:
                pass
            except Exception:
                pass

        return "Доступ запрещён", "denied"

    def _check_pass(self, lp: LicensePlate) -> Tuple[str, str]:
        """
        Проверка наличия действующего пропуска для номера.

        Args:
            lp: Объект LicensePlate

        Returns:
            Tuple[str, str]: (Текст статуса, Код статуса)
        """
        try:
            passes = Pass.objects.filter(
                license_plate=lp,
                start_date__lte=datetime.now().date()
            )

            if not passes.exists():
                return "Доступ запрещён", "denied"

            p: Pass = passes.first()
            if p.pass_type == 'permanent':
                return "Постоянный, въезд разрешён", "permanent"
            else:  # temporary
                if p.end_date and p.end_date >= datetime.now().date():
                    return "Временный, ручной контроль", "temporary"
                return "Доступ запрещён", "denied"
        except Exception:
            return "Ошибка проверки", "error"

    def _get_color_for_code(self, code: str) -> Tuple[int, int, int]:
        """
        Возвращает цвет BGR для статуса доступа.

        Args:
            code: Код статуса

        Returns:
            Tuple[int, int, int]: Цвет в формате BGR
        """
        colors: Dict[str, Tuple[int, int, int]] = {
            'permanent': (0, 255, 0),  # зеленый
            'temporary': (0, 255, 255),  # желтый
            'denied': (0, 0, 255),  # красный
            'unrecognized': (128, 128, 128),  # серый
            'error': (255, 0, 255),  # фиолетовый
            'processing': (255, 255, 0)  # голубой
        }
        return colors.get(code, (255, 255, 255))  # белый по умолчанию

    def get_frame(self) -> Optional[bytes]:
        """
        Получение последнего кадра для live просмотра.

        Returns:
            JPEG изображение в байтах или None
        """
        with self.lock:
            if self.last_frame is None:
                return None
            ret: bool
            jpeg: Optional[np.ndarray]
            ret, jpeg = cv2.imencode('.jpg', self.last_frame)
            return jpeg.tobytes() if ret else None

    def get_processed_frame(self) -> Optional[bytes]:
        """
        Получение последнего обработанного кадра.

        Returns:
            JPEG изображение в байтах или None
        """
        with self.lock:
            if self.last_processed_frame is None:
                return None
            ret, jpeg = cv2.imencode('.jpg', self.last_processed_frame)
            return jpeg.tobytes() if ret else None

    def get_status(self) -> Dict[str, str]:
        """
        Получение статуса последнего распознавания.

        Returns:
            Dict с ключами: plate, plate_main, plate_region, access, code
        """
        with self.lock:
            return {
                'plate': self.last_plate_full,
                'plate_main': self.last_plate_main,
                'plate_region': self.last_plate_region,
                'access': self.last_access_result,
                'code': self.last_access_code
            }

    def get_last_successful(self) -> Optional[Dict[str, Any]]:
        """
        Получение данных последнего успешного распознавания.

        Returns:
            Dict с ключами: frame, plate, access, code, time или None
        """
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

    def get_recognition_history(self) -> List[Dict[str, Any]]:
        """
        Получение истории распознаваний.

        Returns:
            Список записей истории
        """
        with self.lock:
            return self.recognition_history.copy()

    def get_current_processing(self) -> Optional[Dict[str, Any]]:
        """
        Получение текущего обрабатываемого кадра.

        Returns:
            Dict с ключами: frame, plate, access, code или None
        """
        with self.lock:
            if self.current_processing_frame is None:
                return None
            ret, jpeg = cv2.imencode('.jpg', self.current_processing_frame)
            if not ret:
                return None
            return {
                'frame': jpeg.tobytes(),
                'plate': self.current_processing_plate,
                'access': self.current_processing_access,
                'code': self.current_processing_code
            }

    def get_processing_queue(self) -> List[Dict[str, Any]]:
        """
        Получение очереди обработанных кадров.

        Returns:
            Список последних обработанных кадров (до 15)
        """
        with self.lock:
            return [{
                'plate': e['plate'],
                'plate_main': e.get('plate_main', ''),
                'plate_region': e.get('plate_region', ''),
                'access': e['access'],
                'code': e['code'],
                'confidence': e['confidence'],
                'timestamp': e['timestamp']
            } for e in self.processing_queue[-15:]]

    def get_stats(self) -> Dict[str, int]:
        """
        Получение статистики распознаваний.

        Returns:
            Dict с ключами: total_processed, successful, permanent, temporary, denied
        """
        with self.lock:
            return self.stats.copy()

    def stop(self) -> None:
        """Остановка всех потоков и освобождение ресурсов."""
        self.stopped = True

        # Очищаем очередь задач
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
            except queue.Empty:
                break

        # Освобождаем камеру
        if self.cap:
            self.cap.release()

        # Очищаем GPU память
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
        gc.collect()
        print(f"[INFO] Ресурсы освобождены")






# class CameraStream:
#     def __init__(self, camera_source=0, use_network=False, camera_id=None):
#         if camera_id is not None:
#             self.camera_source = camera_id
#             self.use_network = False
#         else:
#             self.camera_source = camera_source
#             self.use_network = use_network
#
#         self.cap = None
#         self.stopped = False
#         self.lock = threading.Lock()
#         self.last_frame = None
#         self.last_processed_frame = None
#         self.last_plate_full = ""
#         self.last_plate_main = ""
#         self.last_plate_region = ""
#         self.last_access_result = ""
#         self.last_access_code = ""
#         self.processing_interval = 3.0
#         self.last_process_time = 0
#         self.reconnect_delay = 3
#         self.frame_count = 0
#
#         # ПОНИЖАЕМ ПОРОГ УВЕРЕННОСТИ для тестирования
#         self.confidence_threshold = 0.05  # Было 0.3
#         self.min_plate_length = 6
#         self.max_plate_length = 9
#
#         self._init_yolo_model()
#         self._init_easyocr()
#
#         self.last_successful_plate = ""
#         self.last_successful_plate_full = ""
#         self.last_successful_access = ""
#         self.last_successful_code = ""
#         self.last_successful_frame = None
#         self.last_successful_time = None
#
#         self.recognition_history = []
#         self.max_history = 20
#
#         self.processing_queue = []
#         self.max_queue_size = 20
#
#         self.current_processing_frame = None
#         self.current_processing_plate = ""
#         self.current_processing_access = ""
#         self.current_processing_code = "processing"
#
#         # Статус камеры
#         self.camera_status = "initializing"
#         self.last_frame_time = 0
#         self.frame_timeout = 10
#
#         # Счетчики для статистики
#         self.stats = {
#             'total_processed': 0,
#             'successful': 0,
#             'permanent': 0,
#             'temporary': 0,
#             'denied': 0
#         }
#
#     def _init_yolo_model(self):
#         try:
#             model_name = 'yolov8m.pt'
#             print(f"[INFO] Загрузка модели {model_name}...")
#             self.detector = YOLO(model_name)
#             self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
#             if self.device == 'cuda':
#                 self.detector.to('cuda')
#                 print(f"[INFO] Модель загружена на GPU")
#             else:
#                 print(f"[INFO] Модель загружена на CPU")
#         except Exception as e:
#             print(f"[ERROR] Ошибка загрузки YOLO: {e}")
#             self.detector = YOLO('yolov8n.pt')
#             self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
#
#     def _init_easyocr(self):
#         try:
#             gpu = True if torch.cuda.is_available() else False
#             self.reader = easyocr.Reader(
#                 ['ru', 'en'],
#                 gpu=gpu,
#                 model_storage_directory='~/.easyocr/model',
#                 download_enabled=True,
#                 verbose=False
#             )
#             print(f"[INFO] EasyOCR инициализирован ({'GPU' if gpu else 'CPU'})")
#         except Exception as e:
#             print(f"[ERROR] Ошибка инициализации EasyOCR: {e}")
#             self.reader = None
#
#     def start(self):
#         """Запуск захвата видео с камеры"""
#         try:
#             if self.use_network:
#                 if 'OPENCV_FFMPEG_CAPTURE_OPTIONS' in os.environ:
#                     del os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS']
#
#                 print(f"[INFO] Попытка открыть камеру: {self.camera_source}")
#                 print(f"[INFO] Пробую: Без параметров")
#                 self.cap = cv2.VideoCapture(self.camera_source)
#
#                 if not self.cap.isOpened():
#                     print(f"[INFO] Пробую: TCP")
#                     os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;5000000|stimeout;5000000"
#                     self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_FFMPEG)
#
#                 if not self.cap.isOpened():
#                     print(f"[INFO] Пробую: UDP")
#                     os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp|timeout;5000000|stimeout;5000000"
#                     self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_FFMPEG)
#             else:
#                 self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
#                 if not self.cap.isOpened():
#                     self.cap = cv2.VideoCapture(self.camera_source)
#
#             if not self.cap.isOpened():
#                 self.camera_status = "error"
#                 raise RuntimeError("Не удалось открыть камеру")
#
#             self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
#             self.cap.set(cv2.CAP_PROP_FPS, 10)
#
#             actual_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
#             actual_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
#             actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
#
#             print(f"[INFO] ✅ Камера успешно открыта")
#             print(f"[INFO] Разрешение: {actual_w} x {actual_h}, FPS: {actual_fps}")
#
#             self.camera_status = "ok"
#             self.stopped = False
#             self.thread = threading.Thread(target=self._update)
#             self.thread.daemon = True
#             self.thread.start()
#             print(f"[INFO] Поток обработки запущен")
#
#             def force_processing():
#                 time.sleep(2)
#                 print("[INFO] Принудительный запуск обработки...")
#                 self.last_process_time = 0
#
#             force_thread = threading.Thread(target=force_processing)
#             force_thread.daemon = True
#             force_thread.start()
#
#         except Exception as e:
#             print(f"[ERROR] Ошибка при открытии камеры: {e}")
#             self.camera_status = "error"
#             raise
#
#         return self
#
#     def _update(self):
#         """Оптимизированный поток захвата и обработки кадров"""
#         reconnect_attempts = 0
#         max_reconnect_attempts = 5
#         consecutive_errors = 0
#         max_consecutive_errors = 5
#         frame_counter = 0
#         last_processing_time = 0
#         last_frame_time = time.time()
#         frame_timeout = 10
#
#         print("[INFO] _update поток запущен")
#
#         while not self.stopped:
#             try:
#                 current_time = time.time()
#
#                 if self.cap is None or not self.cap.isOpened():
#                     self.camera_status = "reconnecting"
#
#                     if reconnect_attempts >= max_reconnect_attempts:
#                         print(f"[ERROR] Превышено число попыток переподключения")
#                         time.sleep(30)
#                         reconnect_attempts = 0
#                         continue
#
#                     reconnect_attempts += 1
#                     print(f"[WARN] Переподключение {reconnect_attempts}/{max_reconnect_attempts}")
#                     time.sleep(min(10, reconnect_attempts * 2))
#
#                     if self.use_network:
#                         if 'OPENCV_FFMPEG_CAPTURE_OPTIONS' in os.environ:
#                             del os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS']
#                         self.cap = cv2.VideoCapture(self.camera_source)
#                     else:
#                         self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
#
#                     if self.cap and self.cap.isOpened():
#                         self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
#                         self.cap.set(cv2.CAP_PROP_FPS, 10)
#                         print(f"[INFO] ✅ Переподключение успешно")
#                         self.camera_status = "ok"
#                         reconnect_attempts = 0
#                         consecutive_errors = 0
#                         last_frame_time = time.time()
#
#                     continue
#
#                 ret, frame = self.cap.read()
#
#                 if not ret:
#                     consecutive_errors += 1
#                     print(f"[WARN] Ошибка чтения кадра #{consecutive_errors}")
#
#                     if consecutive_errors >= max_consecutive_errors:
#                         print(f"[WARN] Слишком много ошибок, переподключаюсь...")
#                         self.cap.release()
#                         self.cap = None
#                         consecutive_errors = 0
#
#                     time.sleep(0.1)
#                     continue
#
#                 consecutive_errors = 0
#                 reconnect_attempts = 0
#                 frame_counter += 1
#                 self.frame_count = frame_counter
#                 last_frame_time = current_time
#
#                 with self.lock:
#                     self.last_frame = frame.copy()
#
#                 if current_time - last_frame_time > frame_timeout:
#                     print(f"[WARN] Нет кадров {frame_timeout} сек, переподключаюсь...")
#                     self.cap.release()
#                     self.cap = None
#                     continue
#
#                 time_since_last = current_time - last_processing_time
#
#                 should_process = (
#                         frame_counter <= 10 or
#                         frame_counter % 5 == 0 or
#                         time_since_last > self.processing_interval or
#                         (frame_counter > 10 and time_since_last > 3)
#                 )
#
#                 if should_process:
#                     last_processing_time = current_time
#
#                     process_thread = threading.Thread(
#                         target=self._process_frame_async,
#                         args=(frame.copy(), frame_counter),
#                         daemon=True
#                     )
#                     process_thread.start()
#
#                     if frame_counter % 10 == 0:
#                         print(f"[INFO] Запущена обработка кадра #{frame_counter}")
#
#             except Exception as e:
#                 print(f"[ERROR] Исключение в _update: {e}")
#                 import traceback
#                 traceback.print_exc()
#                 time.sleep(0.5)
#
#     def _process_frame_async(self, frame, frame_counter):
#         """Асинхронная обработка кадра с обновлением статистики"""
#         try:
#             h, w = frame.shape[:2]
#             small_frame = cv2.resize(frame, (w // 2, h // 2))
#
#             with self.lock:
#                 self.current_processing_frame = frame.copy()
#                 self.current_processing_plate = "обработка..."
#                 self.current_processing_access = "..."
#                 self.current_processing_code = "processing"
#
#             plate_info = self._recognize_plate_yolo_easyocr(small_frame)
#
#             if plate_info.get('bbox'):
#                 x1, y1, x2, y2 = plate_info['bbox']
#                 plate_info['bbox'] = (x1 * 2, y1 * 2, x2 * 2, y2 * 2)
#
#             plate_full = plate_info.get('full', '')
#             plate_main = plate_info.get('main', '')
#             plate_region = plate_info.get('region', '')
#             confidence = plate_info.get('confidence', 0.0)
#             plate_rect = plate_info.get('bbox', None)
#
#             access_result, access_code = self._check_access(plate_full, plate_main)
#
#             # Обновляем статистику
#             with self.lock:
#                 self.stats['total_processed'] += 1
#
#                 if access_code == 'permanent':
#                     self.stats['permanent'] += 1
#                     self.stats['successful'] += 1
#                 elif access_code == 'temporary':
#                     self.stats['temporary'] += 1
#                     self.stats['successful'] += 1
#                 elif access_code == 'denied':
#                     self.stats['denied'] += 1
#
#             processed_frame = frame.copy()
#
#             if plate_rect:
#                 x1, y1, x2, y2 = plate_rect
#                 color = (0, 255, 0) if access_code in ['permanent', 'temporary'] else (0, 0, 255)
#
#                 cv2.rectangle(processed_frame, (x1, y1), (x2, y2), color, 2)
#
#                 if plate_full:
#                     text = f"{plate_full}"
#                     cv2.putText(processed_frame, text, (x1, y1 - 5),
#                                 cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
#
#             status_color = self._get_color_for_code(access_code)
#             cv2.putText(processed_frame, f"{access_result[:15]}", (5, 25),
#                         cv2.FONT_HERSHEY_SIMPLEX, 0.4, status_color, 1)
#
#             cv2.putText(processed_frame, datetime.now().strftime('%H:%M:%S'), (5, 45),
#                         cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
#
#             with self.lock:
#                 self.last_processed_frame = processed_frame
#                 self.last_plate_full = plate_full
#                 self.last_plate_main = plate_main
#                 self.last_plate_region = plate_region
#                 self.last_access_result = access_result
#                 self.last_access_code = access_code
#
#                 if frame_counter % 2 == 0:
#                     queue_entry = {
#                         'plate': plate_full,
#                         'plate_main': plate_main,
#                         'plate_region': plate_region,
#                         'access': access_result,
#                         'code': access_code,
#                         'confidence': round(confidence, 2),
#                         'timestamp': datetime.now().strftime('%H:%M:%S'),
#                     }
#
#                     self.processing_queue.append(queue_entry)
#                     if len(self.processing_queue) > self.max_queue_size:
#                         self.processing_queue.pop(0)
#
#                 # В историю добавляем ВСЕ распознанные номера для тестирования
#                 if plate_full:
#                     history_entry = {
#                         'plate': plate_full,
#                         'plate_main': plate_main,
#                         'plate_region': plate_region,
#                         'access': access_result,
#                         'code': access_code,
#                         'confidence': round(confidence, 2),
#                         'time': datetime.now().strftime('%H:%M:%S'),
#                     }
#
#                     self.recognition_history.append(history_entry)
#                     if len(self.recognition_history) > self.max_history:
#                         self.recognition_history.pop(0)
#
#                     print(f"[INFO] Добавлено в историю: {plate_full} (увер:{confidence:.2f})")
#
#             if plate_full:
#                 print(f"[INFO] Кадр #{frame_counter}: {plate_full} (увер:{confidence:.2f}, стат:{access_code})")
#
#         except Exception as e:
#             print(f"[ERROR] Ошибка в _process_frame_async: {e}")
#             import traceback
#             traceback.print_exc()
#
#     def _recognize_plate_yolo_easyocr(self, frame):
#         """Оптимизированное распознавание номера"""
#         result = {
#             'full': '', 'main': '', 'region': '',
#             'confidence': 0.0, 'bbox': None
#         }
#
#         try:
#             if frame is None or self.detector is None:
#                 return result
#
#             h, w = frame.shape[:2]
#             if w > 640 or h > 480:
#                 scale = min(640 / w, 480 / h)
#                 new_w, new_h = int(w * scale), int(h * scale)
#                 processed_frame = cv2.resize(frame, (new_w, new_h))
#                 scale_factor = scale
#             else:
#                 processed_frame = frame
#                 scale_factor = 1.0
#
#             results = self.detector(
#                 processed_frame,
#                 conf=0.2,
#                 iou=0.3,
#                 max_det=5,
#                 verbose=False
#             )
#
#             best_plate = None
#             best_bbox = None
#             best_confidence = 0.0
#
#             for r in results:
#                 if r.boxes is None:
#                     continue
#
#                 for box in r.boxes:
#                     x1, y1, x2, y2 = map(int, box.xyxy[0])
#                     det_conf = float(box.conf[0])
#
#                     if scale_factor != 1.0:
#                         x1 = int(x1 / scale_factor)
#                         y1 = int(y1 / scale_factor)
#                         x2 = int(x2 / scale_factor)
#                         y2 = int(y2 / scale_factor)
#
#                     padding = 5
#                     h_orig, w_orig = frame.shape[:2]
#                     x1 = max(0, x1 - padding)
#                     y1 = max(0, y1 - padding)
#                     x2 = min(w_orig, x2 + padding)
#                     y2 = min(h_orig, y2 + padding)
#
#                     plate_crop = frame[y1:y2, x1:x2]
#                     if plate_crop.size == 0:
#                         continue
#
#                     ocr_results = []
#
#                     enlarged = cv2.resize(plate_crop, None, fx=2, fy=2)
#                     gray = cv2.cvtColor(enlarged, cv2.COLOR_BGR2GRAY)
#                     clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
#                     enhanced = clahe.apply(gray)
#
#                     res1 = self._fast_ocr(enhanced)
#                     if res1:
#                         ocr_results.append(res1)
#
#                     _, binary = cv2.threshold(gray, 0, 255,
#                                               cv2.THRESH_BINARY + cv2.THRESH_OTSU)
#                     res2 = self._fast_ocr(binary)
#                     if res2:
#                         ocr_results.append(res2)
#
#                     if not ocr_results:
#                         res3 = self._fast_ocr(gray)
#                         if res3:
#                             ocr_results.append(res3)
#
#                     if ocr_results:
#                         best_ocr = max(ocr_results, key=lambda x: x['confidence'])
#
#                         text = best_ocr['text']
#                         ocr_conf = best_ocr['confidence']
#
#                         parsed = self._parse_russian_plate(text)
#
#                         if parsed['full']:
#                             combined_conf = det_conf * ocr_conf
#
#                             if parsed['region']:
#                                 combined_conf *= 1.2
#                                 combined_conf = min(combined_conf, 1.0)
#
#                             length_bonus = min(1.3, 1.0 + len(parsed['full']) * 0.05)
#                             combined_conf *= length_bonus
#                             combined_conf = min(combined_conf, 1.0)
#
#                             if combined_conf > best_confidence:
#                                 best_confidence = combined_conf
#                                 best_bbox = (x1, y1, x2, y2)
#                                 best_plate = parsed
#
#             if best_plate and best_confidence > 0:
#                 result.update({
#                     'full': best_plate['full'],
#                     'main': best_plate['main'],
#                     'region': best_plate['region'],
#                     'confidence': best_confidence,
#                     'bbox': best_bbox
#                 })
#
#             return result
#
#         except Exception as e:
#             return result
#
#     def _fast_ocr(self, img):
#         """Быстрое OCR для одного изображения"""
#         try:
#             if self.reader is None:
#                 return None
#
#             results = self.reader.readtext(
#                 img,
#                 allowlist=ALLOWED_CHARS,
#                 paragraph=False,
#                 low_text=0.3,
#                 text_threshold=0.5,
#                 width_ths=0.5,
#                 height_ths=0.3,
#                 ycenter_ths=0.3,
#                 decoder='greedy',
#                 beamWidth=5,
#                 batch_size=1,
#                 workers=1
#             )
#
#             if results:
#                 full_text = ''.join([r[1] for r in results])
#                 avg_conf = sum([r[2] for r in results]) / len(results)
#
#                 clean_text = re.sub(r'[^A-Z0-9А-Я]', '', full_text).upper()
#
#                 if clean_text:
#                     return {
#                         'text': clean_text,
#                         'confidence': avg_conf
#                     }
#
#             return None
#
#         except Exception as e:
#             return None
#
#     def _parse_russian_plate(self, text):
#         """Парсинг российского автомобильного номера"""
#         if not text or len(text) < 6:
#             return {'full': '', 'main': '', 'region': ''}
#
#         clean_text = re.sub(r'[^A-Z0-9А-Я]', '', text).upper()
#
#         main_pattern = r'([' + RUSSIAN_LETTERS + r'])(\d{3})([' + RUSSIAN_LETTERS + r']{2})'
#         main_match = re.search(main_pattern, clean_text)
#
#         if main_match:
#             main_part = main_match.group(0)
#             remaining = clean_text[main_match.end():]
#
#             region_match = re.search(r'(\d{2,3})', remaining)
#
#             if region_match:
#                 region = region_match.group(0)
#                 try:
#                     region_int = int(region)
#                     if 1 <= region_int <= 999:
#                         return {
#                             'full': main_part + region,
#                             'main': main_part,
#                             'region': region
#                         }
#                 except:
#                     pass
#
#             return {
#                 'full': main_part,
#                 'main': main_part,
#                 'region': ''
#             }
#
#         letters = [c for c in clean_text if c in RUSSIAN_LETTERS]
#         digits = [c for c in clean_text if c.isdigit()]
#
#         if len(letters) >= 3 and len(digits) >= 5:
#             main_letters = letters[:3]
#             main_digits = digits[:3]
#             region_digits = digits[3:6] if len(digits) >= 6 else digits[3:5]
#
#             if len(main_letters) == 3 and len(main_digits) == 3:
#                 main_part = main_letters[0] + ''.join(main_digits) + ''.join(main_letters[1:3])
#                 region = ''.join(region_digits) if region_digits else ''
#
#                 if re.match(main_pattern, main_part):
#                     return {
#                         'full': main_part + region,
#                         'main': main_part,
#                         'region': region
#                     }
#
#         return {'full': '', 'main': '', 'region': ''}
#
#     def _check_access(self, plate_full, plate_main):
#         """Проверка доступа по номеру"""
#         if not plate_full and not plate_main:
#             return "Номер не распознан", "unrecognized"
#
#         def normalize(p):
#             return re.sub(r'[^A-Z0-9А-Я]', '', p).upper() if p else ""
#
#         if plate_full:
#             try:
#                 lp = LicensePlate.objects.get(plate_number=normalize(plate_full))
#                 return self._check_pass(lp)
#             except:
#                 pass
#
#         if plate_main:
#             try:
#                 lp = LicensePlate.objects.get(plate_number=normalize(plate_main))
#                 return self._check_pass(lp)
#             except:
#                 pass
#
#         return "Доступ запрещён", "denied"
#
#     def _check_pass(self, lp):
#         """Проверка пропуска"""
#         try:
#             passes = Pass.objects.filter(
#                 license_plate=lp,
#                 start_date__lte=datetime.now().date()
#             )
#
#             if not passes.exists():
#                 return "Доступ запрещён", "denied"
#
#             p = passes.first()
#             if p.pass_type == 'permanent':
#                 return "Постоянный, въезд разрешён", "permanent"
#             else:
#                 if p.end_date and p.end_date >= datetime.now().date():
#                     return "Временный, ручной контроль", "temporary"
#                 return "Доступ запрещён", "denied"
#         except:
#             return "Ошибка проверки", "error"
#
#     def _get_color_for_code(self, code):
#         """Возвращает цвет BGR для статуса доступа"""
#         colors = {
#             'permanent': (0, 255, 0),
#             'temporary': (0, 255, 255),
#             'denied': (0, 0, 255),
#             'unrecognized': (128, 128, 128),
#             'error': (255, 0, 255),
#             'processing': (255, 255, 0)
#         }
#         return colors.get(code, (255, 255, 255))
#
#     def get_frame(self):
#         with self.lock:
#             if self.last_frame is None:
#                 return None
#             ret, jpeg = cv2.imencode('.jpg', self.last_frame)
#             return jpeg.tobytes() if ret else None
#
#     def get_processed_frame(self):
#         with self.lock:
#             if self.last_processed_frame is None:
#                 return None
#             ret, jpeg = cv2.imencode('.jpg', self.last_processed_frame)
#             return jpeg.tobytes() if ret else None
#
#     def get_status(self):
#         with self.lock:
#             return {
#                 'plate': self.last_plate_full,
#                 'plate_main': self.last_plate_main,
#                 'plate_region': self.last_plate_region,
#                 'access': self.last_access_result,
#                 'code': self.last_access_code
#             }
#
#     def get_last_successful(self):
#         with self.lock:
#             if self.last_successful_frame is None:
#                 return None
#             ret, jpeg = cv2.imencode('.jpg', self.last_successful_frame)
#             if not ret:
#                 return None
#             return {
#                 'frame': jpeg.tobytes(),
#                 'plate': self.last_successful_plate_full,
#                 'access': self.last_successful_access,
#                 'code': self.last_successful_code,
#                 'time': self.last_successful_time.strftime('%H:%M:%S') if self.last_successful_time else None
#             }
#
#     def get_recognition_history(self):
#         with self.lock:
#             return self.recognition_history.copy()
#
#     def get_current_processing(self):
#         with self.lock:
#             if self.current_processing_frame is None:
#                 return None
#             ret, jpeg = cv2.imencode('.jpg', self.current_processing_frame)
#             if not ret:
#                 return None
#             return {
#                 'frame': jpeg.tobytes(),
#                 'plate': self.current_processing_plate,
#                 'access': self.current_processing_access,
#                 'code': self.current_processing_code
#             }
#
#     def get_processing_queue(self):
#         with self.lock:
#             return [{
#                 'plate': e['plate'],
#                 'plate_main': e.get('plate_main', ''),
#                 'plate_region': e.get('plate_region', ''),
#                 'access': e['access'],
#                 'code': e['code'],
#                 'confidence': e['confidence'],
#                 'timestamp': e['timestamp']
#             } for e in self.processing_queue[-15:]]
#
#     def get_stats(self):
#         """Получение статистики распознаваний"""
#         with self.lock:
#             return self.stats.copy()
#
#     def stop(self):
#         self.stopped = True
#         if self.cap:
#             self.cap.release()


# class CameraStream:
#     def __init__(self, camera_source=0, use_network=False, camera_id=None):
#         if camera_id is not None:
#             self.camera_source = camera_id
#             self.use_network = False
#         else:
#             self.camera_source = camera_source
#             self.use_network = use_network
#
#         self.cap = None
#         self.stopped = False
#         self.lock = threading.Lock()
#         self.last_frame = None
#         self.last_processed_frame = None
#         self.last_plate_full = ""
#         self.last_plate_main = ""
#         self.last_plate_region = ""
#         self.last_access_result = ""
#         self.last_access_code = ""
#         self.processing_interval = 3.0
#         self.last_process_time = 0
#         self.reconnect_delay = 3
#         self.frame_count = 0
#
#         # ПОНИЖАЕМ ПОРОГ УВЕРЕННОСТИ для тестирования
#         self.confidence_threshold = 0.0
#         self.min_plate_length = 6
#         self.max_plate_length = 9
#
#         # Очередь для обработки кадров (ограничиваем размер)
#         self.frame_queue = queue.Queue(maxsize=5)
#
#         # Пул потоков обработчиков
#         self.num_workers = 2  # Ограничиваем количество параллельных обработчиков
#         self.worker_threads = []
#         self.worker_semaphore = threading.Semaphore(self.num_workers)
#
#         # Событие для остановки воркеров
#         self.stop_workers = threading.Event()
#
#         self._init_yolo_model()
#         self._init_easyocr()
#
#         self.last_successful_plate = ""
#         self.last_successful_plate_full = ""
#         self.last_successful_access = ""
#         self.last_successful_code = ""
#         self.last_successful_frame = None
#         self.last_successful_time = None
#
#         self.recognition_history = []
#         self.max_history = 15  # Уменьшаем для экономии памяти
#
#         self.processing_queue = []
#         self.max_queue_size = 10  # Уменьшаем для экономии памяти
#
#         self.current_processing_frame = None
#         self.current_processing_plate = ""
#         self.current_processing_access = ""
#         self.current_processing_code = "processing"
#
#         # Статус камеры
#         self.camera_status = "initializing"
#         self.last_frame_time = 0
#         self.frame_timeout = 10
#
#         # Счетчики для статистики
#         self.stats = {
#             'total_processed': 0,
#             'successful': 0,
#             'permanent': 0,
#             'temporary': 0,
#             'denied': 0
#         }
#
#     def _init_yolo_model(self):
#         try:
#             model_name = 'yolov8m.pt'
#             print(f"[INFO] Загрузка модели {model_name}...")
#             self.detector = YOLO(model_name)
#             self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
#             if self.device == 'cuda':
#                 self.detector.to('cuda')
#                 print(f"[INFO] Модель загружена на GPU")
#                 # Очищаем кэш CUDA после загрузки
#                 torch.cuda.empty_cache()
#             else:
#                 print(f"[INFO] Модель загружена на CPU")
#         except Exception as e:
#             print(f"[ERROR] Ошибка загрузки YOLO: {e}")
#             self.detector = YOLO('yolov8n.pt')
#             self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
#
#     def _init_easyocr(self):
#         try:
#             gpu = True if torch.cuda.is_available() else False
#             self.reader = easyocr.Reader(
#                 ['ru', 'en'],
#                 gpu=gpu,
#                 model_storage_directory='~/.easyocr/model',
#                 download_enabled=True,
#                 verbose=False
#             )
#             print(f"[INFO] EasyOCR инициализирован ({'GPU' if gpu else 'CPU'})")
#         except Exception as e:
#             print(f"[ERROR] Ошибка инициализации EasyOCR: {e}")
#             self.reader = None
#
#     def start(self):
#         """Запуск захвата видео с камеры"""
#         try:
#             if self.use_network:
#                 try:
#                     print(f'OPENCV_FFMPEG_CAPTURE_OPTIONS: {os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS']}')
#                     if 'OPENCV_FFMPEG_CAPTURE_OPTIONS' in os.environ:
#                         del os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS']
#                 except KeyError as e:
#                     print(f'--> {e}')
#
#                 print(f"[INFO] Попытка открыть камеру: {self.camera_source}")
#                 print(f"[INFO] Пробую: Без параметров")
#                 self.cap = cv2.VideoCapture(self.camera_source)
#                 print(f'camera_source: {self.camera_source}')
#                 print(f'cap: {self.cap}')
#                 if not self.cap.isOpened():
#                     print(f"[INFO] Пробую: TCP")
#                     os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|timeout;5000000|stimeout;5000000"
#                     self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_FFMPEG)
#
#                 if not self.cap.isOpened():
#                     print(f"[INFO] Пробую: UDP")
#                     os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp|timeout;5000000|stimeout;5000000"
#                     self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_FFMPEG)
#             else:
#                 self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
#                 if not self.cap.isOpened():
#                     self.cap = cv2.VideoCapture(self.camera_source)
#
#             if not self.cap.isOpened():
#                 self.camera_status = "error"
#                 raise RuntimeError("Не удалось открыть камеру")
#
#             self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
#             self.cap.set(cv2.CAP_PROP_FPS, 10)
#
#             actual_w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
#             actual_h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
#             actual_fps = self.cap.get(cv2.CAP_PROP_FPS)
#
#             print(f"[INFO] ✅ Камера успешно открыта")
#             print(f"[INFO] Разрешение: {actual_w} x {actual_h}, FPS: {actual_fps}")
#
#             self.camera_status = "ok"
#             self.stopped = False
#             self.stop_workers.clear()
#
#             # Запускаем основной поток захвата
#             self.thread = threading.Thread(target=self._update)
#             self.thread.daemon = True
#             self.thread.start()
#
#             # Запускаем пул воркеров для обработки
#             for i in range(self.num_workers):
#                 worker = threading.Thread(target=self._worker_process)
#                 worker.daemon = True
#                 worker.start()
#                 self.worker_threads.append(worker)
#
#             print(f"[INFO] Поток захвата и {self.num_workers} воркеров запущены")
#
#             def force_processing():
#                 time.sleep(2)
#                 self.last_process_time = 0
#
#             force_thread = threading.Thread(target=force_processing)
#             force_thread.daemon = True
#             force_thread.start()
#
#         except Exception as e:
#             print(f"[ERROR] Ошибка при открытии камеры: {e}")
#             self.camera_status = "error"
#             raise
#
#         return self
#
#     def _worker_process(self):
#         """Воркер для обработки кадров из очереди"""
#         while not self.stop_workers.is_set():
#             try:
#                 # Получаем кадр из очереди с таймаутом
#                 frame_data = self.frame_queue.get(timeout=1)
#                 if frame_data is None:
#                     continue
#
#                 frame, frame_counter = frame_data
#
#                 # Используем семафор для ограничения параллельных обработок
#                 with self.worker_semaphore:
#                     self._process_frame_async(frame, frame_counter)
#
#             except queue.Empty:
#                 continue
#             except Exception as e:
#                 print(f"[ERROR] Ошибка в воркере: {e}")
#
#     def _update(self):
#         """Оптимизированный поток захвата и обработки кадров"""
#         reconnect_attempts = 0
#         max_reconnect_attempts = 5
#         consecutive_errors = 0
#         max_consecutive_errors = 5
#         frame_counter = 0
#         last_processing_time = 0
#         last_frame_time = time.time()
#         frame_timeout = 10
#
#         print("[INFO] _update поток запущен")
#
#         while not self.stopped:
#             try:
#                 current_time = time.time()
#
#                 if self.cap is None or not self.cap.isOpened():
#                     self.camera_status = "reconnecting"
#
#                     if reconnect_attempts >= max_reconnect_attempts:
#                         print(f"[ERROR] Превышено число попыток переподключения")
#                         time.sleep(30)
#                         reconnect_attempts = 0
#                         continue
#
#                     reconnect_attempts += 1
#                     print(f"[WARN] Переподключение {reconnect_attempts}/{max_reconnect_attempts}")
#                     time.sleep(min(10, reconnect_attempts * 2))
#
#                     if self.use_network:
#                         if 'OPENCV_FFMPEG_CAPTURE_OPTIONS' in os.environ:
#                             del os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS']
#                         self.cap = cv2.VideoCapture(self.camera_source)
#                     else:
#                         self.cap = cv2.VideoCapture(self.camera_source, cv2.CAP_DSHOW)
#
#                     if self.cap and self.cap.isOpened():
#                         self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
#                         self.cap.set(cv2.CAP_PROP_FPS, 10)
#                         print(f"[INFO] ✅ Переподключение успешно")
#                         self.camera_status = "ok"
#                         reconnect_attempts = 0
#                         consecutive_errors = 0
#                         last_frame_time = time.time()
#
#                     continue
#
#                 ret, frame = self.cap.read()
#                 # print(f'ret,{type(ret), ret}')
#                 # print(f'frame: {type(frame), frame}')
#                 if not ret:
#                     consecutive_errors += 1
#                     print(f"[WARN] Ошибка чтения кадра #{consecutive_errors}")
#
#                     if consecutive_errors >= max_consecutive_errors:
#                         print(f"[WARN] Слишком много ошибок, переподключаюсь...")
#                         self.cap.release()
#                         self.cap = None
#                         consecutive_errors = 0
#
#                     time.sleep(0.1)
#                     continue
#
#                 consecutive_errors = 0
#                 reconnect_attempts = 0
#                 frame_counter += 1
#                 self.frame_count = frame_counter
#                 last_frame_time = current_time
#
#                 with self.lock:
#                     # Сохраняем только уменьшенную копию для last_frame
#                     if frame_counter % 3 == 0:
#                         self.last_frame = frame.copy()
#
#                 if current_time - last_frame_time > frame_timeout:
#                     print(f"[WARN] Нет кадров {frame_timeout} сек, переподключаюсь...")
#                     self.cap.release()
#                     self.cap = None
#                     continue
#
#                 time_since_last = current_time - last_processing_time
#
#                 should_process = (
#                         frame_counter <= 10 or
#                         frame_counter % 6 == 0 or  # Увеличили с 5 до 6
#                         time_since_last > self.processing_interval or
#                         (frame_counter > 10 and time_since_last > 4)
#                 )
#
#                 if should_process:
#                     last_processing_time = current_time
#
#                     # Добавляем кадр в очередь для обработки (неблокирующая)
#                     try:
#                         self.frame_queue.put_nowait((frame.copy(), frame_counter))
#                     except queue.Full:
#                         pass  # Пропускаем кадр если очередь переполнена
#
#                     if frame_counter % 30 == 0:
#                         print(f"[INFO] Кадр #{frame_counter} добавлен в очередь")
#
#             except Exception as e:
#                 print(f"[ERROR] Исключение в _update: {e}")
#                 import traceback
#                 traceback.print_exc()
#                 time.sleep(0.5)
#
#     def _process_frame_async(self, frame, frame_counter):
#         """Асинхронная обработка кадра с обновлением статистики"""
#         try:
#             # Уменьшаем разрешение для обработки
#             h, w = frame.shape[:2]
#             if w > 640:
#                 scale = 640 / w
#                 new_w, new_h = 640, int(h * scale)
#                 small_frame = cv2.resize(frame, (new_w, new_h))
#                 scale_factor = w / new_w
#             else:
#                 small_frame = frame
#                 scale_factor = 1.0
#
#             with self.lock:
#                 self.current_processing_frame = frame.copy()
#                 self.current_processing_plate = "обработка..."
#                 self.current_processing_access = "..."
#                 self.current_processing_code = "processing"
#             plate_info = self._recognize_plate_optimized(small_frame)
#             if plate_info.get('bbox') and scale_factor != 1.0:
#                 x1, y1, x2, y2 = plate_info['bbox']
#                 plate_info['bbox'] = (int(x1 * scale_factor), int(y1 * scale_factor),
#                                       int(x2 * scale_factor), int(y2 * scale_factor))
#
#             plate_full = plate_info.get('full', '')
#             plate_main = plate_info.get('main', '')
#             plate_region = plate_info.get('region', '')
#             confidence = plate_info.get('confidence', 0.0)
#             plate_rect = plate_info.get('bbox', None)
#
#             access_result, access_code = self._check_access(plate_full, plate_main)
#
#             # Обновляем статистику
#             with self.lock:
#                 self.stats['total_processed'] += 1
#
#                 if access_code == 'permanent':
#                     self.stats['permanent'] += 1
#                     self.stats['successful'] += 1
#                 elif access_code == 'temporary':
#                     self.stats['temporary'] += 1
#                     self.stats['successful'] += 1
#                 elif access_code == 'denied':
#                     self.stats['denied'] += 1
#
#             # Создаем обработанный кадр
#             processed_frame = frame.copy()
#             if plate_rect:
#                 x1, y1, x2, y2 = plate_rect
#                 color = (0, 255, 0) if access_code in ['permanent', 'temporary'] else (0, 0, 255)
#
#                 cv2.rectangle(processed_frame, (x1, y1), (x2, y2), color, 2)
#
#                 if plate_full:
#                     cv2.putText(processed_frame, plate_full, (x1, y1 - 5),
#                                 cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
#
#             status_color = self._get_color_for_code(access_code)
#             cv2.putText(processed_frame, f"{access_result[:15]}", (5, 25),
#                         cv2.FONT_HERSHEY_SIMPLEX, 0.4, status_color, 1)
#
#             cv2.putText(processed_frame, datetime.now().strftime('%H:%M:%S'), (5, 45),
#                         cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
#
#             with self.lock:
#                 self.last_processed_frame = processed_frame
#                 self.last_plate_full = plate_full
#                 self.last_plate_main = plate_main
#                 self.last_plate_region = plate_region
#                 self.last_access_result = access_result
#                 self.last_access_code = access_code
#
#                 # Обновляем очередь обработки реже
#                 if frame_counter % 4 == 0:
#                     queue_entry = {
#                         'plate': plate_full,
#                         'plate_main': plate_main,
#                         'plate_region': plate_region,
#                         'access': access_result,
#                         'code': access_code,
#                         'confidence': round(confidence, 2),
#                         'timestamp': datetime.now().strftime('%H:%M:%S'),
#                     }
#
#                     self.processing_queue.append(queue_entry)
#                     if len(self.processing_queue) > self.max_queue_size:
#                         self.processing_queue.pop(0)
#
#                 # В историю добавляем все распознанные номера
#                 if plate_full:
#                     history_entry = {
#                         'plate': plate_full,
#                         'plate_main': plate_main,
#                         'plate_region': plate_region,
#                         'access': access_result,
#                         'code': access_code,
#                         'confidence': round(confidence, 2),
#                         'time': datetime.now().strftime('%H:%M:%S'),
#                     }
#
#                     self.recognition_history.append(history_entry)
#                     if len(self.recognition_history) > self.max_history:
#                         self.recognition_history.pop(0)
#
#             if plate_full and confidence > 0.3:
#                 print(f"[INFO] Кадр #{frame_counter}: {plate_full} (увер:{confidence:.2f}, стат:{access_code})")
#
#             # Периодическая очистка памяти
#             if frame_counter % 30 == 0:
#                 gc.collect()
#                 if torch.cuda.is_available():
#                     torch.cuda.empty_cache()
#
#         except Exception as e:
#             print(f"[ERROR] Ошибка в _process_frame_async: {e}")
#
#     def _recognize_plate_optimized(self, frame):
#         """Максимально оптимизированное распознавание"""
#         result = {
#             'full': '', 'main': '', 'region': '',
#             'confidence': 0.0, 'bbox': None
#         }
#
#         try:
#             if frame is None or self.detector is None:
#                 return result
#
#             # Ограничиваем размер входного кадра для YOLO
#             h, w = frame.shape[:2]
#             if w > 640 or h > 480:
#                 scale = min(640 / w, 480 / h)
#                 new_w, new_h = int(w * scale), int(h * scale)
#                 processed_frame = cv2.resize(frame, (new_w, new_h))
#                 scale_factor = scale
#             else:
#                 processed_frame = frame
#                 scale_factor = 1.0
#             # Детекция с оптимальными параметрами
#             results = self.detector(
#                 processed_frame,
#                 conf=0.15,  # Низкий порог для лучшей детекции
#                 iou=0.4,
#                 max_det=3,  # Уменьшаем до 3 объектов
#                 verbose=False
#             )
#             best_plate = None
#             best_bbox = None
#             best_confidence = 0.0
#
#             for r in results:
#                 if r.boxes is None:
#                     continue
#
#                 for box in r.boxes:
#                     x1, y1, x2, y2 = map(int, box.xyxy[0])
#                     det_conf = float(box.conf[0])
#
#                     if scale_factor != 1.0:
#                         x1 = int(x1 / scale_factor)
#                         y1 = int(y1 / scale_factor)
#                         x2 = int(x2 / scale_factor)
#                         y2 = int(y2 / scale_factor)
#
#                     # Проверяем что координаты в пределах кадра
#                     h_orig, w_orig = frame.shape[:2]
#                     x1 = max(0, min(x1, w_orig - 1))
#                     y1 = max(0, min(y1, h_orig - 1))
#                     x2 = max(x1 + 1, min(x2, w_orig))
#                     y2 = max(y1 + 1, min(y2, h_orig))
#
#                     plate_crop = frame[y1:y2, x1:x2]
#                     if plate_crop.size < 100:  # Слишком маленькая область
#                         continue
#
#                     # Минимальная предобработка для OCR
#                     try:
#                         plate_crop = cv2.resize(plate_crop, None, fx=2, fy=2)
#                         gray = cv2.cvtColor(plate_crop, cv2.COLOR_BGR2GRAY)
#                         # Простая бинаризация
#                         _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
#                     except:
#                         continue
#
#                     if self.reader:
#                         # Одна попытка распознавания (без множественных методов)
#                         ocr_res = self.reader.readtext(
#                             binary,
#                             allowlist=ALLOWED_CHARS,
#                             paragraph=False,
#                             low_text=0.3,
#                             text_threshold=0.4,  # Понижаем порог
#                             width_ths=0.5,
#                             height_ths=0.3,
#                             decoder='greedy',
#                             beamWidth=5
#                         )
#
#                         if ocr_res:
#                             text = ''.join([r[1] for r in ocr_res])
#                             avg_conf = sum([r[2] for r in ocr_res]) / len(ocr_res)
#
#                             parsed = self._parse_russian_plate(text)
#                             combined_conf = det_conf * avg_conf * 1.2  # Бонус за успешное распознавание
#
#                             if parsed['full'] and combined_conf > best_confidence:
#                                 best_confidence = min(combined_conf, 1.0)
#                                 best_bbox = (x1, y1, x2, y2)
#                                 best_plate = parsed
#             print("best_plate", best_plate)
#             if best_plate and best_confidence > 0:
#                 result.update({
#                     'full': best_plate['full'],
#                     'main': best_plate['main'],
#                     'region': best_plate['region'],
#                     'confidence': best_confidence,
#                     'bbox': best_bbox
#                 })
#
#             return result
#
#         except Exception as e:
#             print(f'ОШИБКА -> {e}')
#             return result
#
#     def _parse_russian_plate(self, text):
#         """Парсинг российского автомобильного номера"""
#         if not text or len(text) < 6:
#             return {'full': '', 'main': '', 'region': ''}
#
#         clean_text = re.sub(r'[^A-Z0-9А-Я]', '', text).upper()
#
#         main_pattern = r'([' + RUSSIAN_LETTERS + r'])(\d{3})([' + RUSSIAN_LETTERS + r']{2})'
#         main_match = re.search(main_pattern, clean_text)
#
#         if main_match:
#             main_part = main_match.group(0)
#             remaining = clean_text[main_match.end():]
#
#             region_match = re.search(r'(\d{2,3})', remaining)
#
#             if region_match:
#                 region = region_match.group(0)
#                 try:
#                     region_int = int(region)
#                     if 1 <= region_int <= 999:
#                         return {
#                             'full': main_part + region,
#                             'main': main_part,
#                             'region': region
#                         }
#                 except:
#                     pass
#
#             return {
#                 'full': main_part,
#                 'main': main_part,
#                 'region': ''
#             }
#
#         # Упрощенный парсинг для нестандартных случаев
#         letters = [c for c in clean_text if c in RUSSIAN_LETTERS]
#         digits = [c for c in clean_text if c.isdigit()]
#
#         if len(letters) >= 3 and len(digits) >= 5:
#             return {
#                 'full': clean_text,
#                 'main': clean_text[:6] if len(clean_text) >= 6 else clean_text,
#                 'region': clean_text[6:] if len(clean_text) > 6 else ''
#             }
#
#         return {'full': '', 'main': '', 'region': ''}
#
#     def _check_access(self, plate_full, plate_main):
#         """Проверка доступа по номеру"""
#         if not plate_full and not plate_main:
#             return "Номер не распознан", "unrecognized"
#
#         def normalize(p):
#             return re.sub(r'[^A-Z0-9А-Я]', '', p).upper() if p else ""
#
#         if plate_full:
#             try:
#                 lp = LicensePlate.objects.get(plate_number=normalize(plate_full))
#                 return self._check_pass(lp)
#             except:
#                 pass
#
#         if plate_main:
#             try:
#                 lp = LicensePlate.objects.get(plate_number=normalize(plate_main))
#                 return self._check_pass(lp)
#             except:
#                 pass
#
#         return "Доступ запрещён", "denied"
#
#     def _check_pass(self, lp):
#         """Проверка пропуска"""
#         try:
#             passes = Pass.objects.filter(
#                 license_plate=lp,
#                 start_date__lte=datetime.now().date()
#             )
#
#             if not passes.exists():
#                 return "Доступ запрещён", "denied"
#
#             p = passes.first()
#             if p.pass_type == 'permanent':
#                 return "Постоянный, въезд разрешён", "permanent"
#             else:
#                 if p.end_date and p.end_date >= datetime.now().date():
#                     return "Временный, ручной контроль", "temporary"
#                 return "Доступ запрещён", "denied"
#         except:
#             return "Ошибка проверки", "error"
#
#     def _get_color_for_code(self, code):
#         """Возвращает цвет BGR для статуса доступа"""
#         colors = {
#             'permanent': (0, 255, 0),
#             'temporary': (0, 255, 255),
#             'denied': (0, 0, 255),
#             'unrecognized': (128, 128, 128),
#             'error': (255, 0, 255),
#             'processing': (255, 255, 0)
#         }
#         return colors.get(code, (255, 255, 255))
#
#     def get_frame(self):
#         with self.lock:
#             if self.last_frame is None:
#                 return None
#             ret, jpeg = cv2.imencode('.jpg', self.last_frame)
#             return jpeg.tobytes() if ret else None
#
#     def get_processed_frame(self):
#         with self.lock:
#             if self.last_processed_frame is None:
#                 return None
#             ret, jpeg = cv2.imencode('.jpg', self.last_processed_frame)
#             return jpeg.tobytes() if ret else None
#
#     def get_status(self):
#         with self.lock:
#             return {
#                 'plate': self.last_plate_full,
#                 'plate_main': self.last_plate_main,
#                 'plate_region': self.last_plate_region,
#                 'access': self.last_access_result,
#                 'code': self.last_access_code
#             }
#
#     def get_last_successful(self):
#         with self.lock:
#             if self.last_successful_frame is None:
#                 return None
#             ret, jpeg = cv2.imencode('.jpg', self.last_successful_frame)
#             if not ret:
#                 return None
#             return {
#                 'frame': jpeg.tobytes(),
#                 'plate': self.last_successful_plate_full,
#                 'access': self.last_successful_access,
#                 'code': self.last_successful_code,
#                 'time': self.last_successful_time.strftime('%H:%M:%S') if self.last_successful_time else None
#             }
#
#     def get_recognition_history(self):
#         with self.lock:
#             return self.recognition_history.copy()
#
#     def get_current_processing(self):
#         with self.lock:
#             if self.current_processing_frame is None:
#                 return None
#             ret, jpeg = cv2.imencode('.jpg', self.current_processing_frame)
#             if not ret:
#                 return None
#             return {
#                 'frame': jpeg.tobytes(),
#                 'plate': self.current_processing_plate,
#                 'access': self.current_processing_access,
#                 'code': self.current_processing_code
#             }
#
#     def get_processing_queue(self):
#         with self.lock:
#             return [{
#                 'plate': e['plate'],
#                 'plate_main': e.get('plate_main', ''),
#                 'plate_region': e.get('plate_region', ''),
#                 'access': e['access'],
#                 'code': e['code'],
#                 'confidence': e['confidence'],
#                 'timestamp': e['timestamp']
#             } for e in self.processing_queue[-10:]]
#
#     def get_stats(self):
#         """Получение статистики распознаваний"""
#         with self.lock:
#             return self.stats.copy()
#
#     def stop(self):
#         self.stopped = True
#         self.stop_workers.set()
#
#         # Очищаем очередь
#         while not self.frame_queue.empty():
#             try:
#                 self.frame_queue.get_nowait()
#             except queue.Empty:
#                 break
#
#         if self.cap:
#             self.cap.release()
#
#         # Очищаем GPU память
#         if torch.cuda.is_available():
#             torch.cuda.empty_cache()
#         gc.collect()
#         print("[INFO] Ресурсы освобождены")

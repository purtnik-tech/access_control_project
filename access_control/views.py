"""
Представления (views) для системы контроля доступа.
Обрабатывают HTTP-запросы и возвращают ответы: HTML страницы,
изображения, JSON данные и MJPEG видеопотоки.
"""

from django.shortcuts import render
from django.http import StreamingHttpResponse, HttpResponse, JsonResponse
from django.views.decorators import gzip
import time
import threading
from typing import Optional, Generator, Dict, Any, List

from .camera_stream import CameraStream

# Глобальные переменные для управления единственным экземпляром камеры
_camera_stream: Optional[CameraStream] = None  # Экземпляр потока камеры
_camera_lock: threading.Lock = threading.Lock()  # Блокировка для потокобезопасности
_camera_initializing: bool = False  # Флаг, указывающий что камера инициализируется


def get_camera_stream() -> Optional[CameraStream]:
    """
    Получение или создание экземпляра потока камеры (ленивая инициализация с синглтоном).

    Реализует потокобезопасный паттерн Singleton с ожиданием инициализации.

    Returns:
        Optional[CameraStream]: Экземпляр потока камеры или None в случае ошибки

    Raises:
        RuntimeError: Если не удалось инициализировать камеру в течение таймаута
    """
    global _camera_stream, _camera_initializing

    # Быстрая проверка без блокировки
    if _camera_stream is not None:
        return _camera_stream

    # Блокируем для потокобезопасности
    with _camera_lock:
        # Проверяем ещё раз после получения блокировки
        if _camera_stream is not None:
            return _camera_stream

        # Если камера уже инициализируется в другом потоке - ждём
        if _camera_initializing:
            print("[INFO] Ожидание инициализации камеры...")
            for attempt in range(20):  # Максимум 20 попыток * 0.5 сек = 10 секунд
                time.sleep(0.5)
                if _camera_stream is not None:
                    return _camera_stream
            print("[WARN] Таймаут ожидания инициализации камеры")

        # Помечаем, что начинаем инициализацию
        _camera_initializing = True

        try:
            print(f"[INFO] Инициализация камеры...")

            # URL RTSP потока камеры (замените на свой)
            camera_url: str = "rtsp://admin:123qweQWE@10.2.26.3:554/stream"

            # Создаём экземпляр потока камеры
            _camera_stream = CameraStream(camera_source=camera_url, use_network=True)

            start_time: float = time.time()
            timeout: int = 15  # Таймаут инициализации 15 секунд

            # Запускаем инициализацию в отдельном потоке
            def init_camera() -> None:
                """Внутренняя функция для инициализации камеры в отдельном потоке."""
                try:
                    _camera_stream.start()
                except Exception as e:
                    print(f"[ERROR] Ошибка инициализации камеры: {e}")

            init_thread: threading.Thread = threading.Thread(target=init_camera)
            init_thread.daemon = True  # Поток завершится при завершении основного
            init_thread.start()

            # Ожидаем завершения инициализации с таймаутом
            while time.time() - start_time < timeout:
                time.sleep(0.5)
                # Проверяем, открылась ли камера
                if hasattr(_camera_stream, 'cap') and _camera_stream.cap is not None:
                    if _camera_stream.cap.isOpened():
                        print(f"[INFO] Камера успешно инициализирована")
                        _camera_initializing = False
                        return _camera_stream

            # Если дошли сюда - таймаут
            print(f"[ERROR] Таймаут инициализации камеры")
            _camera_stream = None
            _camera_initializing = False
            raise RuntimeError("Таймаут инициализации камеры")

        except Exception as e:
            print(f"[ERROR] Ошибка при создании камеры: {e}")
            _camera_stream = None
            _camera_initializing = False
            raise

    return _camera_stream


def index(request) -> HttpResponse:
    """
    Главная страница с веб-интерфейсом системы контроля доступа.

    Args:
        request: HTTP запрос

    Returns:
        HttpResponse: HTML страница
    """
    return render(request, 'access_control/index.html')


@gzip.gzip_page
def video_feed(request) -> StreamingHttpResponse | HttpResponse:
    """
    MJPEG поток для отображения live видео с камеры.
    Используется в теге <img src="..."> для непрерывного видео.

    Args:
        request: HTTP запрос

    Returns:
        StreamingHttpResponse: Бесконечный MJPEG поток
    """
    stream: Optional[CameraStream] = get_camera_stream()
    if stream is None:
        return HttpResponse(status=503)  # Service Unavailable

    def generate() -> Generator[bytes, None, None]:
        """
        Генератор MJPEG потока.
        Отправляет кадры как multipart/x-mixed-replace.
        """
        while True:
            try:
                # Получаем текущий кадр
                frame: Optional[bytes] = stream.get_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue

                # Отправляем кадр в MJPEG формате
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            except GeneratorExit:
                # Клиент закрыл соединение
                break
            except Exception as e:
                # Ошибка при отправке
                break

    return StreamingHttpResponse(
        generate(),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


def last_processed_frame(request) -> HttpResponse:
    """
    Получение последнего обработанного кадра.

    Args:
        request: HTTP запрос

    Returns:
        HttpResponse: JPEG изображение или 204 No Content
    """
    stream: Optional[CameraStream] = get_camera_stream()
    if stream is None:
        return HttpResponse(status=503)

    frame: Optional[bytes] = stream.get_processed_frame()
    if frame is None:
        return HttpResponse(status=204)  # No Content
    return HttpResponse(frame, content_type='image/jpeg')


def recognition_status(request) -> JsonResponse:
    """
    Получение статуса последнего распознавания в формате JSON.

    Args:
        request: HTTP запрос

    Returns:
        JsonResponse: Статус распознавания
    """
    stream: Optional[CameraStream] = get_camera_stream()
    if stream is None:
        return JsonResponse({'error': 'Camera not initialized'}, status=503)

    status: Dict[str, str] = stream.get_status()
    return JsonResponse(status)


def last_successful_frame(request) -> HttpResponse:
    """
    Получение кадра с последним успешным распознаванием.

    Args:
        request: HTTP запрос

    Returns:
        HttpResponse: JPEG изображение или 204 No Content
    """
    stream: Optional[CameraStream] = get_camera_stream()
    if stream is None:
        return HttpResponse(status=503)

    successful_data: Optional[Dict[str, Any]] = stream.get_last_successful()
    if successful_data is None or successful_data['frame'] is None:
        return HttpResponse(status=204)
    return HttpResponse(successful_data['frame'], content_type='image/jpeg')


def last_successful_data(request) -> JsonResponse:
    """
    Получение данных последнего успешного распознавания в формате JSON.

    Args:
        request: HTTP запрос

    Returns:
        JsonResponse: Данные успешного распознавания
    """
    stream: Optional[CameraStream] = get_camera_stream()
    if stream is None:
        return JsonResponse({'exists': False, 'error': 'Camera not initialized'})

    successful_data: Optional[Dict[str, Any]] = stream.get_last_successful()
    if successful_data is None:
        return JsonResponse({'exists': False})

    return JsonResponse({
        'exists': True,
        'plate': successful_data['plate'],
        'access': successful_data['access'],
        'code': successful_data['code'],
        'time': successful_data['time']
    })


def recognition_history(request) -> JsonResponse:
    """
    Получение истории распознаваний в формате JSON.

    Args:
        request: HTTP запрос

    Returns:
        JsonResponse: История распознаваний
    """
    stream: Optional[CameraStream] = get_camera_stream()
    if stream is None:
        return JsonResponse({'history': [], 'error': 'Camera not initialized'})

    history: List[Dict[str, Any]] = stream.get_recognition_history()
    return JsonResponse({'history': history})


def current_processing_frame(request) -> HttpResponse:
    """
    Получение текущего обрабатываемого кадра.

    Args:
        request: HTTP запрос

    Returns:
        HttpResponse: JPEG изображение или 204 No Content
    """
    stream: Optional[CameraStream] = get_camera_stream()
    if stream is None:
        return HttpResponse(status=503)

    data: Optional[Dict[str, Any]] = stream.get_current_processing()
    if data is None or data['frame'] is None:
        return HttpResponse(status=204)
    return HttpResponse(data['frame'], content_type='image/jpeg')


def current_processing_status(request) -> JsonResponse:
    """
    Получение статуса текущего обрабатываемого кадра в формате JSON.

    Args:
        request: HTTP запрос

    Returns:
        JsonResponse: Статус текущей обработки
    """
    stream: Optional[CameraStream] = get_camera_stream()
    if stream is None:
        return JsonResponse({
            'plate': '',
            'access': 'Камера не инициализирована',
            'code': 'error'
        })

    data: Optional[Dict[str, Any]] = stream.get_current_processing()
    if data is None:
        return JsonResponse({
            'plate': '',
            'access': 'Ожидание...',
            'code': 'processing'
        })

    return JsonResponse({
        'plate': data['plate'],
        'access': data['access'],
        'code': data['code']
    })


def processing_queue(request) -> JsonResponse:
    """
    Получение очереди обработанных кадров в формате JSON.

    Args:
        request: HTTP запрос

    Returns:
        JsonResponse: Очередь обработанных кадров
    """
    stream: Optional[CameraStream] = get_camera_stream()
    if stream is None:
        return JsonResponse({'queue': []})

    queue_data: List[Dict[str, Any]] = stream.get_processing_queue()
    return JsonResponse({'queue': queue_data})


def stats_info(request) -> JsonResponse:
    """
    Получение статистики распознаваний в формате JSON.

    Args:
        request: HTTP запрос

    Returns:
        JsonResponse: Статистика распознаваний
    """
    stream: Optional[CameraStream] = get_camera_stream()
    if stream is None:
        return JsonResponse({'error': 'Camera not initialized'})

    stats: Dict[str, int] = stream.get_stats()
    return JsonResponse(stats)
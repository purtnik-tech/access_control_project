from django.shortcuts import render
from django.http import StreamingHttpResponse, HttpResponse, JsonResponse
from django.views.decorators import gzip
import time
import threading
from datetime import datetime
from .camera_stream import CameraStream

_camera_stream = None
_camera_lock = threading.Lock()
_camera_initializing = False


def get_camera_stream():
    global _camera_stream, _camera_initializing

    if _camera_stream is not None:
        return _camera_stream

    with _camera_lock:
        if _camera_stream is not None:
            return _camera_stream

        if _camera_initializing:
            print("[INFO] Ожидание инициализации камеры...")
            for _ in range(20):
                time.sleep(0.5)
                if _camera_stream is not None:
                    return _camera_stream
            print("[WARN] Таймаут ожидания инициализации камеры")

        _camera_initializing = True

        try:
            print(f"[INFO] Инициализация камеры...")

            # ВАШ РЕАЛЬНЫЙ URL КАМЕРЫ
            camera_url = "rtsp://admin:123qweQWE@10.2.26.3:554/stream"

            _camera_stream = CameraStream(camera_source=camera_url, use_network=True)

            start_time = time.time()
            timeout = 15

            def init_camera():
                try:
                    _camera_stream.start()
                except Exception as e:
                    print(f"[ERROR] Ошибка инициализации камеры: {e}")

            init_thread = threading.Thread(target=init_camera)
            init_thread.daemon = True
            init_thread.start()

            while time.time() - start_time < timeout:
                time.sleep(0.5)
                if hasattr(_camera_stream, 'cap') and _camera_stream.cap is not None:
                    if _camera_stream.cap.isOpened():
                        print(f"[INFO] Камера успешно инициализирована")
                        _camera_initializing = False
                        return _camera_stream

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


def index(request):
    return render(request, 'access_control/index.html')


@gzip.gzip_page
def video_feed(request):
    stream = get_camera_stream()
    if stream is None:
        return HttpResponse(status=503)

    def generate():
        while True:
            try:
                frame = stream.get_frame()
                if frame is None:
                    time.sleep(0.1)
                    continue

                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
            except GeneratorExit:
                break
            except Exception as e:
                break

    return StreamingHttpResponse(generate(),
                                 content_type='multipart/x-mixed-replace; boundary=frame')


def last_processed_frame(request):
    stream = get_camera_stream()
    if stream is None:
        return HttpResponse(status=503)

    frame = stream.get_processed_frame()
    if frame is None:
        return HttpResponse(status=204)
    return HttpResponse(frame, content_type='image/jpeg')


def recognition_status(request):
    stream = get_camera_stream()
    if stream is None:
        return JsonResponse({'error': 'Camera not initialized'}, status=503)

    status = stream.get_status()
    return JsonResponse(status)


def last_successful_frame(request):
    stream = get_camera_stream()
    if stream is None:
        return HttpResponse(status=503)

    successful_data = stream.get_last_successful()
    if successful_data is None or successful_data['frame'] is None:
        return HttpResponse(status=204)
    return HttpResponse(successful_data['frame'], content_type='image/jpeg')


def last_successful_data(request):
    stream = get_camera_stream()
    if stream is None:
        return JsonResponse({'exists': False, 'error': 'Camera not initialized'})

    successful_data = stream.get_last_successful()
    if successful_data is None:
        return JsonResponse({'exists': False})

    return JsonResponse({
        'exists': True,
        'plate': successful_data['plate'],
        'access': successful_data['access'],
        'code': successful_data['code'],
        'time': successful_data['time']
    })


def recognition_history(request):
    stream = get_camera_stream()
    if stream is None:
        return JsonResponse({'history': [], 'error': 'Camera not initialized'})

    history = stream.get_recognition_history()
    return JsonResponse({'history': history})


def current_processing_frame(request):
    stream = get_camera_stream()
    if stream is None:
        return HttpResponse(status=503)

    data = stream.get_current_processing()
    if data is None or data['frame'] is None:
        return HttpResponse(status=204)
    return HttpResponse(data['frame'], content_type='image/jpeg')


def current_processing_status(request):
    stream = get_camera_stream()
    if stream is None:
        return JsonResponse({'plate': '', 'access': 'Камера не инициализирована', 'code': 'error'})

    data = stream.get_current_processing()
    if data is None:
        return JsonResponse({'plate': '', 'access': 'Ожидание...', 'code': 'processing'})
    return JsonResponse({
        'plate': data['plate'],
        'access': data['access'],
        'code': data['code']
    })


def processing_queue(request):
    stream = get_camera_stream()
    if stream is None:
        return JsonResponse({'queue': []})

    queue = stream.get_processing_queue()
    return JsonResponse({'queue': queue})


def stats_info(request):
    """Получение статистики"""
    stream = get_camera_stream()
    if stream is None:
        return JsonResponse({'error': 'Camera not initialized'})

    stats = stream.get_stats()
    return JsonResponse(stats)
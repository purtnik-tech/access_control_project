from django.shortcuts import render
from django.http import StreamingHttpResponse, HttpResponse, JsonResponse
from django.views.decorators import gzip
import time
from .camera_stream import CameraStream

_camera_stream = None


def get_camera_stream():
    global _camera_stream
    if _camera_stream is None:
        # Для сетевой камеры (RTSP поток)
        camera_url = "rtsp://admin:password@10.2.26.25:554/stream"
        _camera_stream = CameraStream(camera_source=camera_url, use_network=True)
        _camera_stream.start()
    return _camera_stream


def index(request):
    return render(request, 'access_control/index.html')


@gzip.gzip_page
def video_feed(request):
    stream = get_camera_stream()

    def generate():
        while True:
            frame = stream.get_frame()
            if frame is None:
                time.sleep(0.1)
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

    return StreamingHttpResponse(generate(),
                                 content_type='multipart/x-mixed-replace; boundary=frame')


def last_processed_frame(request):
    stream = get_camera_stream()
    frame = stream.get_processed_frame()
    if frame is None:
        return HttpResponse(status=204)
    return HttpResponse(frame, content_type='image/jpeg')


def recognition_status(request):
    stream = get_camera_stream()
    status = stream.get_status()
    return JsonResponse(status)


def last_successful_frame(request):
    """Получить кадр последнего успешного распознавания"""
    stream = get_camera_stream()
    successful_data = stream.get_last_successful()
    if successful_data is None or successful_data['frame'] is None:
        return HttpResponse(status=204)
    return HttpResponse(successful_data['frame'], content_type='image/jpeg')


def last_successful_data(request):
    """Получить данные последнего успешного распознавания"""
    stream = get_camera_stream()
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
    """Получить историю распознаваний"""
    stream = get_camera_stream()
    history = stream.get_recognition_history()
    return JsonResponse({'history': history})
from django.shortcuts import render
from django.http import StreamingHttpResponse, HttpResponse, JsonResponse
from django.views.decorators import gzip
import cv2
from .camera_stream import CameraStream

# Получаем ссылку на поток (инициализируем при первом обращении)
_camera_stream = None

def get_camera_stream():
    global _camera_stream
    if _camera_stream is None:
        _camera_stream = CameraStream(camera_id=0)
        _camera_stream.start()
    return _camera_stream

def index(request):
    return render(request, 'access_control/index.html')

@gzip.gzip_page
def video_feed(request):
    """MJPEG поток live видео."""
    stream = get_camera_stream()
    def generate():
        while True:
            frame = stream.get_frame()
            if frame is None:
                continue
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')
    return StreamingHttpResponse(generate(),
                                 content_type='multipart/x-mixed-replace; boundary=frame')

def last_processed_frame(request):
    """Последний кадр, на котором производилось распознавание."""
    stream = get_camera_stream()
    frame = stream.get_processed_frame()
    if frame is None:
        return HttpResponse(status=204)
    return HttpResponse(frame, content_type='image/jpeg')

def recognition_status(request):
    """JSON с результатами последнего распознавания."""
    stream = get_camera_stream()
    status = stream.get_status()
    return JsonResponse(status)
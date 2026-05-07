import torch
from django.http import HttpResponseNotAllowed, StreamingHttpResponse, JsonResponse
from easyocr import easyocr
from ultralytics import YOLO

from camera_stream.camera.stream import mjpeg_stream
from camera_stream.camera.registry import get_camera
from processing.frame_analyzer import YoloFrameAnalyzer
from processing.frame_processor import FrameProcessor


def camera_stream_view(request):
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    return StreamingHttpResponse(mjpeg_stream(), content_type='multipart/x-mixed-replace; boundary=frame')


def tst(request):
    analyzer = YoloFrameAnalyzer(YOLO('yolov8m.pt'), easyocr.Reader(
            ['ru', 'en'],
                gpu=True if torch.cuda.is_available() else False,
                model_storage_directory='~/.easyocr/model',
                download_enabled=True,
                verbose=False
            ))
    processor = FrameProcessor(get_camera(), analyzer, FrameProcessor.Mode.ULTRA_SLOW)
    processor.run()
    return JsonResponse({'test': 'test'})
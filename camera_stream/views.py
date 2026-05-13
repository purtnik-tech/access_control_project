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

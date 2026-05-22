import os

from django.core.management import BaseCommand

from camera_stream.camera.registry import get_camera
from processing.frame_analyzer import YoloFrameAnalyzer
from processing.frame_processor import FrameProcessor
from processing.utils.ocrs.easy_ocr import LicensePlateOCR
from processing.utils.detectors.yolo_detector import YoloDetector
from processing.handlers.base import NumberFrameHandler


class Command(BaseCommand):

    def handle(self, *args, **options):
        model_path = os.getenv('YOLO_MODEL_PATH')
        if not model_path:
            raise RuntimeError('YOLO_MODEL_PATH не задан в .env')
        analyzer = YoloFrameAnalyzer(YoloDetector(model_path), LicensePlateOCR())
        processor = FrameProcessor(get_camera(True), analyzer, NumberFrameHandler(), FrameProcessor.Mode.NORMAL)
        processor.loop()
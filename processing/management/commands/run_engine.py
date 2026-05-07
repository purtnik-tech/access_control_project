from django.core.management import BaseCommand

from camera_stream.camera.registry import get_camera
from processing.frame_analyzer import YoloFrameAnalyzer
from processing.frame_processor import FrameProcessor
from processing.utils.ocrs.easy_ocr import EasyOcrEngine
from processing.utils.detectors.yolo_detector import YoloDetector


class Command(BaseCommand):

    def handle(self, *args, **options):
        analyzer = YoloFrameAnalyzer(YoloDetector('yolov10x.pt'), EasyOcrEngine())
        processor = FrameProcessor(get_camera(), analyzer, FrameProcessor.Mode.REALTIME)
        processor.loop()
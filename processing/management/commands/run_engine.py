from django.core.management import BaseCommand

from camera_stream.camera.registry import get_camera
from processing.frame_analyzer import YoloFrameAnalyzer
from processing.frame_processor import FrameProcessor
from processing.utils.ocrs.easy_ocr import LicensePlateOCR
from processing.utils.detectors.yolo_detector import YoloDetector


LICENSE_PLATE_DETECT_MODEL_PATH = 'C:\\Users\\localadmin\\PycharmProjects\\access_control_project\\tools\\train\\car_license\\best.pt'


class Command(BaseCommand):

    def handle(self, *args, **options):
        analyzer = YoloFrameAnalyzer(YoloDetector(LICENSE_PLATE_DETECT_MODEL_PATH), LicensePlateOCR())
        processor = FrameProcessor(get_camera(), analyzer, FrameProcessor.Mode.FAST)
        processor.loop()
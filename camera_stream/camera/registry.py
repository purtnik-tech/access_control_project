import os

from dotenv import load_dotenv
from .service import CameraStream, CameraStreamOCR


load_dotenv()


CAMERA_LOGIN = os.getenv('CAMERA_LOGIN')
CAMERA_PASS = os.getenv('CAMERA_PASS')
CAMERA_IP = os.getenv('CAMERA_IP')
_camera = None
_camera_ocr = None


def get_camera(ocr: bool = False) -> CameraStream | CameraStreamOCR:
    """
    :return:
    """
    global _camera, _camera_ocr
    if not _camera and not ocr:
        _camera = CameraStream(f'rtsp://{CAMERA_LOGIN}:{CAMERA_PASS}@{CAMERA_IP}/Streaming/Channels/101?tcp')
    elif not _camera_ocr and ocr:
        _camera_ocr = CameraStreamOCR(f'rtsp://{CAMERA_LOGIN}:{CAMERA_PASS}@{CAMERA_IP}/Streaming/Channels/101?tcp')
    if ocr:
        return _camera_ocr
    return _camera

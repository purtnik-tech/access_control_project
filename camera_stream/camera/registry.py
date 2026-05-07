import os

from dotenv import load_dotenv
from .service import CameraStream


load_dotenv()


CAMERA_LOGIN = os.getenv('CAMERA_LOGIN')
CAMERA_PASS = os.getenv('CAMERA_PASS')
CAMERA_IP = os.getenv('CAMERA_IP')
_camera = None


def get_camera() -> CameraStream:
    """
    :return:
    """
    global _camera
    if not _camera:
        _camera = CameraStream(f'rtsp://{CAMERA_LOGIN}:{CAMERA_PASS}@{CAMERA_IP}/stream')
    return _camera

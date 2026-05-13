from time import sleep

import cv2

from camera_stream.camera.registry import get_camera


def mjpeg_stream():
    camera = get_camera()
    while True:
        if not (jpeg := camera.jpeg_frame):
            sleep(0.01)
            continue
        yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n'

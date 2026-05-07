from time import sleep

from camera_stream.camera.registry import get_camera


def mjpeg_stream():
    camera = get_camera()
    while True:
        if not (jpeg := camera.jpeg_frame):
            sleep(1)
            continue
        yield b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + jpeg + b'\r\n'
        sleep(0.03)
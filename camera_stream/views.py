from django.http import HttpResponseNotAllowed, StreamingHttpResponse

from camera_stream.camera.stream import mjpeg_stream


def camera_stream_view(request):
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    return StreamingHttpResponse(mjpeg_stream(), content_type='multipart/x-mixed-replace; boundary=frame')

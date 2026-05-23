from django.urls import path

from camera_stream import views


app_name = 'camera_stream'
urlpatterns = [
    path('stream/', views.camera_stream_view, name='camera_stream'),
]
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('video_feed/', views.video_feed, name='video_feed'),
    path('last_frame/', views.last_processed_frame, name='last_processed_frame'),
    path('status/', views.recognition_status, name='recognition_status'),
]
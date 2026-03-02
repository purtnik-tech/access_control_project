from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('video_feed/', views.video_feed, name='video_feed'),
    path('last_frame/', views.last_processed_frame, name='last_processed_frame'),
    path('status/', views.recognition_status, name='recognition_status'),
    path('last_successful_frame/', views.last_successful_frame, name='last_successful_frame'),
    path('last_successful_data/', views.last_successful_data, name='last_successful_data'),
    path('recognition_history/', views.recognition_history, name='recognition_history'),
]
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('video_feed/', views.video_feed, name='video_feed'),
    path('last_processed_frame/', views.last_processed_frame, name='last_processed_frame'),
    path('status/', views.recognition_status, name='recognition_status'),
    path('last_successful_frame/', views.last_successful_frame, name='last_successful_frame'),
    path('last_successful_data/', views.last_successful_data, name='last_successful_data'),
    path('recognition_history/', views.recognition_history, name='recognition_history'),
    path('current_processing_frame/', views.current_processing_frame, name='current_processing_frame'),
    path('current_processing_status/', views.current_processing_status, name='current_processing_status'),
    path('processing_queue/', views.processing_queue, name='processing_queue'),
    path('stats/', views.stats_info, name='stats_info'),  # НОВЫЙ МАРШРУТ
]
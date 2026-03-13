"""
URL-маршруты для приложения access_control.
Определяет соответствие между URL-адресами и функциями представлений (views).
"""

from django.urls import path
from django.urls.resolvers import URLPattern
from typing import List

from . import views

# Список всех URL-маршрутов приложения
urlpatterns: List[URLPattern] = [
    # === Основные страницы ===
    # Главная страница с интерфейсом системы контроля доступа
    path('', views.index, name='index'),

    # === Видеопотоки ===
    # MJPEG поток для отображения live видео с камеры
    path('video_feed/', views.video_feed, name='video_feed'),

    # === Обработанные кадры ===
    # Последний обработанный кадр (с наложенной информацией)
    path('last_processed_frame/', views.last_processed_frame, name='last_processed_frame'),

    # === Статус распознавания ===
    # Текущий статус распознавания (номер, доступ) в формате JSON
    path('status/', views.recognition_status, name='recognition_status'),

    # === Успешные распознавания ===
    # Кадр с последним успешно распознанным номером
    path('last_successful_frame/', views.last_successful_frame, name='last_successful_frame'),

    # Данные последнего успешного распознавания (номер, время, статус)
    path('last_successful_data/', views.last_successful_data, name='last_successful_data'),

    # === История ===
    # Полная история распознаваний в формате JSON
    path('recognition_history/', views.recognition_history, name='recognition_history'),

    # === Текущая обработка ===
    # Кадр, который сейчас обрабатывается
    path('current_processing_frame/', views.current_processing_frame, name='current_processing_frame'),

    # Статус текущего обрабатываемого кадра
    path('current_processing_status/', views.current_processing_status, name='current_processing_status'),

    # Очередь обработанных кадров (последние N результатов)
    path('processing_queue/', views.processing_queue, name='processing_queue'),

    # === Статистика ===
    # Статистика распознаваний (количество обработанных, успешных, отказов)
    path('stats/', views.stats_info, name='stats_info'),  # Эндпоинт для получения статистики
]
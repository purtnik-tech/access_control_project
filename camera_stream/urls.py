from django.urls import path, include

from camera_stream import views


# Список всех URL-маршрутов проекта
# Каждый элемент может быть либо URLPattern (конечный маршрут),
# либо URLResolver (включает другие URL-конфигурации)
urlpatterns = [
    path('stream/', views.camera_stream_view, name='camera_stream'),
]
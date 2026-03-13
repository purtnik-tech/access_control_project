"""
ASGI (Asynchronous Server Gateway Interface) конфигурация для проекта access_control_project.

ASGI является преемником WSGI и добавляет поддержку асинхронных протоколов,
таких как WebSockets, HTTP/2 и Server-Sent Events. Это стандарт для асинхронных
веб-приложений на Python.

Данный файл предоставляет точку входа ASGI-сервера (например, Uvicorn, Daphne)
для запуска Django приложения в асинхронном режиме.

Для получения дополнительной информации:
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
from typing import Any

from django.core.asgi import get_asgi_application
from django.core.handlers.asgi import ASGIHandler


# Устанавливаем модуль настроек Django по умолчанию для ASGI-сервера
# Это необходимо до загрузки любых компонентов Django
os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',  # Переменная окружения, указывающая на файл настроек
    'access_control_project.settings'  # Путь к модулю настроек проекта
)

# Создаем ASGI-приложение, которое будет обрабатывать входящие запросы
# get_asgi_application() инициализирует Django и возвращает ASGI-совместимый обработчик
# Этот объект будет использоваться ASGI-сервером для маршрутизации запросов
application: ASGIHandler = get_asgi_application()
"""
WSGI (Web Server Gateway Interface) конфигурация для проекта access_control_project.

WSGI - это стандартный интерфейс между веб-серверами и веб-приложениями на Python.
Он обеспечивает синхронное взаимодействие, когда каждый запрос обрабатывается
последовательно в отдельном потоке или процессе.

Данный файл предоставляет точку входа WSGI-сервера (например, Gunicorn, uWSGI, mod_wsgi)
для запуска Django приложения в production-среде.

Для получения дополнительной информации см. документацию:
https://docs.djangoproject.com/en/6.0/howto/deployment/wsgi/
"""

import os
from typing import Any

from django.core.wsgi import get_wsgi_application
from django.core.handlers.wsgi import WSGIHandler


# Устанавливаем модуль настроек Django по умолчанию для WSGI-сервера
# Это необходимо до загрузки любых компонентов Django, чтобы сервер знал,
# какой проект он запускает.
# setdefault() устанавливает значение только если переменная ещё не задана.
os.environ.setdefault(
    'DJANGO_SETTINGS_MODULE',  # Переменная окружения, указывающая на файл настроек
    'access_control_project.settings'  # Путь к модулю настроек проекта (в формате Python: 'пакет.модуль')
)

# Создаем WSGI-приложение, которое будет обрабатывать входящие запросы
# get_wsgi_application() инициализирует Django и возвращает WSGI-совместимый обработчик
# Этот объект будет использоваться WSGI-сервером для вызова приложения при каждом запросе
#
# Пример использования с Gunicorn:
#   gunicorn access_control_project.wsgi:application
#
# Пример использования с uWSGI:
#   uwsgi --module access_control_project.wsgi:application
application: WSGIHandler = get_wsgi_application()
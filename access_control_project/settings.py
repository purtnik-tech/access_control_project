"""
Настройки Django проекта access_control_project.

Этот файл содержит все конфигурационные параметры Django проекта:
база данных, установленные приложения, middleware, шаблоны и т.д.

Сгенерировано командой 'django-admin startproject' с использованием Django 6.0.2.

Для получения дополнительной информации см. документацию:
https://docs.djangoproject.com/en/6.0/topics/settings/
https://docs.djangoproject.com/en/6.0/ref/settings/
"""

from pathlib import Path
from typing import Dict, List, Tuple, Any

# === Базовые пути ===
# BASE_DIR - корневая директория проекта (где находится manage.py)
BASE_DIR: Path = Path(__file__).resolve().parent.parent


# === Настройки разработки ===
# ВНИМАНИЕ: Эти настройки НЕ подходят для продакшена!
# См. документацию по развертыванию:
# https://docs.djangoproject.com/en/6.0/howto/deployment/checklist/

# Секретный ключ Django - должен быть уникальным и действительно секретным!
# В продакшене должен храниться в переменных окружения
SECRET_KEY: str = 'django-insecure-wnmcwp1346vqb_cxbm)xeh=*!5)a=vj1o!qrsz_#-1f(fz$^g='

# Режим отладки - должен быть False в продакшене!
# Включенные подробные страницы ошибок могут раскрыть чувствительную информацию
DEBUG: bool = True

# Список разрешенных хостов для доступа к приложению
# В продакшене должен содержать доменные имена сервера
ALLOWED_HOSTS: List[str] = []


# === Приложения Django ===
# Список всех установленных приложений, включая встроенные и пользовательские
INSTALLED_APPS: List[str] = [
    # Встроенные приложения Django
    'django.contrib.admin',          # Административный интерфейс
    'django.contrib.auth',            # Система аутентификации
    'django.contrib.contenttypes',    # Фреймворк для работы с типами контента
    'django.contrib.sessions',        # Поддержка сессий
    'django.contrib.messages',        # Система сообщений
    'django.contrib.staticfiles',     # Управление статическими файлами

    # Пользовательские приложения проекта
    'access_control',
    'camera_stream',
    'processing'
]

# === Middleware ===
# Промежуточные слои, обрабатывающие запросы и ответы
# Выполняются в порядке сверху вниз для запросов и снизу вверх для ответов
MIDDLEWARE: List[str] = [
    'django.middleware.security.SecurityMiddleware',           # Безопасность
    'django.contrib.sessions.middleware.SessionMiddleware',   # Управление сессиями
    'django.middleware.common.CommonMiddleware',               # Общие функции (ETag и др.)
    'django.middleware.csrf.CsrfViewMiddleware',              # Защита от CSRF-атак
    'django.contrib.auth.middleware.AuthenticationMiddleware', # Аутентификация
    'django.contrib.messages.middleware.MessageMiddleware',   # Система сообщений
    'django.middleware.clickjacking.XFrameOptionsMiddleware', # Защита от clickjacking
]

# === Конфигурация URL ===
# Корневой модуль маршрутизации URL
ROOT_URLCONF: str = 'access_control_project.urls'

# === Конфигурация шаблонов ===
TEMPLATES: List[Dict[str, Any]] = [
    {
        # Движок шаблонов (Django templates)
        'BACKEND': 'django.template.backends.django.DjangoTemplates',

        # Дополнительные директории для поиска шаблонов
        'DIRS': [
            BASE_DIR / 'access_control/templates'  # Шаблоны приложения
        ],

        # Автоматический поиск шаблонов в директориях приложений
        'APP_DIRS': True,

        # Дополнительные контекстные процессоры
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',  # Добавляет request в контекст
                'django.contrib.auth.context_processors.auth',  # Добавляет user в контекст
                'django.contrib.messages.context_processors.messages',  # Добавляет messages
            ],
        },
    },
]

# === WSGI конфигурация ===
# Путь к WSGI-приложению для синхронных серверов
WSGI_APPLICATION: str = 'access_control_project.wsgi.application'


# === Настройки базы данных ===
# Поддерживаются: SQLite, PostgreSQL, MySQL, Oracle и др.
# https://docs.djangoproject.com/en/6.0/ref/settings/#databases
DATABASES: Dict[str, Dict[str, Any]] = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',  # Движок базы данных
        'NAME': BASE_DIR / 'db.sqlite3',          # Путь к файлу базы данных
    }
}


# === Валидация паролей ===
# Набор валидаторов для проверки сложности паролей
# Используются при смене пароля через встроенные формы
AUTH_PASSWORD_VALIDATORS: List[Dict[str, str]] = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
        # Проверяет, что пароль не похож на атрибуты пользователя
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        # Проверяет минимальную длину пароля
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
        # Проверяет, что пароль не слишком распространенный
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
        # Проверяет, что пароль не состоит только из цифр
    },
]


# === Интернационализация ===
# Настройки локализации и временных зон

# Код языка по умолчанию (ru-ru - русский)
LANGUAGE_CODE: str = 'ru-ru'

# Временная зона по умолчанию (UTC - всемирное координированное время)
TIME_ZONE: str = 'UTC'

# Включить поддержку интернационализации
USE_I18N: bool = True

# Включить поддержку временных зон
USE_TZ: bool = True


# === Статические файлы ===
# Настройки для CSS, JavaScript, изображений и т.д.

# URL-префикс для статических файлов
STATIC_URL: str = 'static/'

# Примечание: Для продакшена потребуются дополнительные настройки:
# STATIC_ROOT - директория для сбора статических файлов
# STATICFILES_DIRS - дополнительные директории со статическими файлами
# MEDIA_URL и MEDIA_ROOT - для пользовательских файлов


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname:<7} {name}:{lineno} - {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        # Это НАШ код, нам надо видеть про него всё. Включая дебаг.
        # Если что-то сломается — без этого ты будешь сидеть и гадать
        # как гадалка на кофейной гуще.
        "access_control": {"level": "INFO", "propagate": True},
        "processing": {"level": "INFO", "propagate": True},
        "camera_stream": {"level": "INFO", "propagate": True},
        # А это сторонние библиотеки которые любят насрать в лог по
        # 50 строк на каждый чих. Затыкаем им рот — пусть пишут только
        # реально важное (WARNING и выше). Если ты лезешь дебажить
        # внутренности самой ultralytics — поставь DEBUG, но я тебя
        # предупреждал.
        "ultralytics": {"level": "WARNING", "propagate": True},
        "paddleocr": {"level": "WARNING", "propagate": True},
        "paddlepaddle": {"level": "WARNING", "propagate": True},
        "paddle": {"level": "WARNING", "propagate": True},
        "paddlex": {"level": "WARNING", "propagate": True},
    },
}

LOGIN_URL = 'login'
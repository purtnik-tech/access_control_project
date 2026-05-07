"""
Конфигурация URL-маршрутов для проекта access_control_project.

Этот файл определяет все возможные URL-адреса проекта и связывает их
с соответствующими представлениями (views). Django использует эти маршруты
для маршрутизации входящих HTTP-запросов.

Список `urlpatterns` определяет соответствие между URL-путями и функциями
обработки (views). Для получения дополнительной информации см. документацию:
https://docs.djangoproject.com/en/6.0/topics/http/urls/

Примеры включения:
    - Функциональные представления:
        path('', views.home, name='home')
    - Классовые представления:
        path('', Home.as_view(), name='home')
    - Включение других URL-конфигураций:
        path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import path, include
from django.urls.resolvers import URLPattern, URLResolver
from typing import List, Union


# Список всех URL-маршрутов проекта
# Каждый элемент может быть либо URLPattern (конечный маршрут),
# либо URLResolver (включает другие URL-конфигурации)
urlpatterns: List[Union[URLPattern, URLResolver]] = [
    # === Административный интерфейс ===
    # Все URL, начинающиеся с 'admin/', направляются в стандартную
    # админ-панель Django. Это дает доступ к интерфейсу управления
    # моделями по адресу http://ваш-сайт/admin/
    path('admin/', admin.site.urls),

    # === Основное приложение контроля доступа ===
    # Пустая строка '' означает корневой URL сайта (http://ваш-сайт/)
    # Все маршруты, начинающиеся с '', передаются в URL-конфигурацию
    # приложения 'access_control' (файл urls.py внутри этого приложения)
    # Это позволяет модульно организовать маршруты для разных частей проекта
    path('', include('access_control.urls')),
    path('camera/', include('camera_stream.urls')),
]
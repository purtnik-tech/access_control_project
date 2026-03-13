#!/usr/bin/env python
"""
Утилита командной строки Django для выполнения административных задач.

Это основной исполняемый файл Django, который используется для:
- Запуска сервера разработки (runserver)
- Создания миграций (makemigrations)
- Применения миграций (migrate)
- Создания суперпользователя (createsuperuser)
- И многих других команд управления проектом

Данный файл автоматически создается при старте проекта и служит точкой входа
для всех команд django-admin и manage.py.
"""

import sys
import os
from typing import NoReturn


def main() -> NoReturn:
    """
    Запускает административные задачи Django.

    Эта функция:
    1. Устанавливает модуль настроек Django по умолчанию
    2. Импортирует функцию execute_from_command_line из django.core.management
    3. Передает аргументы командной строки в Django для выполнения

    Returns:
        NoReturn: Функция никогда не возвращает значение, так как вызывает
                  sys.exit() при завершении команды или raise при ошибке

    Raises:
        ImportError: Если Django не установлен или не доступен в окружении
    """

    # Устанавливаем модуль настроек Django по умолчанию
    # Это необходимо до загрузки любых компонентов Django
    # setdefault() устанавливает значение только если переменная ещё не задана,
    # что позволяет переопределить настройки через переменные окружения
    os.environ.setdefault(
        'DJANGO_SETTINGS_MODULE',  # Переменная окружения с путём к настройкам
        'access_control_project.settings'  # Путь к модулю настроек проекта
    )

    try:
        # Пытаемся импортировать функцию выполнения команд Django
        # Импорт выполняется внутри try-except для graceful error handling
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        # Если Django не найден, выбрасываем понятное исключение
        # с инструкциями по исправлению ситуации
        raise ImportError(
            "Не удалось импортировать Django. Убедитесь, что Django установлен "
            "и доступен в PYTHONPATH. Возможно, вы забыли активировать "
            "виртуальное окружение? Подсказки:\n"
            "  - Установка Django: pip install django\n"
            "  - Активация виртуального окружения: \n"
            "      Windows: .\\venv\\Scripts\\activate\n"
            "      Linux/Mac: source venv/bin/activate"
        ) from exc

    # Передаем управление Django с аргументами командной строки
    # execute_from_command_line проанализирует sys.argv и выполнит соответствующую команду
    # После выполнения команды функция вызовет sys.exit() с соответствующим кодом возврата
    execute_from_command_line(sys.argv)


# Стандартный идиоматический паттерн Python для исполняемых скриптов
# Код выполняется только при прямом запуске файла, а не при импорте
if __name__ == '__main__':
    main()  # Запускаем основную функцию приложения
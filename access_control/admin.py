"""
Модуль административного интерфейса Django для управления моделями системы контроля доступа.
Регистрирует модели в админ-панели и настраивает их отображение.
"""

from django.contrib import admin
from django.db import models
from typing import Optional, Any

from .models import LicensePlate, Employee, Pass


class PassAdmin(admin.ModelAdmin):
    """
    Настройка административного интерфейса для модели Pass (пропуски).
    Определяет, как будут отображаться, фильтроваться и искаться пропуска в админке.
    """

    # Поля для фильтрации в правой боковой панели
    list_filter: tuple = ('pass_type',)  # Фильтр по типу пропуска (постоянный/временный)

    # Поля для поиска (строка поиска вверху)
    search_fields: tuple = ('license_plate', 'employee__surname')  # Поиск по номеру и фамилии сотрудника

    # Поля, отображаемые в списке объектов
    list_display: tuple = ('show_man', 'car_brand', 'license_plate', 'pass_type')

    def show_man(self, obj: Pass) -> str:
        """
        Кастомное поле для отображения владельца пропуска (сотрудник или гость).

        Args:
            obj: Объект модели Pass

        Returns:
            str: Строковое представление владельца или '-' если ошибка
        """
        try:
            # Пытаемся получить сотрудника или гостя, связанного с пропуском
            owner: Optional[Any] = obj.employee or obj.guest
            return f'{owner}' if owner else '-'
        except Exception:
            # В случае любой ошибки возвращаем прочерк
            return '-'

    # Настраиваем заголовок для кастомного поля в админке
    show_man.short_description = 'Владелец'  # Заголовок колонки
    show_man.admin_order_field = 'employee'  # Поле для сортировки (по сотруднику)


# Регистрация модели LicensePlate (государственные номера) в админке
# Используются настройки по умолчанию
admin.site.register(LicensePlate)

# Регистрация модели Employee (сотрудники) в админке
# Используются настройки по умолчанию
admin.site.register(Employee)

# Регистрация модели Pass (пропуски) с кастомными настройками
admin.site.register(Pass, PassAdmin)
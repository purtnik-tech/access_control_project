"""
Модели данных для системы контроля доступа.
Определяют структуру базы данных для сотрудников, гостей, номеров и пропусков.
"""

from django.db import models
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from typing import Optional, Union, Tuple, Any


class Employee(models.Model):
    """
    Модель сотрудника предприятия.
    Хранит персональные данные и учётную информацию сотрудника.
    """

    # Логин сотрудника (используется как первичный ключ)
    login_user: models.CharField = models.CharField(
        max_length=50,
        primary_key=True,
        verbose_name="Логин"
    )

    # Персональные данные
    surname: models.CharField = models.CharField(
        max_length=50,
        verbose_name="Фамилия"
    )
    first_name: models.CharField = models.CharField(
        max_length=50,
        verbose_name="Имя"
    )
    patronymic: models.CharField = models.CharField(
        max_length=50,
        blank=True,  # Может быть пустым
        verbose_name="Отчество"
    )

    # Уникальный табельный номер сотрудника
    employee_number: models.CharField = models.CharField(
        max_length=20,
        unique=True,  # Должен быть уникальным
        verbose_name="Табельный номер"
    )

    def __str__(self) -> str:
        """
        Строковое представление объекта сотрудника.

        Returns:
            str: Фамилия и имя сотрудника
        """
        return f"{self.surname} {self.first_name}"

    class Meta:
        """Метаданные модели для административного интерфейса."""
        verbose_name: str = 'сотрудник'  # Имя в единственном числе
        verbose_name_plural: str = 'сотрудники'  # Имя во множественном числе


class Guest(models.Model):
    """
    Модель гостя предприятия.
    Хранит данные посетителей, не являющихся сотрудниками.
    """

    # Персональные данные
    surname: models.CharField = models.CharField(
        max_length=50,
        verbose_name="Фамилия"
    )
    first_name: models.CharField = models.CharField(
        max_length=50,
        verbose_name="Имя"
    )
    patronymic: models.CharField = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Отчество"
    )

    # Контактная информация
    phone_number: models.CharField = models.CharField(
        max_length=20,
        verbose_name="Номер телефона"
    )
    organization: models.CharField = models.CharField(
        max_length=100,
        blank=True,  # Может быть пустым
        verbose_name="Организация"
    )

    def __str__(self) -> str:
        """
        Строковое представление объекта гостя.

        Returns:
            str: Фамилия и имя гостя
        """
        return f"{self.surname} {self.first_name}"


class LicensePlate(models.Model):
    """
    Модель государственного номерного знака (ГНЗ).
    Хранит информацию об автомобильных номерах.
    """

    # Номерной знак (например, "А123ВС177")
    plate_number: models.CharField = models.CharField(
        max_length=15,
        unique=True,  # Номер должен быть уникальным
        validators=[
            RegexValidator(
                r'^[А-ЯA-Z0-9]+$',  # Только буквы (рус/лат) и цифры
                'Только буквы и цифры'
            )
        ],
        verbose_name="Государственный номер"
    )

    def __str__(self) -> str:
        """
        Строковое представление объекта номерного знака.

        Returns:
            str: Номерной знак
        """
        return self.plate_number


class Pass(models.Model):
    """
    Модель пропуска на территорию.
    Связывает автомобиль с сотрудником или гостем и определяет права доступа.
    """

    # Типы пропусков
    PASS_TYPES: Tuple[Tuple[str, str], ...] = (
        ('permanent', 'Постоянный (сотрудник)'),  # Для сотрудников
        ('temporary', 'Временный (гость)'),  # Для гостей
    )

    # Владелец пропуска (может быть либо сотрудник, либо гость)
    guest: Optional[models.ForeignKey] = models.ForeignKey(
        Guest,
        on_delete=models.CASCADE,  # При удалении гостя удаляются его пропуска
        null=True,
        blank=True
    )
    employee: Optional[models.ForeignKey] = models.ForeignKey(
        Employee,
        on_delete=models.CASCADE,  # При удалении сотрудника удаляются его пропуска
        null=True,
        blank=True
    )

    # Информация об автомобиле
    car_brand: models.CharField = models.CharField(
        max_length=50,
        verbose_name="Марка автомобиля"
    )
    license_plate: models.ForeignKey = models.ForeignKey(
        LicensePlate,
        on_delete=models.CASCADE,  # При удалении номера удаляются связанные пропуска
        verbose_name="ГНЗ"
    )

    # Параметры пропуска
    pass_type: models.CharField = models.CharField(
        max_length=10,
        choices=PASS_TYPES,  # Выбор из предопределенных типов
        verbose_name="Тип пропуска"
    )
    start_date: models.DateField = models.DateField(
        verbose_name="Дата начала действия"
    )
    end_date: Optional[models.DateField] = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата окончания (для временных)"
    )

    # Дополнительная информация для временных пропусков
    cargo_type: models.CharField = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Вид груза (для временных)"
    )
    entry_time: Optional[models.TimeField] = models.TimeField(
        null=True,
        blank=True,
        verbose_name="Время въезда (для временных)"
    )

    def clean(self) -> None:
        """
        Валидация данных пропуска.
        Проверяет корректность заполнения полей перед сохранением.

        Raises:
            ValidationError: Если данные не проходят валидацию
        """
        # Проверка наличия владельца
        if not self.guest and not self.employee:
            raise ValidationError(
                "Должен быть указан либо сотрудник, либо гость."
            )

        # Проверка даты окончания для постоянного пропуска
        if self.pass_type == 'permanent' and self.end_date:
            raise ValidationError(
                "Для постоянного пропуска дата окончания не задаётся."
            )

        # Проверка наличия даты окончания для временного пропуска
        if self.pass_type == 'temporary' and not self.end_date:
            raise ValidationError(
                "Для временного пропуска необходима дата окончания."
            )

    def __str__(self) -> str:
        """
        Строковое представление объекта пропуска.

        Returns:
            str: Номерной знак и информация о владельце
        """
        owner: Optional[Union[Employee, Guest]] = self.employee or self.guest
        return f"{self.license_plate} - {owner}"
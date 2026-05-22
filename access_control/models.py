"""
Модели данных для системы контроля доступа.
Определяют структуру базы данных для сотрудников, гостей, номеров и пропусков.
"""
import uuid

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError

from django.db import models
from django.utils import timezone


class PassLogsModel(models.Model):
    """
    Таблица Логов для проекта
    """
    id = models.UUIDField(
        primary_key=True,
        verbose_name='ID',
        db_comment='ID',
        default=uuid.uuid4
    )
    creation_date = models.DateTimeField(
        default=timezone.now,
        verbose_name='Дата создания',
        db_comment='Дата создания',
        editable=False,
    )
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        verbose_name='Объект модели',
        db_comment='Объект модели',
        null=True,
        blank=True
    )
    key = models.UUIDField(
        blank=True,
        null=True,
        verbose_name='Ключ записи',
        db_comment='Ключ записи',
    )
    message = models.CharField(
        max_length=2048,
        verbose_name='Сообщение',
        db_comment='Сообщение',
        null=True,
        blank=True
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='Пользователь',
        db_comment='Пользователь',
        null=True,
        blank=True
    )
    topic_id = models.UUIDField(
        blank=True,
        null=True,
        verbose_name='ID общего топика логов',
        db_comment='ID общего топика логов',
    )

    class Meta:
        db_table = 'pass_logs'
        verbose_name = 'Лог'
        verbose_name_plural = 'Логи'
        ordering = ['-creation_date']


class AccessLog(models.Model):
    plate = models.CharField(max_length=20)
    action = models.CharField(max_length=50)
    timestamp = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"{self.plate} - {self.action} at {self.timestamp}"

class PersonalDataModel(models.Model):
    """
    Абстрактная модель персональных данных
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        verbose_name='ID',
        db_comment='ID',
    )
    creation_date = models.DateTimeField(
        default=timezone.now,
        verbose_name='Дата создания',
        db_comment='Дата создания',
        editable=False,
    )
    surname = models.CharField(
        max_length=64,
        verbose_name="Фамилия",
        db_comment="Фамилия",
    )
    first_name = models.CharField(
        max_length=64,
        verbose_name="Имя",
        db_comment="Имя",
    )
    patronymic = models.CharField(
        max_length=64,
        blank=True,  # Может быть пустым
        verbose_name="Отчество",
        db_comment="Отчество",
    )
    phone_number = models.CharField(
        max_length=20,
        verbose_name="Номер телефона",
        db_comment="Номер телефона",
        blank=True,
        null=True,
    )

    class Meta:
        abstract = True


class Employee(PersonalDataModel):
    """
    Модель сотрудника предприятия.
    Хранит персональные данные и учётную информацию сотрудника.
    """
    login_user = models.CharField(
        unique=True,
        db_index=True,
        max_length=64,
        verbose_name="Логин",
        db_comment="Логин",
    )
    employee_number = models.CharField(
        max_length=20,
        unique=True,  # Должен быть уникальным
        verbose_name="Табельный номер",
        db_comment="Табельный номер",
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
        db_table = 'employees'
        ordering = ['surname', 'creation_date']
        verbose_name = 'Сотрудник'  # Имя в единственном числе
        verbose_name_plural = 'Сотрудники'  # Имя во множественном числе


class Guest(PersonalDataModel):
    """
    Модель гостя предприятия.
    Хранит данные посетителей, не являющихся сотрудниками.
    """
    organization = models.CharField(
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

    class Meta:
        db_table = 'guests'
        ordering = ['surname', 'creation_date']
        verbose_name = 'Гость'
        verbose_name_plural = 'Гости'


class LicensePlate(models.Model):
    """
    Модель государственного номерного знака (ГНЗ).
    Хранит информацию об автомобильных номерах.
    """
    id = models.UUIDField(
        primary_key=True,
        verbose_name='ID',
        db_comment='ID',
        default=uuid.uuid4,
    )
    creation_date = models.DateTimeField(
        default=timezone.now,
        verbose_name='Дата создания',
        db_comment='Дата создания',
    )
    plate_number = models.CharField(
        max_length=15,
        unique=True,
        validators=[
            RegexValidator(r'^[А-ЯA-Z0-9]+$','Только буквы и цифры') # Только буквы (рус/лат) и цифры
        ],
        verbose_name="Государственный номер",
        db_comment="Государственный номер",
        db_index=True,
    )

    def clean(self):
        self.plate_number = self.plate_number.upper() # Явно переводит все символы номера в верхний регистр

    def save(self, **kwargs):
        self.full_clean()
        super().save(**kwargs)

    def __str__(self) -> str:
        """
        Строковое представление объекта номерного знака.

        Returns:
            str: Номерной знак
        """
        return f'{self.plate_number}'

    class Meta:
        db_table = 'license_plates'
        ordering = ['plate_number']
        verbose_name = 'Регистрационный номер'
        verbose_name_plural = 'Регистрационные номера'


class LicensePlateForManualHandleModel(models.Model):
    """
    Модель данных номеров ожидающих ручной обработки
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        verbose_name='ID',
        db_comment='ID',
    )
    creation_date = models.DateTimeField(
        default=timezone.now,
        verbose_name='Дата создания',
        db_comment='Дата создания',
    )
    license_plate = models.OneToOneField(
        LicensePlate,
        on_delete=models.CASCADE,
        verbose_name='Гос. номер',
        db_comment='Гос. номер',
    )

    class Meta:
        db_table = 'license_plates_for_manual_handle'
        ordering = ['-creation_date']
        verbose_name = 'Регистрационный номер для ручной обработки'
        verbose_name_plural = 'Регистрационные номера для ручной обработки'


class Vehicle(models.Model):
    """
    Модель данных транспортных средств
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        verbose_name='ID',
        db_comment='ID',
    )
    creation_date = models.DateTimeField(
        default=timezone.now,
        verbose_name='Дата создания',
        db_comment='Дата создания',
    )
    license_plate = models.ForeignKey(
        LicensePlate,
        on_delete=models.PROTECT,
        verbose_name='Гос.номер',
        db_comment='Гос.номер',
        null=True,
        blank=True,
    )
    brand = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        verbose_name='Марка транспортного средства',
        db_comment='Марка транспортного средства',
    )
    model = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        verbose_name='Модель транспортного средства',
        db_comment='Модель транспортного средства',
    )
    color = models.CharField(
        max_length=16,
        verbose_name='Цвет транспортного средства',
        db_comment='Цвет транспортного средства',
        blank=True,
        null=True,
    )

    @property
    def plate_number(self) -> str:
        return self.license_plate.plate_number

    def __str__(self) -> str:
        """
        :return: Наименование и модель транспортного средства
        """
        return f'{self.brand} {self.model} {self.plate_number}'

    class Meta:
        db_table = 'vehicles'
        ordering = ['brand', 'model', 'creation_date']
        verbose_name = 'Транспортное средство'
        verbose_name_plural = 'Транспортные средства'


class AccessSubject(models.Model):
    """
    Модель данных субъектов пропусков
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        verbose_name='ID',
        db_comment='ID',
    )
    creation_date = models.DateTimeField(
        default=timezone.now,
        verbose_name='Дата создания',
        db_comment='Дата создания',
    )
    employee = models.ForeignKey(
        Employee,
        on_delete=models.PROTECT,
        verbose_name='Сотрудник',
        db_comment='Сотрудник',
        blank=True,
        null=True,
    )
    guest = models.ForeignKey(
        Guest,
        on_delete=models.PROTECT,
        verbose_name='Гость',
        db_comment='Гость',
        blank=True,
        null=True,
    )
    vehicle = models.ForeignKey(
        Vehicle,
        on_delete=models.PROTECT,
        verbose_name='Транспортное средство',
        db_comment='Транспортное средство',
    )

    @property
    def subject(self) -> Employee | Guest:
        return self.employee or self.guest

    @property
    def plate_number(self) -> str:
        return self.vehicle.license_plate.plate_number

    def __str__(self) -> str:
        return f'{self.subject} {self.vehicle}'

    class Meta:
        db_table = 'access_subjects'
        ordering = ['creation_date']
        verbose_name = 'Субъект пропуска'
        verbose_name_plural = 'Субъекты пропуска'
        constraints = [
            models.UniqueConstraint(fields=['employee', 'guest'], name='unique_access_subjects_employee_guest'),
            models.CheckConstraint(
                check=models.Q(employee__isnull=True, guest__isnull=False) |
                      models.Q(employee__isnull=False, guest__isnull=True),
                name='unique_access_one_subject'
            )
        ]


class PassModel(models.Model):
    """
    Модель пропуска на территорию.
    Связывает автомобиль с сотрудником или гостем и определяет права доступа.
    """

    class TypesPass(models.TextChoices):
        """
        Типы пропусков
        """
        PERMANENT = 'Постоянный'
        TEMPORARY = 'Временный'

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        verbose_name='ID',
        db_comment='ID',
    )
    creation_date = models.DateTimeField(
        default=timezone.now,
        verbose_name='Дата создания',
        db_comment='Дата создания',
    )
    subject = models.ForeignKey(
        AccessSubject,
        on_delete=models.CASCADE,
        verbose_name='Субъект пропуска',
        db_comment='Субъект пропуска',
    )
    pass_type = models.CharField(
        max_length=10,
        choices=TypesPass.choices,
        verbose_name="Тип пропуска",
        db_comment="Тип пропуска",
    )
    start_date = models.DateField(
        verbose_name="Дата начала действия"
    )
    end_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Дата окончания (для временных)"
    )
    cargo_type = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Вид груза (для временных)"
    )
    entry_time = models.TimeField(
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
        # Проверка даты окончания для постоянного пропуска
        if self.pass_type == self.TypesPass.PERMANENT and self.end_date:
            raise ValidationError("Для постоянного пропуска дата окончания не задаётся.")

        # Проверка наличия даты окончания для временного пропуска
        if self.pass_type == self.TypesPass.TEMPORARY and not self.end_date:
            raise ValidationError("Для временного пропуска необходима дата окончания.")

    def save(self, **kwargs):
        self.full_clean()
        super().save(**kwargs)

    def __str__(self) -> str:
        """
        Строковое представление объекта пропуска.

        Returns:
            str: Номерной знак и информация о владельце
        """
        return f"{self.subject.subject} {self.subject.vehicle.plate_number}"

    class Meta:
        db_table = 'passes'
        ordering = ['creation_date']
        verbose_name = 'Пропуск'
        verbose_name_plural = 'Пропуска'
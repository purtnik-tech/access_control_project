from django.db import models
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError

class Employee(models.Model):
    login_user = models.CharField(max_length=50, primary_key=True, verbose_name="Логин")
    surname = models.CharField(max_length=50, verbose_name="Фамилия")
    first_name = models.CharField(max_length=50, verbose_name="Имя")
    patronymic = models.CharField(max_length=50, blank=True, verbose_name="Отчество")
    employee_number = models.CharField(max_length=20, unique=True, verbose_name="Табельный номер")

    def __str__(self):
        return f"{self.surname} {self.first_name}"

    class Meta:
        verbose_name = ('сотрудник')
        verbose_name_plural = ('сотрудники')

class Guest(models.Model):
    surname = models.CharField(max_length=50, verbose_name="Фамилия")
    first_name = models.CharField(max_length=50, verbose_name="Имя")
    patronymic = models.CharField(max_length=50, blank=True, verbose_name="Отчество")
    phone_number = models.CharField(max_length=20, verbose_name="Номер телефона")
    organization = models.CharField(max_length=100, blank=True, verbose_name="Организация")

    def __str__(self):
        return f"{self.surname} {self.first_name}"

class LicensePlate(models.Model):
    plate_number = models.CharField(
        max_length=15,
        unique=True,
        validators=[RegexValidator(r'^[А-ЯA-Z0-9]+$', 'Только буквы и цифры')],
        verbose_name="Государственный номер"
    )

    def __str__(self):
        return self.plate_number

class Pass(models.Model):
    PASS_TYPES = (
        ('permanent', 'Постоянный (сотрудник)'),
        ('temporary', 'Временный (гость)'),
    )
    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, null=True, blank=True)
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, null=True, blank=True)
    car_brand = models.CharField(max_length=50, verbose_name="Марка автомобиля")
    license_plate = models.ForeignKey(LicensePlate, on_delete=models.CASCADE, verbose_name="ГНЗ")
    pass_type = models.CharField(max_length=10, choices=PASS_TYPES, verbose_name="Тип пропуска")
    start_date = models.DateField(verbose_name="Дата начала действия")
    end_date = models.DateField(null=True, blank=True, verbose_name="Дата окончания (для временных)")
    cargo_type = models.CharField(max_length=100, blank=True, verbose_name="Вид груза (для временных)")
    entry_time = models.TimeField(null=True, blank=True, verbose_name="Время въезда (для временных)")

    def clean(self):
        if not self.guest and not self.employee:
            raise ValidationError("Должен быть указан либо сотрудник, либо гость.")
        if self.pass_type == 'permanent' and self.end_date:
            raise ValidationError("Для постоянного пропуска дата окончания не задаётся.")
        if self.pass_type == 'temporary' and not self.end_date:
            raise ValidationError("Для временного пропуска необходима дата окончания.")

    def __str__(self):
        owner = self.employee or self.guest
        return f"{self.license_plate} - {owner}"
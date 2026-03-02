import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'access_control_project.settings')
django.setup()

from access_control.models import LicensePlate, Employee, Guest, Pass
from datetime import date, datetime

# Создаем тестовые номера
test_plates = ['A798AP177', 'B456EK', 'C789MH', 'X000XX']

for plate in test_plates:
    LicensePlate.objects.get_or_create(plate_number=plate)

print("Тестовые номера добавлены")

# Создаем сотрудника (опционально)
employee, _ = Employee.objects.get_or_create(
    login_user='ivanov',
    defaults={
        'surname': 'Иванов',
        'first_name': 'Иван',
        'patronymic': 'Иванович',
        'employee_number': '001'
    }
)

# Создаем пропуск для тестового номера
plate = LicensePlate.objects.get(plate_number='A798AP177')
Pass.objects.get_or_create(
    license_plate=plate,
    employee=employee,
    defaults={
        'car_brand': 'Toyota',
        'pass_type': 'permanent',
        'start_date': date.today()
    }
)

print("Тестовый пропуск создан")
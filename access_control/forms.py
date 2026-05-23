from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .models import PassModel, Guest, Employee, LicensePlate


class CreatePassCommonForm(forms.Form):
    """

    """
    plate_number = forms.CharField(
        label='Номер автомобиля',
        max_length=15,
        validators=[RegexValidator(r'^[А-ЯA-Z0-9]+$','Только буквы и цифры')]
    )
    brand = forms.CharField(
        label='Марка транспортного средства',
        max_length=32
    )
    model = forms.CharField(
        label='Модель транспортного средства',
        max_length=32,
        required=False
    )
    color = forms.CharField(
        label='Цвет транспортного средства',
        max_length=16,
        required=False
    )
    start_date = forms.DateField(
        label='Дата начала действия',
        widget=forms.widgets.Input(attrs={'type': 'date'})
    )


class CreateEmployeePassForm(CreatePassCommonForm):
    """
    Форма создания пропуска для сотрудника
    """
    employee = forms.ModelChoiceField(
        queryset=Employee.objects.all(),
        label='Сотрудник'
    )

    def clean(self):
        plate_number = self.cleaned_data.get('plate_number')
        employee = self.cleaned_data.get('employee')
        queryset = PassModel.objects.filter(
            subject__vehicle__license_plate__plate_number=plate_number, subject__employee=employee
        )
        if queryset.exists():
            raise ValidationError(f'Пропуск с таким номером транспортного средства для сотрудника уже существует!')
        return super().clean()

class CreateGuestPassForm(CreatePassCommonForm):
    """
    Форма создания пропуска для гостя
    """
    surname = forms.CharField(
        label='Фамилия',
        max_length=64
    )
    first_name = forms.CharField(
        label='Имя',
        max_length=64
    )
    patronymic = forms.CharField(
        label='Отчество',
        max_length=64,
    )
    phone_number = forms.CharField(
        label='Номер телефона',
        max_length=20,
    )
    organization = forms.CharField(
        label='Организация',
        max_length=100,
    )
    end_date = forms.DateField(
        label='Дата окончания действия',
        widget=forms.widgets.Input(attrs={'type': 'date'})
    )
    cargo_type = forms.CharField(
        label='Тип груза',
        max_length=100,
    )

    def clean(self):
        guest, _ = Guest.objects.get_or_create(
            surname=self.cleaned_data.get('surname'),
            first_name=self.cleaned_data.get('first_name'),
            patronymic=self.cleaned_data.get('patronymic'),
            phone_number=self.cleaned_data.get('phone_number'),
            organization=self.cleaned_data.get('organization'),
        )
        plate_number = self.cleaned_data.get('plate_number')
        queryset = PassModel.objects.filter(
            subject__vehicle__license_plate__plate_number=plate_number, subject__guest=guest
        )
        if queryset.exists():
            raise ValidationError(f'Пропуск с таким номером транспортного средства для гостя уже существует!')
        cleaned_data = super().clean()
        cleaned_data.update(guest=guest)
        return cleaned_data

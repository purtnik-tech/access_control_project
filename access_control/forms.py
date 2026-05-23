from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator

from .models import PassModel, Guest, Employee


class CreatePassForm(forms.Form):
    """
    Форма создания пропуска
    """
    pass_type = forms.ChoiceField(
        choices=PassModel.TypesPass.choices,
        label='Тип пропуска'
    )
    subject = forms.ChoiceField(
        choices=(('guest', 'Гость'), ('employee', 'Сотрудник')),
        label='Субъект пропуска'
    )
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
        required=False,
        widget=forms.widgets.TextInput(attrs={'placeholder': 'Только для гостей'})
    )
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
    end_date = forms.DateField(
        label='Дата окончания действия',
        required=False,
        widget=forms.widgets.Input(attrs={'type': 'date'})
    )
    cargo_type = forms.CharField(
        label='Тип груза',
        max_length=100,
        widget=forms.widgets.TextInput(attrs={'placeholder': 'Только для временных пропусков'}),
        required=False
    )

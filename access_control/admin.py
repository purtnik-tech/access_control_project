"""
Модуль административного интерфейса Django для управления моделями системы контроля доступа.
Регистрирует модели в админ-панели и настраивает их отображение.
"""

from django.contrib import admin

from .models import LicensePlate, Employee, Pass, Guest, Vehicle, AccessSubject


class PassAdmin(admin.ModelAdmin):
    """
    Настройка административного интерфейса для модели Pass (пропуски).
    Определяет, как будут отображаться, фильтроваться и искаться пропуска в админке.
    """
    queryset = Pass.objects.select_related('subject', 'subject__employee', 'subject__guest', 'subject__license_plate').all()
    # Поля, отображаемые в списке объектов
    list_display: tuple = ('subject','pass_type', 'start_date', 'end_date')
    # Поля для фильтрации в правой боковой панели
    list_filter: tuple = ('pass_type',)  # Фильтр по типу пропуска (постоянный/временный)
    # Поля для поиска (строка поиска вверху)
    search_fields: tuple = ('subject__vehicle__license_plate__plate_number', 'subject__guest__surname', 'subject__employee__surname')  # Поиск по номеру и фамилии сотрудника


class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('login_user', 'surname', 'first_name', 'patronymic', 'phone_number', 'employee_number')
    search_fields = ('login_user', 'surname', 'phone_number', 'employee_number')
    search_help_text = 'Поиск по личным данным сотрудника'
    list_filter = ('creation_date', )


class GuestAdmin(admin.ModelAdmin):
    list_display = ('surname', 'first_name', 'patronymic', 'phone_number', 'organization')
    search_fields = ('surname', 'phone_number', 'organization')
    search_help_text = 'Поиск по личным данным гостя'
    list_filter = ('creation_date', )


class LicensePlateAdmin(admin.ModelAdmin):
    list_display = ('plate_number', 'creation_date')
    search_fields = ('plate_number',)
    search_help_text = f'Поиск по номеру'
    list_filter = ('plate_number', )


class VehicleAdmin(admin.ModelAdmin):
    list_display = ('license_plate', 'brand', 'model', 'color', 'creation_date')
    list_filter = ('creation_date',)
    search_fields = ('license_plate__plate_number', 'brand', 'model')
    search_help_text = 'Поиск автомобиля по бренду, марке и номеру'


class AccessSubjectAdmin(admin.ModelAdmin):
    queryset = AccessSubject.objects.select_related('guest', 'employee', 'vehicle', 'vehicle__license_plate').all()
    list_display = ('subject', 'vehicle', 'creation_date')
    list_filter = ('creation_date',)
    search_fields = ('employee__surname', 'employee__login_user', 'guest__surname')
    search_help_text = 'Поиск субъекта по фамилии и гос.номеру'


admin.site.register(LicensePlate, LicensePlateAdmin)
admin.site.register(Employee, EmployeeAdmin)
admin.site.register(Guest, GuestAdmin)
admin.site.register(Vehicle, VehicleAdmin)
admin.site.register(AccessSubject, AccessSubjectAdmin)
admin.site.register(Pass, PassAdmin)
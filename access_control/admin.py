from django.contrib import  admin

from .models import LicensePlate,  Employee, Pass

class PassAdmin(admin.ModelAdmin):
    list_filter = ('pass_type', )
    search_fields = ('license_plate', 'employee__surname')
    list_display = ('show_man', 'car_brand', 'license_plate', 'pass_type')

    def show_man(self, obj):
        try:
            return f'{obj.employee or obj.guest}'
        except:
            return f'-'

admin.site.register(LicensePlate)
admin.site.register(Employee)
admin.site.register(Pass, PassAdmin)

from django.apps import AppConfig

class AccessControlConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'access_control'

    def ready(self):
        # Инициализация камеры происходит в views.py при первом запросе
        pass
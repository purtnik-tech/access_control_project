# access_control/apps.py
from django.apps import AppConfig
import threading

class AccessControlConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'access_control'

    def ready(self):
        # Запускаем фоновый поток с камерой только при запуске сервера (не в режиме миграций)
        from .camera_stream import CameraStream
        import os
        if os.environ.get('RUN_MAIN') == 'true':  # предотвращаем двойной запуск в dev-сервере
            stream = CameraStream(camera_id=0)  # 0 - встроенная камера, для Logitech C270 тоже 0
            stream.start()
            # Сохраняем ссылку в глобальной переменной или через singleton
            import sys
            sys.modules[__name__].camera_stream = stream
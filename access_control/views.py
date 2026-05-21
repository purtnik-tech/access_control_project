import json
import time
import threading
from datetime import date
from typing import Optional

from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse, StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt

# Импорт реального класса CameraStream (файл camera_stream/camera_stream.py)
from camera_stream.camera.service import CameraStream

# Импорт моделей (AccessLog должен быть создан)
from .models import LicensePlate, AccessLog


# -------------------------------------------------------------------
# Декоратор для проверки принадлежности к группе
# -------------------------------------------------------------------
def group_required(group_name):
    """Разрешает доступ только пользователям из указанной группы."""
    return user_passes_test(
        lambda u: u.is_authenticated and u.groups.filter(name=group_name).exists()
    )


# -------------------------------------------------------------------
# Потокобезопасный синглтон для камеры
# -------------------------------------------------------------------
_camera_stream: Optional[CameraStream] = None
_camera_initializing: bool = False
_camera_lock = threading.Lock()


def get_camera_stream() -> Optional[CameraStream]:
    """
    Получение или создание экземпляра потока камеры (ленивая инициализация с синглтоном).
    Реализует потокобезопасный паттерн Singleton с ожиданием инициализации.
    """
    global _camera_stream, _camera_initializing

    if _camera_stream is not None:
        return _camera_stream

    with _camera_lock:
        if _camera_stream is not None:
            return _camera_stream

        if _camera_initializing:
            print("[INFO] Ожидание инициализации камеры...")
            for _ in range(20):  # 20 * 0.5 = 10 секунд
                time.sleep(0.5)
                if _camera_stream is not None:
                    return _camera_stream
            print("[WARN] Таймаут ожидания инициализации камеры")

        _camera_initializing = True

        try:
            print("[INFO] Инициализация камеры...")
            camera_url = "rtsp://admin:123qweQWE@10.2.26.3:554/stream"

            _camera_stream = CameraStream(url=camera_url)

            start_time = time.time()
            timeout = 15

            while time.time() - start_time < timeout:
                time.sleep(0.5)
                if hasattr(_camera_stream, 'cap') and _camera_stream.cap is not None:
                    if _camera_stream.cap.isOpened():
                        print("[INFO] Камера успешно инициализирована")
                        _camera_initializing = False
                        return _camera_stream

            print("[WARN] Таймаут инициализации камеры — продолжаем без видео")
            _camera_stream = None
            _camera_initializing = False
            return None

        except Exception as e:
            print(f"[ERROR] Ошибка при создании камеры: {e} — продолжаем без видео")
            _camera_stream = None
            _camera_initializing = False
            return None

    return _camera_stream


# -------------------------------------------------------------------
# Основные представления (видео, статус, история)
# -------------------------------------------------------------------
def index(request):
    if request.user.is_authenticated:
        if request.user.groups.filter(name='post').exists():
            return redirect('post_dashboard')
        elif request.user.groups.filter(name='admin').exists():
            return redirect('admin_dashboard')
        elif request.user.groups.filter(name='it_specialist').exists():
            return redirect('it_dashboard')
        return redirect('post_dashboard')
    return redirect('login')


def video_feed(request):
    stream = get_camera_stream()
    return StreamingHttpResponse(
        stream.generate_frames(),
        content_type='multipart/x-mixed-replace; boundary=frame'
    )


def status(request):
    stream = get_camera_stream()
    plate = getattr(stream, 'last_recognized_plate', '')
    return JsonResponse({'plate': plate})


def recognition_history(request):
    logs = AccessLog.objects.order_by('-timestamp')[:20]
    history = [
        {
            'plate': log.plate,
            'timestamp': log.timestamp.isoformat(),
            'action': log.action
        }
        for log in logs
    ]
    return JsonResponse({'history': history})


# -------------------------------------------------------------------
# Аутентификация
# -------------------------------------------------------------------
def user_login(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            if user.groups.filter(name='post').exists():
                return redirect('post_dashboard')
            elif user.groups.filter(name='admin').exists():
                return redirect('admin_dashboard')
            elif user.groups.filter(name='it_specialist').exists():
                return redirect('it_dashboard')
            else:
                return redirect('post_dashboard')
        else:
            return render(request, 'login.html', {'error': 'Неверное имя пользователя или пароль'})
    return render(request, 'login.html')


def user_logout(request):
    logout(request)
    return redirect('login')


# -------------------------------------------------------------------
# Рабочие столы (дашборды)
# -------------------------------------------------------------------
@login_required
@group_required('post')
def post_dashboard(request):
    return render(request, 'post.html')


@login_required
@group_required('admin')
def admin_dashboard(request):
    today = date.today()
    access_logs = AccessLog.objects.filter(timestamp__date=today).order_by('-timestamp')
    stream = get_camera_stream()
    current_plate = getattr(stream, 'last_recognized_plate', '')
    return render(request, 'admin_dashboard.html', {
        'access_logs': access_logs,
        'current_plate': current_plate,
    })


@login_required
@group_required('it_specialist')
def it_dashboard(request):
    try:
        with open('/var/log/access_control_server.log', 'r') as f:
            lines = f.readlines()[-100:]
            server_logs = ''.join(lines)
    except FileNotFoundError:
        server_logs = 'Файл логов не найден'
    return render(request, 'it_dashboard.html', {'server_logs': server_logs})


# -------------------------------------------------------------------
# AJAX-обработчики для поста охраны
# -------------------------------------------------------------------
@csrf_exempt
@login_required
@group_required('post')
def add_pass(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            plate_number = data.get('plate', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({'status': 'Некорректный запрос'}, status=400)

        if not plate_number:
            return JsonResponse({'status': 'Номер не указан'}, status=400)

        LicensePlate.objects.get_or_create(number=plate_number)
        AccessLog.objects.create(plate=plate_number, action='Пропуск добавлен')
        return JsonResponse({'status': f'Пропуск для {plate_number} добавлен'})
    return JsonResponse({'status': 'Метод не поддерживается'}, status=405)


@csrf_exempt
@login_required
@group_required('post')
def allow_access(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            plate_number = data.get('plate', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({'status': 'Некорректный запрос'}, status=400)

        if not plate_number:
            return JsonResponse({'status': 'Номер не указан'}, status=400)

        if LicensePlate.objects.filter(number=plate_number).exists():
            AccessLog.objects.create(plate=plate_number, action='Допуск')
            return JsonResponse({'status': f'Доступ для {plate_number} разрешён'})
        else:
            return JsonResponse({'status': f'Нет пропуска для {plate_number}'}, status=403)
    return JsonResponse({'status': 'Метод не поддерживается'}, status=405)


@csrf_exempt
@login_required
@group_required('post')
def deny_access(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            plate_number = data.get('plate', '').strip()
        except json.JSONDecodeError:
            return JsonResponse({'status': 'Некорректный запрос'}, status=400)

        if not plate_number:
            return JsonResponse({'status': 'Номер не указан'}, status=400)

        AccessLog.objects.create(plate=plate_number, action='Запрет')
        return JsonResponse({'status': f'Доступ для {plate_number} запрещён'})
    return JsonResponse({'status': 'Метод не поддерживается'}, status=405)
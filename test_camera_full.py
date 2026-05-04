import cv2
import os
import subprocess
import re


def test_camera_connection(url):
    print("=" * 60)
    print(f"ДИАГНОСТИКА ПОДКЛЮЧЕНИЯ К КАМЕРЕ")
    print("=" * 60)
    print(f"URL: {url}")

    # 1. Проверка IP доступности
    print("\n📡 1. ПРОВЕРКА СЕТЕВОЙ ДОСТУПНОСТИ")
    ip_match = re.search(r'@(\d+\.\d+\.\d+\.\d+)', url)
    if ip_match:
        ip = ip_match.group(1)
        print(f"   IP адрес: {ip}")
        result = subprocess.run(['ping', '-n', '2', ip], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✅ IP доступен (ping успешен)")
        else:
            print(f"   ❌ IP НЕ доступен (ping failed)")
            print(f"      Возможно камера выключена или не в сети")

    # 2. Проверка порта
    print("\n🔌 2. ПРОВЕРКА ПОРТА 554")
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(3)
    result = sock.connect_ex((ip, 554))
    if result == 0:
        print(f"   ✅ Порт 554 открыт")
    else:
        print(f"   ❌ Порт 554 закрыт или фильтруется")
    sock.close()

    # 3. Проверка аутентификации
    print("\n🔐 3. ПРОВЕРКА АУТЕНТИФИКАЦИИ")
    # Извлекаем логин и пароль
    auth_match = re.search(r'://(.+):(.+)@', url)
    if auth_match:
        username = auth_match.group(1)
        password = '*' * len(auth_match.group(2))
        print(f"   Логин: {username}")
        print(f"   Пароль: {password}")

    # 4. Тестирование разных транспортов
    print("\n🔄 4. ТЕСТИРОВАНИЕ ТРАНСПОРТОВ")

    transports = [
        ("TCP", "rtsp_transport;tcp"),
        ("UDP", "rtsp_transport;udp"),
        ("HTTP", "rtsp_transport;http"),
        ("TCP низкий таймаут", "rtsp_transport;tcp|timeout;2000000|stimeout;2000000"),
    ]

    for name, params in transports:
        print(f"\n   📍 Тест: {name}")
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = params
        cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)

        if cap.isOpened():
            print(f"      ✅ УСПЕХ: камера открыта")
            # Пробуем прочитать кадр
            ret, frame = cap.read()
            if ret:
                print(f"      ✅ Кадр получен")
                cv2.imwrite(f'test_frame_{name}.jpg', frame)
                print(f"      ✅ Кадр сохранён")
            else:
                print(f"      ❌ Кадр не получен")
            cap.release()
        else:
            print(f"      ❌ Не удалось открыть")

    # 5. Очистка переменных окружения
    if 'OPENCV_FFMPEG_CAPTURE_OPTIONS' in os.environ:
        del os.environ['OPENCV_FFMPEG_CAPTURE_OPTIONS']

    print("\n" + "=" * 60)
    print("ДИАГНОСТИКА ЗАВЕРШЕНА")
    print("=" * 60)


if __name__ == "__main__":
    url = "rtsp://admin:123qweQWE@10.2.26.3:554/stream"
    test_camera_connection(url)
import cv2
import time

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # попробуйте 0 или 1
if not cap.isOpened():
    print("Камера не открывается")
else:
    print("Камера открыта")
    for i in range(30):  # попробуем получить 30 кадров
        ret, frame = cap.read()
        if ret:
            cv2.imwrite(f'test_frame_{i}.jpg', frame)
            print(f"Кадр {i} сохранён")
        else:
            print(f"Кадр {i} не получен")
        time.sleep(0.1)
    cap.release()
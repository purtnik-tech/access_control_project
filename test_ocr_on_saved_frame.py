import cv2
import pytesseract
import re
import os

# Путь к Tesseract (измените при необходимости)
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'


def test_ocr_on_image(image_path):
    """Тестирование OCR на конкретном изображении"""
    print(f"\n--- Тестирование файла: {image_path} ---")

    if not os.path.exists(image_path):
        print(f"Файл не найден: {image_path}")
        return

    # Загружаем изображение
    img = cv2.imread(image_path)
    if img is None:
        print("Не удалось загрузить изображение")
        return

    print(f"Размер изображения: {img.shape}")

    # Конвертируем в серый
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Список методов предобработки для тестирования
    preprocessing_methods = [
        ('Original', gray),
        ('Gaussian Blur', cv2.GaussianBlur(gray, (3, 3), 0)),
        ('Median Blur', cv2.medianBlur(gray, 3)),
        ('Threshold (127)', cv2.threshold(gray, 127, 255, cv2.THRESH_BINARY)[1]),
        ('Threshold (150)', cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]),
        ('Otsu', cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)[1]),
        ('Adaptive Gaussian', cv2.adaptiveThreshold(gray, 255,
                                                    cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)),
        ('Adaptive Mean', cv2.adaptiveThreshold(gray, 255,
                                                cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 11, 2)),
        ('CLAHE', cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)),
    ]

    # Режимы PSM для тестирования
    psm_modes = [6, 7, 8, 13]  # 6-блок, 7-строка, 8-слово, 13-сырая строка

    best_result = ""
    best_score = 0

    for method_name, processed in preprocessing_methods:
        # Сохраняем обработанное изображение
        output_file = f"debug_{method_name.replace(' ', '_')}.jpg"
        cv2.imwrite(output_file, processed)
        print(f"\nМетод: {method_name}")

        for psm in psm_modes:
            config = f'--psm {psm} --oem 3'
            try:
                text = pytesseract.image_to_string(processed, lang='rus+eng', config=config)
                cleaned = re.sub(r'[^A-Z0-9А-Я]', '', text).strip()

                # Оцениваем качество (больше букв/цифр - лучше)
                score = len(cleaned)
                if score > best_score:
                    best_score = score
                    best_result = cleaned

                print(f"  PSM {psm}: '{text.strip()}' -> '{cleaned}'")
            except Exception as e:
                print(f"  PSM {psm}: Ошибка - {e}")

    print(f"\n✅ Лучший результат: '{best_result}'")
    return best_result


if __name__ == "__main__":
    # Тестируем на всех сохранённых кадрах
    import glob

    frames = glob.glob("debug_frame_*.jpg")

    if not frames:
        print("Нет сохранённых кадров. Сначала запустите основное приложение.")
    else:
        for frame in frames:
            test_ocr_on_image(frame)
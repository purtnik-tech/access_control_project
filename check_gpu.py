import torch
import easyocr
import cv2

print("=== ПРОВЕРКА GPU ===")
print(f"PyTorch версия: {torch.__version__}")

# Проверка CUDA
cuda_available = torch.cuda.is_available()
print(f"CUDA доступна: {cuda_available}")

if cuda_available:
    print(f"Количество GPU: {torch.cuda.device_count()}")
    print(f"Имя GPU: {torch.cuda.get_device_name(0)}")
    print(f"Текущее устройство: {torch.cuda.current_device()}")
else:
    print("❌ CUDA НЕ доступна. GPU не будет использоваться.")

# Проверка версии CUDA
if hasattr(torch, 'version'):
    print(f"Версия CUDA в PyTorch: {torch.version.cuda}")

print("\n=== ПРОВЕРКА OPENCV ===")
print(f"OpenCV версия: {cv2.__version__}")
print(f"OpenCV собран с CUDA: {cv2.cuda.getCudaEnabledDeviceCount() if hasattr(cv2, 'cuda') else 'Нет'}")

print("\n=== ИНСТРУКЦИИ ===")
if not cuda_available:
    print("\n❌ GPU НЕ ДОСТУПЕН. Чтобы включить GPU:")
    print("1. Установите CUDA Toolkit: https://developer.nvidia.com/cuda-downloads")
    print("2. Установите PyTorch с CUDA:")
    print("   pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118")
    print("3. Переустановите easyOCR:")
    print("   pip uninstall easyocr")
    print("   pip install easyocr")
else:
    print("\n✅ GPU ДОСТУПЕН! EasyOCR будет использовать GPU.")
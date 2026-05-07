from ultralytics import YOLO


def main():
    model = YOLO('yolov10x.pt')
    model.train(
        data='C:\\space\\ac\\tools\\yamls\\license.yaml',
        epochs=50,
        imgsz=640,
        batch=16,

        mosaic=1.0,
        mixup=0.1,
        hsv_h=0.015,
        hsv_s=0.7,
        hsv_v=0.4,
        name='yolov10x_license_plate'
    )

if __name__ == '__main__':
    main()
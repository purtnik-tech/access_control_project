from ultralytics import YOLO


model = YOLO('yolov10x.pt')
model.train(
    data='C:\\space\\ac\\tools\\yamls\\car_license.yaml',
    epochs=50,
    imgsz=640,
    batch=16,
    name='yolov10x_car_license',
)
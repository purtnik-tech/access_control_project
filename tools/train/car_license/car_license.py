import logging
from multiprocessing import freeze_support
import torch
from ultralytics import YOLO

def setup_logger():
    logger = logging.getLogger(__name__)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s — %(levelname)s — %(message)s', datefmt='%d-%m-%Y %H:%M:%S'))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger

def main():
    logger = setup_logger()
    logger.debug('Start')   # теперь только в главном процессе

    if torch.cuda.is_available():
        logger.info(f'GPU COUNT: {torch.cuda.device_count()}')
        logger.info('Init model')
        model = YOLO(r'C:\Users\localadmin\PycharmProjects\access_control_project\yolov10x.pt')
        model.to('cuda')
        logger.info('Run')
        model.train(
            data=r'C:\Users\localadmin\PycharmProjects\access_control_project\tools\yamls\car_license.yaml',
            epochs=50,
            imgsz=640,
            batch=2,
            name='yolov10x_car_license',
            device='cuda:0',
            amp=False,
        )
        logger.info('End')
    else:
        logger.critical('CUDA не обнаружено!')

if __name__ == '__main__':
    freeze_support()
    main()
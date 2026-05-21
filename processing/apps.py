"""
Это та самая хрень, которая включает мозг у проекта когда ты запускаешь runserver.

Слушай сюда внимательно потому что я устал обьяснять. Раньше было так:
один терминал крутил камеру и веб, второй терминал крутил YOLO+OCR через
команду run_engine. И они друг про друга НЕ ЗНАЛИ, потомучто это два
разных процесса Питона. Распознанный номер записывался в один процесс,
а сайт читал из другого. Поэтому у тебя на экране всегда висело
"Номер не распознан" гениально, спасибо за внимание дебилоиды.

Теперь весь движок запускается ВНУТРИ того же процесса где runserver.
Один процесс одна память одна камера один распознанный номер.
Все читают и пишут в один и тот же кусок памяти. Магии тут ноль,
просто здравый смысл. Если ты до этого момента не догнал почему так
надо - перечитай ещё раз.

Старая команда run_engine осталась лежать на случай если кто-то
захочет запускать движок отдельно. В обычной жизни она ТЕБЕ НЕ НУЖНА.
Запускаешь runserver и всё, ничего больше не делаешь, всё само.
"""

import logging
import os
import sys
import threading

from django.apps import AppConfig

logger = logging.getLogger(__name__)

# Флажок чтобы движок не запустился дважды. Без него под autoreload
# было бы два YOLO загруженых в память одновременно — это плохо.
_engine_started = False
_engine_lock = threading.Lock()


class ProcessingConfig(AppConfig):
    """
    Django вызывает ready() когда грузит наше приложение. Мы цепляемся
    к этому моменту и запускаем фоновый поток с распознаванием. Всё.
    """

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'processing'

    def ready(self) -> None:
        # Если ты сейчас делаешь миграции, makemigrations, shell или
        # ещё какую-то фигню которая не runserver — НЕ НАДО грузить
        # YOLO. Это занимает кучу памяти и времени. Тихо уходим.
        if not _should_autostart_engine():
            logger.debug('Engine не стартуем (это не runserver), команда=%s', sys.argv[1:2])
            return

        # Django при autoreload запускает себя дважды: родитель смотрит
        # за файлами, дочка реально работает. Без этой проверки мы бы
        # подняли два инстанса YOLO. Один процесс == один движок.
        global _engine_started
        with _engine_lock:
            if _engine_started:
                logger.debug('Опять? Я уже запущен в этом процессе, иди гуляй')
                return
            _engine_started = True

        # YoloDetector грузит .pt файл несколько секунд. Если делать
        # это прямо здесь — runserver встанет на старте и юзер будет
        # сидеть и думать "почему сайт не открывается". Поэтому
        # выкидываем всю инициализацию в отдельный поток, runserver
        # летит дальше своими делами.
        threading.Thread(
            target=_bootstrap_engine,
            name='engine-bootstrap',
            daemon=True,
        ).start()


def _should_autostart_engine() -> bool:
    """
    Тут думаем: запускать движок или нет.

    Правило простое как пробка. Запускаем если:
      1) Команда runserver (а не миграции, не тесты, не shell)
      2) Мы реально в РАБОЧЕМ процессе, а не в watcher'е autoreload

    Watcher отличается от рабочего процесса тем, что у второго в env
    стоит RUN_MAIN=true. Это Django нам так подсказывает. Если ты
    запустил с --noreload, никакого watcher'а вообще нет, тогда
    запускаем без проверок.

    Если хочешь знать ЗАЧЕМ это всё нужно гугли "Django autoreload
    RUN_MAIN", там умные люди уже всё расписали. Не моя работа тебе
    Django объяснять.
    """
    if len(sys.argv) < 2 or sys.argv[1] != 'runserver':
        return False
    if '--noreload' in sys.argv:
        return True
    return os.environ.get('RUN_MAIN') == 'true'


def _bootstrap_engine() -> None:
    """
    Собираем frankenstein'а: детектор + OCR + анализатор + процессор.
    И запускаем его крутиться в фоне.

    Импорты тут ленивые. Потомучто torch и paddleocr весят как
    небольшая планета, и если бы они импортились наверху файла, то
    Django при каждом запуске любой команды (даже makemigrations)
    стартовал бы по 30 секунд. Не надо. Импортим только когда реально
    хотим работать.

    Если что-то отвалится пишем в лог с трейсбеком, и тихо уходим.
    runserver продолжает работать без распознавания, что лучше чем
    лежать колом.
    """
    try:
        from camera_stream.camera.registry import get_camera
        from processing.frame_analyzer import YoloFrameAnalyzer
        from processing.frame_processor import FrameProcessor
        from processing.utils.detectors.yolo_detector import YoloDetector
        from processing.utils.ocrs.easy_ocr import LicensePlateOCR
    except Exception:
        # Скорее всего ты не установил torch или ultralytics. Иди ставь.
        logger.exception('Engine не запущен: импорты отвалились, разбирайся')
        return

    # Путь к .pt модели лежит в .env. Если его нет — значит ты не
    # настроил .env, и я тебе тут не нянька. Иди читай README или
    # как там оно у вас называется.
    model_path = os.getenv('YOLO_MODEL_PATH')
    if not model_path:
        logger.warning('Engine не запущен: YOLO_MODEL_PATH в .env пустой, удачи без распознавания')
        return

    try:
        # Грузим модель YOLO. Тут будет пауза на пару секунд.
        logger.info('Engine: грузим YoloDetector из %s', model_path)
        detector = YoloDetector(model_path)

        # Грузим PaddleOCR. Тут будет ещё пауза и куча шума в логе
        # от самой библиотеки про CUDA, ccache и прочую радость.
        # Это нормально, я её прижал до WARNING в settings.LOGGING,
        # так что должно быть тихо. Если шумит — значит шумит сильно.
        logger.info('Engine: грузим LicensePlateOCR')
        ocr = LicensePlateOCR()

        # А вот тут уже собирается пайплайн. Просто соединяем кубики.
        logger.info('Engine: собираем YoloFrameAnalyzer + FrameProcessor')
        analyzer = YoloFrameAnalyzer(detector, ocr)
        camera = get_camera(ocr=True)
        processor = FrameProcessor(camera, analyzer, FrameProcessor.Mode.FAST)

        # processor.run() — это НЕ блокирующий вызов, он сам внутри
        # стартует поток. Мы тут не зависаем, бутстрап заканчивается,
        # а движок уходит крутиться.
        processor.run()
        logger.info('Engine: всё, поехали, поток крутится')
    except Exception:
        # Что-то развалилось в процессе сборки. PaddleOCR не нашёл
        # модель, YOLO не открыл .pt файл, камера не отвечает —
        # вариантов миллион. Пиши в лог трейсбек, читай его, чини.
        logger.exception('Engine помер на старте, читай трейсбек')

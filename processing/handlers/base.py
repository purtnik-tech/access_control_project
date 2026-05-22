import logging
from collections import Counter
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from access_control.models import PassModel, PassLogsModel, LicensePlateForManualHandle
from processing.frame_analyzer.frame_analyzer import AnalyzerResult


logger = logging.getLogger(__name__)
PASS_DELAY = 2


SYMBOLS = {
    'А': 'A',
    'В': 'B',
    'Е': 'E',
    'К': 'K',
    'М': 'M',
    'Н': 'H',
    'О': 'O',
    'Р': 'P',
    'С': 'C',
    'Т': 'T',
    'У': 'Y',
    'Х': 'X',
}


class NumberFrameHandler:

    def __init__(self, container_size: int = 7):
        self._container_size = container_size
        self._container: list[AnalyzerResult] = []

    def __call__(self, result: AnalyzerResult):
        if not self.add_value(result):
            self._handle()

    @property
    def get_and_reset_container(self) -> list[AnalyzerResult]:
        """
        :return:
        """
        container = list(self._container)
        self._container = []
        return container

    def add_value(self, result: AnalyzerResult) -> bool:
        if len(self._container) == self._container_size:
            return False
        if not result.value.isalpha() and not result.value.isdigit():
            self._container.append(result)
            return True
        return False

    def _handle(self):
        # Номер в строковом представлении
        number = self._detect_number(self.get_and_reset_container)
        # Queryset[Список записей] всех пропусков для этого номера
        pass_queryset = PassModel.objects.filter(subject__vehicle__license_plate__plate_number__icontains=number)
        # Временная метка на PASS_DELAY минут меньше текущей даты
        today_delta = timezone.now() - timedelta(minutes=PASS_DELAY)
        # Ссылка на модель PassModel как объект логов Django
        pass_model_content_type = ContentType.objects.get_for_model(PassModel)
        if pass_queryset.count() == 1:
            self._handle_pass(number, pass_queryset.first())
        elif pass_queryset.count() > 1:
            for pass_instance in pass_queryset:
                if self._handle_pass(number, pass_instance):
                    break
        else:
            logger.warning(f'Для номера {number} не оформлен пропуск')

    @classmethod
    def _handle_number(cls, value: str) -> str:
        value = value.replace('RUS', '')
        for symbol, latin in SYMBOLS.items():
            value = value.replace(symbol, latin)
        return value

    def _detect_number(self, results: list[AnalyzerResult]) -> str:
        """
        Логика обработки сырого номера на основе списка из последних self._container_size извлечённых записей
        :param results: Список номеров, полученных от OCR
        :return: Обработанный номер
        """
        for result in results:
            result.value = self._handle_number(result.value)
        data = [candidate.value.strip() for candidate in results if candidate.value and candidate.value.strip()]
        if not data:
            raise ValueError(f'Не получены данные {results}')
        max_len = max(map(len, data))
        result = []
        for i in range(max_len):
            if chars := [candidate[i] for candidate in data if i < len(candidate)]:
                result.append(Counter(chars).most_common(1)[0][0])
        return ''.join(result)

    @classmethod
    def _handle_pass(cls, number: str, pass_instance: PassModel) -> bool:
        """

        :param number:
        :param pass_instance:
        :return:
        """
        today_delta = timezone.now() - timedelta(minutes=PASS_DELAY)
        pass_model_content_type = ContentType.objects.get_for_model(PassModel)
        log_queryset = PassLogsModel.objects.filter(
            content_type=pass_model_content_type, creation_date__gte=today_delta, key=pass_instance.id
        )
        if pass_instance.pass_type == PassModel.TypesPass.PERMANENT and not log_queryset.exists():
            # Логика автоматического открытия шлагбаума
            PassLogsModel.objects.create(
                content_type=pass_model_content_type,
                message=f'Автоматическое открытие шлагбаума. Пропуск {pass_instance}',
                key=pass_instance.id
            )
            return True
        elif pass_instance.pass_type == PassModel.TypesPass.TEMPORARY and not log_queryset.exists():
            result = False
            plates_for_handle_instance, create = LicensePlateForManualHandle.objects.get_or_create(
                license_plate=pass_instance.subject.vehicle.license_plate
            )
            if create:
                PassLogsModel.objects.create(
                    content_type=ContentType.objects.get_for_model(LicensePlateForManualHandle),
                    message=f'Создана запись ручной обработки для номера {number}',
                    key=plates_for_handle_instance.id
                )
                result = True
            PassLogsModel.objects.create(
                content_type=pass_model_content_type,
                message=f'Требуется ручное открытие шлагбаума. Пропуск {pass_instance}',
                key=pass_instance.id
            )
            return result
        else:
            logger.info(f'Ожидание таймаута для номера {number}. Пропуск {pass_instance}')
        return False
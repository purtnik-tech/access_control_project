import logging
import uuid
from http import HTTPStatus


from django.contrib.contenttypes.models import ContentType
from django.core.paginator import Paginator
from django.db.models import Value
from django.db.models.functions import Concat
from django.db.transaction import atomic
from django.shortcuts import get_object_or_404
from django.views.generic import TemplateView, ListView, FormView
from django.http import JsonResponse, HttpResponseNotAllowed

from .forms import CreatePassForm
from .models import LicensePlateForManualHandleModel, PassLogsModel, PassModel, LicensePlate, Vehicle, AccessSubject

logger = logging.getLogger(__name__)
LICENSE_PLATE_FOR_MANUAL_HANDLE_OFFSET = 20
LOGS_OFFSET = 50


class ControlPanelView(TemplateView):
    """
    Основное представление для отображения страницы контрольной панели
    """
    template_name = 'access_control/control_panel.html'
    extra_context = {'title': 'Панель управления'}


class PassListView(ListView):
    """
    Представление для отображения списка всех пропусков
    """
    template_name = 'access_control/passes.html'
    extra_context = {'title': 'Список пропусков'}
    queryset = PassModel.objects.all()


class CreatePassFormView(FormView):
    """
    Представления для отображения формы создания пропуска
    """
    template_name = 'access_control/create_pass.html'
    form_class = CreatePassForm
    success_url = 'access_control:passes'

def logs_view(reqeust) -> HttpResponseNotAllowed | JsonResponse:
    """

    :param reqeust:
    :return:
    """
    if reqeust.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    page = reqeust.GET.get('page', 1)
    queryset = (
        PassLogsModel.objects.
        select_related('content_type').
        annotate(username=Concat('user__last_name', Value(' '), 'user__first_name')).
        all()
    )
    paginator = Paginator(queryset, LOGS_OFFSET)
    page_instance = paginator.page(page)
    data = {
        'result': list(page_instance.object_list.values('creation_date', 'content_type__model', 'key', 'message', 'username')),
        'current_page': page_instance.number,
        'last_page': paginator.num_pages
    }
    if page_instance.has_next():
        data.update(next_page=page_instance.next_page_number())
    if page_instance.has_previous():
        data.update(prev_page=page_instance.previous_page_number())
    return JsonResponse(data, status=HTTPStatus.OK)

def license_plates_for_manual_handle_view(request) -> HttpResponseNotAllowed | JsonResponse:
    """

    :param request:
    :return:
    """
    if request.method != 'GET':
        return HttpResponseNotAllowed(['GET'])
    queryset = LicensePlateForManualHandleModel.objects.select_related('license_plate').all()
    queryset = queryset[:LICENSE_PLATE_FOR_MANUAL_HANDLE_OFFSET]
    return JsonResponse(
        data={'result': list(queryset.values_list('license_plate__plate_number', 'id'))}, status=HTTPStatus.OK
    )


def handle_license_plate_for_manual(request, pk: uuid.UUID, action: str) -> JsonResponse:
    """

    :param request:
    :param pk:
    :param action:
    :return:
    """
    instance = get_object_or_404(LicensePlateForManualHandleModel, pk=pk)
    match action:
        case 'reject':
            message = f'Отказано во въезде для номера: {instance.license_plate.plate_number}'
        case 'allow':
            # Логика поднятия шлагбаума
            message = f'Разрешён въезд вручную для номера: {instance.license_plate.plate_number}'
        case _:
            return JsonResponse({'error': f'Разрешённые действия: allow, reject'}, status=HTTPStatus.BAD_REQUEST)
    content_type = ContentType.objects.get_for_model(LicensePlateForManualHandleModel)
    PassLogsModel.objects.create(content_type=content_type, key=pk, message=message, user=request.user)
    instance.delete()
    return JsonResponse({'pk': pk}, status=HTTPStatus.NO_CONTENT)

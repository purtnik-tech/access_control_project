from django.urls import path
from . import views


app_name = 'access_control'
urlpatterns = [
    # Основные страницы и API (существовавшие ранее)
    path('', views.ControlPanelView.as_view(), name='control_panel'),
    path('logs/', views.logs_view, name='logs'),
    path('passes/', views.PassListView.as_view(), name='passes'),
    path('create_pass/', views.CreatePassFormView.as_view(), name='create_pass'),
    path('license_plates/for_manual_handle/', views.license_plates_for_manual_handle_view, name='licence_plates_for_manual_handle_view'),
    path('license_plates/for_manual_handle/<uuid:pk>/<str:action>/', views.handle_license_plate_for_manual, name='licence_plates_for_manual_handled'),

]
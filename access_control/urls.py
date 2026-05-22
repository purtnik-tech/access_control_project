from django.urls import path
from . import views

urlpatterns = [
    # Основные страницы и API (существовавшие ранее)
    path('', views.ControlPanelView.as_view(), name='control_panel'),

    path('license_plates/for_manual_handle/', views.licence_plates_for_manual_handle_view, name='licence_plates_for_manual_handle_view'),
    path('license_plates/for_manual_handle/<uuid:pk>/<str:action>/', views.handle_license_plate_for_manual, name='licence_plates_for_manual_handled'),

    path('video_feed/', views.video_feed, name='video_feed'),
    path('status/', views.status, name='status'),
    path('recognition_history/', views.recognition_history, name='recognition_history'),

    # Аутентификация
    path('login/', views.user_login, name='login'),
    path('logout/', views.user_logout, name='logout'),

    # Рабочие столы по ролям
    path('post/', views.post_dashboard, name='post_dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('it-dashboard/', views.it_dashboard, name='it_dashboard'),

    # Действия для поста охраны (AJAX)
    path('add-pass/', views.add_pass, name='add_pass'),
    path('allow-access/', views.allow_access, name='allow_access'),
    path('deny-access/', views.deny_access, name='deny_access'),
]
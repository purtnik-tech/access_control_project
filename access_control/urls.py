from django.urls import path
from . import views

urlpatterns = [
    # Основные страницы и API (существовавшие ранее)
    path('', views.index, name='index'),
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
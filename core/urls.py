# core/urls.py
from django.urls import path, include
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('accounts/', include('allauth.urls')),  # allauth 라우트 추가
    path('', views.main, name='main'),
]

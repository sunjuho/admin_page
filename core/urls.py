# core/urls.py
from django.urls import path
from django.views.generic import RedirectView

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    # path('', RedirectView.as_view(pattern_name='main', permanent=False)),
    path('main/', views.main, name='main'),
]

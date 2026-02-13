"""
URL configuration for adminPage project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [
    # 어드민 로그인 주소 대신 내 로그인 페이지로 리다이렉트
    # path('admin/login/', login_redirect),
    path('admin/login/', RedirectView.as_view(url='/accounts/login/', query_string=True)),
    path('admin/', admin.site.urls),

    # 소셜 로그인 관련 (allauth)
    path('accounts/', include('allauth.urls')),

    # 앱의 urls 연결
    path('', include('core.urls')),

]

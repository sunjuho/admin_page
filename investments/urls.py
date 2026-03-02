from django.urls import path

from .views import AccountCreateView, AccountListView, AccountUpdateView, AccountDeleteView
from . import views

app_name = 'investments'  # 이게 있어야 'investments:account_create' 가능

urlpatterns = [
    # /investments/account/create/
    path('account/create/', AccountCreateView.as_view(), name='account_create'),
    # /investments/account/list/
    path('account/list/', AccountListView.as_view(), name='account_list'),
    # /investments/account/<int:pk>/update/
    path('account/<int:pk>/update/', AccountUpdateView.as_view(), name='account_update'),
    # /investments/account/<int:pk>/delete/
    path('account/<int:pk>/delete/', AccountDeleteView.as_view(), name='account_delete'),
    # /investments/account/<int:pk>/delete/ajax/
    path('account/<int:pk>/delete/ajax/', views.account_delete_ajax, name='account_delete_ajax'),
]

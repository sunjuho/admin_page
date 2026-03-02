from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, ListView, UpdateView, DeleteView

from .models import Account


# 계좌 등록 뷰 (Create)
class AccountCreateView(LoginRequiredMixin, CreateView):
    model = Account
    fields = ['name', 'account_number', 'hts_id', 'app_key', 'secret_key']  # 사용자에게 입력받을 필드
    template_name = 'investments/account_form.html'  # 사용할 HTML 파일
    # 등록 성공 시 이동할 URL 패턴 이름
    success_url = reverse_lazy('investments:account_list')

    # 자바의 @RequestBody에 현재 사용자 세팅하는 로직과 동일
    def form_valid(self, form):
        # 현재 로그인한 사용자를 계좌의 주인(Owner)으로 자동 지정
        form.instance.owner = self.request.user
        return super().form_valid(form)


# 계좌 목록 뷰 (List)
class AccountListView(LoginRequiredMixin, ListView):
    model = Account
    template_name = 'investments/account_list.html'
    context_object_name = 'accounts'  # HTML에서 사용할 변수명 (기본값은 object_list)

    def get_queryset(self):
        # 로그인한 사용자의 계좌만 필터링
        return Account.objects.filter(owner=self.request.user)


# 계좌 수정 뷰(Update)
class AccountUpdateView(LoginRequiredMixin, UpdateView):
    model = Account
    # 수정 가능한 필드 지정 (보통 계좌번호는 수정을 막기도 하지만, 일단 포함합니다)
    fields = ['name', 'account_number', 'hts_id', 'app_key', 'secret_key']
    template_name = 'investments/account_form.html'  # CreateView와 같은 템플릿 재사용 가능!
    success_url = reverse_lazy('investments:account_list')

    # 보안: 남의 계좌를 URL ID값으로 때려 맞춰서 수정하지 못하게 방어 (자바의 권한 체크)
    def get_queryset(self):
        return Account.objects.filter(owner=self.request.user)


# 계좌 삭제 뷰 (Delete)
class AccountDeleteView(LoginRequiredMixin, DeleteView):
    model = Account
    # 삭제 후 돌아갈 페이지 (계좌 목록)
    success_url = reverse_lazy('investments:account_list')

    # 본인 계좌만 삭제할 수 있도록 쿼리셋 제한 (보안상 매우 중요!)
    def get_queryset(self):
        return Account.objects.filter(owner=self.request.user)


# 계좌 삭제 AJAX (Delete)
@require_POST  # POST 요청만 허용 (보안)
def account_delete_ajax(request, pk):
    # 내 계좌인지 확인하고 가져오기 (보안)
    account = get_object_or_404(Account, pk=pk, owner=request.user)
    account.delete()

    # 자바의 ResponseEntity.ok()와 같음
    return JsonResponse({'status': 'success', 'message': '삭제되었습니다.'})

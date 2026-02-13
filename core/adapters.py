# 특정 event에 대해 "일을 진행할지 말지" 결정하는 중간 관리자

from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

from .models import AllowedEmail


class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    # 로그인 성공 전에 동작해야 하는 필터링이라 어댑터
    def pre_social_login(self, request, sociallogin):
        # 1. 관리자(Superuser)는 체크 제외
        if sociallogin.user.is_superuser:
            return

        email = sociallogin.user.email

        # 2. 허용 리스트 확인
        if not AllowedEmail.objects.filter(email=email).exists():
            # 사용자에게 보여줄 메시지 추가
            messages.error(request, f"등록되지 않은 이메일({email})입니다. 관리자에게 승인을 요청하세요.")

            # 로그인 프로세스를 중단하고 즉시 메인(또는 로그인) 페이지로 리다이렉트
            # 'account_login'은 allauth에서 제공하는 로그인 페이지의 URL 네임입니다.
            raise ImmediateHttpResponse(redirect('account_login'))

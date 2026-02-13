# 특정 event에 대해 "일을 진행할지 말지" 결정하는 중간 관리자

import os

from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.contrib import messages
from django.shortcuts import redirect

from core.models import AllowedEmail


class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    # 로그인 성공 전에 동작해야 하는 필터링이라 어댑터
    def pre_social_login(self, request, sociallogin):
        email = sociallogin.user.email

        # 특정 이메일은 자동으로 슈퍼유저/스태프 권한 부여
        admin_emails = os.getenv('SUPERUSER_EMAILS', '').split(',')
        if email in admin_emails:
            user = sociallogin.user
            user.is_superuser = True
            user.is_staff = True

        # 관리자(Superuser)는 체크 제외
        if sociallogin.user.is_superuser:
            return

        # 허용 리스트 확인
        if not AllowedEmail.objects.filter(email=email).exists():
            # 사용자에게 보여줄 메시지 추가
            messages.error(request, f"등록되지 않은 이메일({email})입니다.")

            # 로그인 프로세스를 중단하고 즉시 메인(또는 로그인) 페이지로 리다이렉트
            raise ImmediateHttpResponse(redirect('account_login'))

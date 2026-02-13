# 특정 event에 대해 "일을 진행할지 말지" 결정하는 중간 관리자

from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.forms import ValidationError

from .models import AllowedEmail


class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    # 로그인 성공 전에 동작해야 하는 필터링이라 어댑터
    def pre_social_login(self, request, sociallogin):
        """
        소셜 로그인이 완료되기 직전에 호출됩니다.
        """
        email = sociallogin.user.email

        # 1. 관리자(Superuser)는 화이트리스트 체크를 건너뜁니다 (관리자 접속 보장)
        if sociallogin.user.is_superuser:
            return

        # 2. 허용된 이메일 목록에 있는지 확인
        if not AllowedEmail.objects.filter(email=email).exists():
            raise ValidationError(
                f"등록되지 않은 이메일({email})입니다. 관리자에게 문의하세요."
            )

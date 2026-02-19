from django.db import models
from django.utils import timezone
from datetime import timedelta

# 한투 계좌
class Account(models.Model):
    name = models.CharField(max_length=50, help_text="계좌 별명 (예: 메인 투자계좌)")
    account_number = models.CharField(max_length=20, unique=True, verbose_name="계좌번호")

    # API 접속 정보 (실전 계좌용)
    app_key = models.CharField(max_length=200)
    secret_key = models.CharField(max_length=200)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.account_number})"

    class Meta:
        verbose_name = "한투 계좌"
        verbose_name_plural = "한투 계좌 목록"


class Token(models.Model):
    # 계좌 하나당 하나의 토큰만 관리 (1:1 관계)
    account = models.OneToOneField(Account, on_delete=models.CASCADE, related_name='token')

    access_token = models.TextField(verbose_name="접근 토큰")

    # 한투에서 응답받은 실제 만료 시간 (보통 24시간)
    issued_at = models.DateTimeField(auto_now_add=True, verbose_name="발급 일시")
    expired_at = models.DateTimeField(verbose_name="공식 만료 일시")

    # 관리용 필드
    is_valid = models.BooleanField(default=True, verbose_name="유효 여부")

    def __str__(self):
        return f"Token for {self.account.name}"

    @property
    def is_expired_custom(self):
        """
        23시간이 지났는지 체크하는 로직
        True면 새로 발급받아야 함
        """
        if not self.is_valid:
            return True

        # 발급된 지 23시간이 지났는지 확인
        refresh_limit = self.issued_at + timedelta(hours=23)
        return timezone.now() >= refresh_limit

    class Meta:
        verbose_name = "API 토큰"
        verbose_name_plural = "API 토큰 목록"
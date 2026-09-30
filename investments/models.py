from datetime import timedelta

from django.conf import settings  # 유저 모델 참조용
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

from investments.strategies import get_strategy_choices


# 한투 계좌
class Account(models.Model):
    # 숫자 10자리 정규식 설정
    numeric_filter = RegexValidator(
        regex=r'^\d{10}$',
        message='계좌번호는 숫자 10자리여야 합니다.'
    )

    # 소유자 필드 추가 (로그인한 유저)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='accounts',
        verbose_name="소유자"
    )
    name = models.CharField(max_length=50,
                            help_text="계좌 별명 (예: 메인 투자계좌)")
    account_number = models.CharField(max_length=10,
                                      unique=True,
                                      validators=[numeric_filter],
                                      verbose_name="계좌번호",
                                      help_text="'-'없이 10자리")
    hts_id = models.CharField(max_length=20)

    app_key = models.CharField(max_length=200)
    secret_key = models.CharField(max_length=200)

    # 투자 전략 (investments/strategies/<key>.md 의 key, 비어 있으면 배치 대상 제외)
    # 선택지는 md 파일에서 동적으로 읽어오므로 전략을 추가해도 마이그레이션 불필요
    strategy = models.CharField(max_length=50,
                                blank=True,
                                default="",
                                choices=get_strategy_choices,
                                verbose_name="투자 전략")

    # 한투 API 접근 토큰 (계좌당 1개, 발급 전에는 비어 있음)
    access_token = models.TextField(blank=True, default="", verbose_name="접근 토큰")

    # 한투에서 응답받은 실제 만료 시간 (보통 24시간)
    token_issued_at = models.DateTimeField(null=True, blank=True, verbose_name="토큰 발급 일시")
    token_expired_at = models.DateTimeField(null=True, blank=True, verbose_name="토큰 공식 만료 일시")

    # 관리용 필드
    token_is_use = models.BooleanField(default=True, verbose_name="토큰 사용 여부")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.owner.username}의 {self.name} ({self.account_number})"

    @property
    def is_token_expired(self):
        """
        토큰이 없거나 발급된 지 23시간이 지났는지 체크하는 로직
        True면 새로 발급받아야 함
        """
        if not self.access_token or not self.token_is_use or self.token_issued_at is None:
            return True

        # 발급된 지 23시간이 지났는지 확인
        refresh_limit = self.token_issued_at + timedelta(hours=23)
        return timezone.now() >= refresh_limit

    class Meta:
        verbose_name = "한투 계좌"
        verbose_name_plural = "한투 계좌 목록"

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    # 구글에서 받은 정보를 저장하거나, 서비스 전용 필드 추가
    profile_image_url = models.URLField(blank=True, null=True)


# 구글 로그인 / 유저 등록 시 허용할 이메일 목록
class AllowedEmail(models.Model):
    email = models.EmailField(unique=True)
    description = models.CharField(max_length=100, blank=True, help_text="이메일 사용자 메모")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.email

    class Meta:
        verbose_name = "허용된 이메일"
        verbose_name_plural = "허용된 이메일"

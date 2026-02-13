from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, AllowedEmail


# 커스텀 유저 모델 등록
@admin.register(User)
class MyUserAdmin(UserAdmin):
    # 여기에 유저 관리 화면 설정을 추가할 수 있습니다.
    pass


# 허용 이메일 모델 등록
@admin.register(AllowedEmail)
class AllowedEmailAdmin(admin.ModelAdmin):
    list_display = ('email', 'description', 'created_at')
    search_fields = ('email', 'description')

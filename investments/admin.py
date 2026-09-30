from django.contrib import admin
from .models import Account

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'account_number', 'strategy', 'get_token_status', 'token_expired_at', 'created_at')
    list_filter = ('strategy',)
    # 어드민 폼에서 owner 필드 제외
    exclude = ('owner',)
    # 토큰 값은 API 발급 결과로만 채워지므로 읽기 전용 (사용 여부만 수정 가능)
    readonly_fields = ('access_token', 'token_issued_at', 'token_expired_at')

    def save_model(self, request, obj, form, change):
        # 새로 생성되는 경우(change=False) 소유주를 현재 로그인 유저로 자동 할당
        if not change:
            obj.owner = request.user
        super().save_model(request, obj, form, change)

    def get_token_status(self, obj):
        if not obj.access_token:
            return "토큰 없음"
        return "갱신 필요" if obj.is_token_expired else "유효함"
    get_token_status.short_description = "토큰 상태"

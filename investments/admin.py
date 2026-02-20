from django.contrib import admin
from .models import Account, Token

# Token 을 어떻게 보여줄지 정의
class TokenInline(admin.StackedInline):
    model = Token
    extra = 0 # 추가로 보여줄 빈 입력 칸의 개수
    readonly_fields = ('access_token', 'issued_at', 'expired_at')

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'account_number', 'get_token_status','created_at')
    # 어드민 폼에서 owner 필드 제외
    exclude = ('owner',)
    # Account 페이지 하단에 TokenInline 노출
    inlines = [TokenInline]

    def save_model(self, request, obj, form, change):
        # 새로 생성되는 경우(change=False) 소유주를 현재 로그인 유저로 자동 할당
        if not change:
            obj.owner = request.user
        super().save_model(request, obj, form, change)

    def get_token_status(self, obj):
        try:
            return "갱신 필요" if obj.token.is_expired_custom else "유효함"
        except Token.DoesNotExist:
            return "토큰 없음"
    get_token_status.short_description = "토큰 상태"

@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ('account', 'issued_at', 'expired_at', 'is_valid')
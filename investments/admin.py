from django.contrib import admin
from .models import Account, Token

class TokenInline(admin.StackedInline):
    model = Token
    extra = 0
    readonly_fields = ('issued_at', 'expired_at')

@admin.register(Account)
class AccountAdmin(admin.ModelAdmin):
    list_display = ('name', 'account_number', 'get_token_status', 'created_at')
    inlines = [TokenInline]

    def get_token_status(self, obj):
        try:
            if obj.token.is_expired_custom:
                return "갱신 필요 (23시간 경과)"
            return "유효함"
        except Token.DoesNotExist:
            return "토큰 없음"
    get_token_status.short_description = "토큰 상태"

@admin.register(Token)
class TokenAdmin(admin.ModelAdmin):
    list_display = ('account', 'issued_at', 'expired_at', 'is_valid')
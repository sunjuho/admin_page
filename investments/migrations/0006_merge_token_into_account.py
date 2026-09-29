from django.db import migrations, models


def copy_token_to_account(apps, schema_editor):
    # 기존 Token 데이터를 Account로 복사
    Token = apps.get_model('investments', 'Token')
    for token in Token.objects.select_related('account'):
        account = token.account
        account.access_token = token.access_token
        account.token_issued_at = token.issued_at
        account.token_expired_at = token.expired_at
        account.token_is_use = token.is_use
        account.save(update_fields=['access_token', 'token_issued_at', 'token_expired_at', 'token_is_use'])


def copy_account_to_token(apps, schema_editor):
    # 롤백 시 Account의 토큰 데이터를 Token으로 복원
    Account = apps.get_model('investments', 'Account')
    Token = apps.get_model('investments', 'Token')
    for account in Account.objects.exclude(access_token=''):
        Token.objects.create(
            account=account,
            access_token=account.access_token,
            issued_at=account.token_issued_at,
            expired_at=account.token_expired_at,
            is_use=account.token_is_use,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('investments', '0005_alter_account_account_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='account',
            name='access_token',
            field=models.TextField(blank=True, default='', verbose_name='접근 토큰'),
        ),
        migrations.AddField(
            model_name='account',
            name='token_issued_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='토큰 발급 일시'),
        ),
        migrations.AddField(
            model_name='account',
            name='token_expired_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='토큰 공식 만료 일시'),
        ),
        migrations.AddField(
            model_name='account',
            name='token_is_use',
            field=models.BooleanField(default=True, verbose_name='토큰 사용 여부'),
        ),
        migrations.RunPython(copy_token_to_account, copy_account_to_token),
        migrations.DeleteModel(
            name='Token',
        ),
    ]

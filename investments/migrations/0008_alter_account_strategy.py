# 매매 전략 필드 표시 이름 변경 ('투자 전략' -> '매매 전략')

import investments.strategies
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('investments', '0007_account_strategy'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='strategy',
            field=models.CharField(blank=True, choices=investments.strategies.get_strategy_choices, default='', max_length=50, verbose_name='매매 전략'),
        ),
    ]

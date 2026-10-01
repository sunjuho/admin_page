"""
balance_check 전략 디버깅용 스크립트 (파이참 Python 실행 구성으로 Debug 실행)

주의: 로컬 db.sqlite3의 실제 계좌/토큰으로 KIS API를 실제 호출합니다.
"""
import os
import sys
from pathlib import Path

# 프로젝트 루트(manage.py 위치)를 import 경로에 추가
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'adminPage.settings.local')
django.setup()

from investments.models import Account
from investments.services.kis.kis_overseas_stock import KisOverseasStockClient
from investments.strategies import get_strategy

STRATEGY_KEY = 'balance_check'

account = Account.objects.first()  # 특정 계좌는 Account.objects.get(pk=...) 로 지정
if account is None:
    raise SystemExit('등록된 계좌가 없습니다.')

strategy = get_strategy(STRATEGY_KEY)
if strategy is None:
    raise SystemExit(f"전략 '{STRATEGY_KEY}'이(가) 없거나 비활성화되어 있습니다.")

client = KisOverseasStockClient(account)
print(strategy.run(account, client))  # <- 필요하면 strategy.run 안에 브레이크포인트

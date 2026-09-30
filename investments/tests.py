import os
import sqlite3
import sys
from io import StringIO
from pathlib import Path
from unittest import mock

import django
import pandas as pd
import requests
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from django_q.models import Schedule

from investments.models import Account
from investments.services.kis_overseas_stock import KisOverseasStockClient
from investments.services.tasks import run_all_strategies, run_account_strategy
from investments.strategies import get_strategy_choices, load_strategies

User = get_user_model()


class KisRealDatabaseIntegrationTest(TestCase):
    """
    실제 DB(db.sqlite3)에 등록된 계좌(Account)와 토큰 데이터를 바탕으로
    토큰이 만료된 경우에만 재발급받아 잔고 조회(inquire_balance)를 수행하는 테스트
    """

    @classmethod
    def setUpTestData(cls):
        # 1. 실제 SQLite DB 파일 경로 확인
        real_db_path = settings.BASE_DIR / 'db.sqlite3'
        if not real_db_path.exists():
            return

        # 2. 실제 DB로부터 User, Account(토큰 포함) 데이터를 테스트 DB로 동기화
        try:
            conn = sqlite3.connect(real_db_path)
            cur = conn.cursor()

            # 유저 정보 동기화
            users = cur.execute(
                "SELECT id, username, email, password, is_active, is_staff, is_superuser FROM core_user"
            ).fetchall()
            for u in users:
                User.objects.update_or_create(
                    id=u[0],
                    defaults={
                        'username': u[1],
                        'email': u[2],
                        'password': u[3],
                        'is_active': bool(u[4]),
                        'is_staff': bool(u[5]),
                        'is_superuser': bool(u[6]),
                    }
                )

            # 계좌 정보 동기화 (토큰 정보 포함)
            accounts = cur.execute(
                "SELECT id, name, account_number, hts_id, app_key, secret_key, owner_id, "
                "access_token, token_issued_at, token_expired_at, token_is_use FROM investments_account"
            ).fetchall()
            for acc in accounts:
                owner = User.objects.filter(id=acc[6]).first() or User.objects.first()
                Account.objects.update_or_create(
                    id=acc[0],
                    defaults={
                        'name': acc[1],
                        'account_number': acc[2],
                        'hts_id': acc[3],
                        'app_key': acc[4],
                        'secret_key': acc[5],
                        'owner': owner,
                        'access_token': acc[7],
                        'token_issued_at': acc[8],
                        'token_expired_at': acc[9],
                        'token_is_use': bool(acc[10]),
                    }
                )

            conn.close()
        except Exception as e:
            print(f"[Warning] Failed to import real DB accounts/tokens: {e}")

    def test_kis_real_account_connection_and_balance(self):
        """
        실제 DB의 계좌 데이터를 조회하고, 토큰이 만료된 경우에만 재발급하여
        계좌별 잔고 조회(inquire_balance)를 수행
        """
        accounts = list(Account.objects.all().order_by('id'))
        if not accounts:
            self.skipTest("실제 DB에 등록된 계좌가 없습니다.")

        print(f"\n[INFO] 실제 DB에서 로드된 계좌 수: {len(accounts)}개")
        for acc in accounts:
            print(f" - 계좌 ID: {acc.id}, 별칭: {acc.name}, 번호: {acc.account_number}")

        clients = []
        for idx, acc in enumerate(accounts, start=1):
            print(f"\n=== [계좌 {idx}: {acc.name} ({acc.account_number})] ===")

            # 1. 토큰 상태 확인 (만료 여부 체크)
            now = timezone.now()
            has_token = bool(acc.access_token)

            is_expired = True
            if has_token and acc.token_expired_at:
                exp = acc.token_expired_at
                if timezone.is_naive(exp):
                    exp = timezone.make_aware(exp)
                # 만료일시가 지났거나 is_token_expired가 True인 경우 만료로 판정
                is_expired = (now >= exp) or acc.is_token_expired

            if not has_token:
                print(f"[계좌 {idx}] 저장된 토큰 없음 -> 토큰 신규 발급 진행")
            elif is_expired:
                print(f"[계좌 {idx}] 토큰 만료됨 (기존 만료일시: {acc.token_expired_at}) -> 토큰 재발급 진행")
                # 만료된 토큰을 비워서 클라이언트가 신규 토큰 발급을 시도하도록 함
                acc.access_token = ""
                acc.save(update_fields=["access_token"])
            else:
                print(f"[계좌 {idx}] 기존 토큰 유효함 (만료일시: {acc.token_expired_at}) -> 기존 토큰 재사용")

            # 2. KisOverseasStockClient 생성 (유효하면 기존 토큰 재사용, 만료되었으면 새 토큰 발급 요청)
            client = KisOverseasStockClient(acc)

            # 3. 토큰 발급/보유 상태 검증
            active_token = client.ka.read_token()
            if not active_token:
                # 한투 서버로부터 토큰 발급이 실패한 경우 상세 사유 진단
                token_url = f"{settings.KIS_URL}/oauth2/tokenP"
                token_payload = {
                    "grant_type": "client_credentials",
                    "appkey": acc.app_key,
                    "appsecret": acc.secret_key,
                }
                res = requests.post(token_url, json=token_payload, headers={"Content-Type": "application/json"})
                print(f"\n[ERROR] 계좌 {idx} 토큰 발급 실패! (한투 서버 응답코드: {res.status_code})")
                print(f" - 응답 내용: {res.text}")
                if "EGW00103" in res.text:
                    print(" - [원인 분석] 등록된 AppKey가 유효하지 않거나 만료되었습니다.")
                    print("   한국투자증권 Open API 포털(https://apiportal.koreainvestment.com)에서")
                    print("   새로운 AppKey / SecretKey를 발급받아 계좌 정보에 등록해야 정상 조회가 가능합니다.")
                continue

            # 새로 발급된 토큰이 있는 경우, 실제 원본 DB(db.sqlite3)에도 동기화 반영
            acc.refresh_from_db()
            if acc.access_token and is_expired:
                real_db_path = settings.BASE_DIR / 'db.sqlite3'
                try:
                    conn = sqlite3.connect(real_db_path)
                    cur = conn.cursor()
                    cur.execute(
                        """
                        UPDATE investments_account
                        SET access_token = ?, token_issued_at = ?, token_expired_at = ?, token_is_use = 1
                        WHERE id = ?
                        """,
                        (
                            acc.access_token,
                            str(acc.token_issued_at),
                            str(acc.token_expired_at),
                            acc.id,
                        ),
                    )
                    conn.commit()
                    conn.close()
                    print(f"[계좌 {idx}] [동기화] 새로 발급된 토큰 및 발급일시를 실제 DB(db.sqlite3)에 성공적으로 저장했습니다! (만료: {acc.token_expired_at})")
                except Exception as e:
                    print(f"[계좌 {idx}] 실제 DB 토큰 동기화 실패: {e}")

            clients.append(client)

            # 4. 유효한 토큰으로 실제 잔고 조회 실행
            print(f"[계좌 {idx}] 잔고 조회 API (/uapi/overseas-stock/v1/trading/inquire-balance) 호출")
            df1, df2 = client.inquire_balance()

            print(f"[계좌 {idx} 보유종목 데이터프레임 (output1)]:\n{df1}")
            print(f"[계좌 {idx} 외화잔고/정산 데이터프레임 (output2)]:\n{df2}")

            self.assertEqual(client.account.id, acc.id)

        # 5. 다중 계좌일 경우 상호 독립성 검증
        if len(clients) >= 2:
            self.assertIsNot(clients[0], clients[1])
            self.assertIsNot(clients[0].ka, clients[1].ka)
            self.assertNotEqual(clients[0].account.account_number, clients[1].account.account_number)
            print("\n[SUCCESS] 다중 계좌 클라이언트가 서로 간섭 없이 독립적으로 연결 및 조회되었습니다.")


class StrategyBatchTest(TestCase):
    """
    투자 전략 레지스트리/배치 단위 테스트 (한투 API는 mock 처리 → 실제 호출 없음)
    실행: python manage.py test investments.tests.StrategyBatchTest
    """

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='tester', email='tester@example.com')
        cls.acc_with_strategy = Account.objects.create(
            owner=cls.user, name='전략계좌', account_number='1234567801',
            hts_id='hts', app_key='k', secret_key='s', strategy='balance_check',
        )
        cls.acc_without_strategy = Account.objects.create(
            owner=cls.user, name='일반계좌', account_number='1234567802',
            hts_id='hts', app_key='k', secret_key='s',
        )

    def test_registry_loads_md_and_skips_template(self):
        strategies = load_strategies()
        self.assertIn('balance_check', strategies)
        self.assertNotIn('_template', strategies)
        self.assertEqual(strategies['balance_check'].name, '잔고 조회 (예시)')
        self.assertIn(('balance_check', '잔고 조회 (예시)'), get_strategy_choices())

    def test_model_rejects_unknown_strategy(self):
        self.acc_with_strategy.strategy = 'not_exists'
        with self.assertRaises(ValidationError):
            self.acc_with_strategy.full_clean()

    @mock.patch('investments.services.tasks.async_task')
    def test_run_all_strategies_enqueues_only_accounts_with_strategy(self, mock_async):
        result = run_all_strategies()

        mock_async.assert_called_once()
        self.assertEqual(mock_async.call_args.args[1], self.acc_with_strategy.id)
        self.assertEqual(result, '1개 계좌 전략 작업 등록')

    @mock.patch('investments.services.kis_overseas_stock.KisOverseasStockClient')
    def test_run_account_strategy_calls_strategy(self, mock_client_cls):
        mock_client_cls.return_value.inquire_balance.return_value = (
            pd.DataFrame([{'ovrs_pdno': 'AAPL'}, {'ovrs_pdno': 'TSLA'}]), pd.DataFrame(),
        )

        result = run_account_strategy(self.acc_with_strategy.id)

        mock_client_cls.assert_called_once()
        self.assertEqual(result, '[잔고 조회 (예시)] 전략계좌: 보유 종목 2개')

    @mock.patch('investments.services.kis_overseas_stock.KisOverseasStockClient')
    def test_run_account_strategy_skips_unknown_strategy(self, mock_client_cls):
        Account.objects.filter(id=self.acc_with_strategy.id).update(strategy='deleted_strategy')

        result = run_account_strategy(self.acc_with_strategy.id)

        mock_client_cls.assert_not_called()  # 전략이 없으면 API 호출도 하지 않음
        self.assertIn('건너뜀', result)

    def test_setup_schedule_command_is_idempotent(self):
        call_command('setup_strategy_schedule', '--time', '22:40', stdout=StringIO())
        call_command('setup_strategy_schedule', '--time', '23:10', stdout=StringIO())

        schedules = Schedule.objects.filter(func='investments.services.tasks.run_all_strategies')
        self.assertEqual(schedules.count(), 1)
        next_run = timezone.localtime(schedules.first().next_run)
        self.assertEqual((next_run.hour, next_run.minute), (23, 10))


if __name__ == '__main__':
    # 단독 실행 지원 (예: python investments/tests.py)
    BASE_DIR = Path(__file__).resolve().parent.parent
    sys.path.append(str(BASE_DIR))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'adminPage.settings.local')
    django.setup()

    from django.test.runner import DiscoverRunner
    test_runner = DiscoverRunner(verbosity=2)
    failures = test_runner.run_tests(['investments.tests'])
    sys.exit(bool(failures))

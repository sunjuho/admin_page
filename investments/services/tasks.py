# 투자 전략 배치 (django-q2)
# 흐름: 스케줄 → run_all_strategies → 계좌마다 run_account_strategy 작업을 큐에 등록 → 워커가 병렬 실행
import logging

from django_q.tasks import async_task

from investments.models import Account
from investments.strategies import get_strategy

logger = logging.getLogger(__name__)


def run_all_strategies():
    """전략이 선택된 모든 계좌에 대해 계좌별 작업을 큐에 등록 (스케줄에서 호출)"""
    account_ids = list(
        Account.objects.exclude(strategy="").values_list("id", flat=True)
    )

    for account_id in account_ids:
        # 계좌별로 작업을 분리 → 한 계좌가 실패해도 다른 계좌는 계속 실행됨
        async_task(
            "investments.services.tasks.run_account_strategy",
            account_id,
            task_name=f"전략 실행 - 계좌 {account_id}",
        )

    return f"{len(account_ids)}개 계좌 전략 작업 등록"  # 이 리턴값은 DB에 결과로 저장됨


def run_account_strategy(account_id):
    """계좌 하나의 전략 실행"""
    # 한투 API 클라이언트는 무거우므로 실제 실행 시점에만 import
    from investments.services.kis_overseas_stock import KisOverseasStockClient

    account = Account.objects.get(id=account_id)

    strategy = get_strategy(account.strategy)
    if strategy is None:
        # md 파일이 삭제됐거나 enabled: false 로 바뀐 경우
        msg = f"계좌 {account.name}: 전략 '{account.strategy}'을(를) 찾을 수 없거나 비활성화됨 → 건너뜀"
        logger.warning(msg)
        return msg

    client = KisOverseasStockClient(account)  # 생성 시 토큰 발급/재사용
    logger.info("계좌 %s: 전략 '%s' 실행 시작", account.name, strategy.name)
    return strategy.run(account, client)

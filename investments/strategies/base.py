import logging


class BaseStrategy:
    """
    모든 매매 전략의 부모 클래스
    각 전략 파일(<key>.py)에서 이 클래스를 상속한 Strategy 클래스를 만들고 run()을 구현
    """

    def __init__(self, info):
        self.info = info  # StrategyInfo (md 파일 내용)
        self.logger = logging.getLogger(f"investments.strategies.{info.key}")

    @property
    def key(self):
        return self.info.key

    @property
    def name(self):
        return self.info.name

    def run(self, account, client):
        """
        배치에서 계좌마다 호출됨
            account : investments.models.Account
            client  : KisOverseasStockClient (토큰 발급 완료 상태)
        반환값(문자열)은 django-q 작업 결과로 DB에 저장됨
        """
        raise NotImplementedError(f"{self.__class__.__name__}.run()을 구현해야 합니다.")

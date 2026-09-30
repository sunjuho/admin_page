from investments.strategies.base import BaseStrategy


class Strategy(BaseStrategy):
    # 주문 없이 잔고만 조회하는 예시 전략 (balance_check.md 참고)
    def run(self, account, client):
        holdings, summary = client.inquire_balance()

        result = f"[{self.name}] {account.name}: 보유 종목 {len(holdings)}개"
        self.logger.info(result)

        lines = [result]
        for _, row in holdings.iterrows():
            # KIS 해외주식 잔고 output1: ovrs_pdno(티커), ovrs_item_name(종목명), ovrs_cblc_qty(보유수량)
            line = f"  {row.get('ovrs_pdno')} | {row.get('ovrs_item_name')} | {row.get('ovrs_cblc_qty')}주"
            self.logger.info(line)
            lines.append(line)

        return "\n".join(lines)

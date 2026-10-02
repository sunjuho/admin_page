# PRD: 시장 사이클 기반 배치 (매매 전략 + 시스템 작업)

- 작성일: 2026-10-01 (수정: 2026-10-01)
- 대상 앱: `investments`
- 상태: 초안
- 1차 구현 범위: 미국 주식. 국내 주식은 구조만 지원하고 구현은 후속 작업(13장)

---

## 1. 배경

지금은 django-q `Schedule` 하나가 매일 KST 고정 시각(기본 22:40)에 `run_all_strategies`를 호출하고, 매매 전략이 지정된 계좌마다 `run_account_strategy`를 한 번씩 실행합니다.

대상 시장이 미국 주식이라 이 구조로는 다음 요구를 충족할 수 없습니다.

1. **하루에 여러 번 실행해야 함.** 장 시작 전, 정규장 마감 후, 애프터장 마감 후에 각각 실행해야 합니다.
2. **한 사이클이 한국 시간으로 밤부터 다음 날 아침까지 이어짐.** KST 날짜로는 하루 작업이 두 날짜에 걸칩니다.
3. **서머타임과 휴장일.** KST 고정 시각은 서머타임이 바뀔 때(2026-11-01 해제) 1시간씩 어긋나고, 미국 휴장일과 조기 폐장을 처리하지 못합니다.
4. **중복 실행 방지가 없음.** 주문이 들어가는 배치에서 같은 작업이 두 번 실행되면 주문이 두 번 나갑니다.
5. **시스템 작업이 매매 전략에 섞여 있음.** 지금은 잔고 조회(`balance_check`)가 매매 전략으로 만들어져 있습니다. 잔고 조회는 매매와 무관한 작업이고, 이런 작업이 앞으로 여러 개 늘어날 수 있으므로 계좌마다 골라서 켤 수 있는 별도 구조가 필요합니다.
6. **국내 주식 확장 가능성.** 추후 국장도 다룰 수 있으므로, 시장별 시간대·캘린더·API 클라이언트를 갈아 끼울 수 있어야 합니다.
7. **실행 결과를 바로 알 수 없음.** 작업이 성공했는지 실패했는지 메신저로 받아볼 수 있어야 합니다.

## 2. 사용자 / 목표 / 비목표

### 사용자

| 사용자 | 인원 | 쓰는 화면 | 하는 일 |
|---|---|---|---|
| 관리자 (나) | 1명 | Django admin + FE 화면 | 배치 운영(실행 기록 확인, 실패 작업 재실행), 매매 전략·시스템 작업 코드 관리, 본인 계좌 관리(가족과 같은 FE 기능) |
| 가족 | 여러 명 | FE 화면만 | 본인 계좌 등록·수정·삭제, 본인 계좌의 매매 전략·시스템 작업 선택, 본인 알림 채널 등록, 본인 계좌의 잔고·배치 결과·주문 조회, 체결 전 주문 정정·취소 |

- 로그인은 `AllowedEmail`에 등록된 가족 이메일만 가능합니다.
- FE 화면은 모든 조회·수정을 `owner=request.user`로 걸러, 다른 가족의 계좌·잔고·배치 결과·주문은 보이지 않습니다.
- 매매 전략과 시스템 작업은 계좌 주인이 FE 화면에서 직접 고릅니다. 관리자가 대신 지정하지 않습니다.
- 알림은 관리자가 아니라 **계좌 주인**에게 갑니다. 그래서 사용자마다 자기 알림 채널을 등록합니다(FR-9).
- **같은 매매 전략을 여러 사람의 계좌에서 동시에 실행할 수 있습니다.** 예를 들어 내 계좌와 가족 계좌가 같은 매매 전략을 선택하면, 배치는 두 계좌에서 각각 실행합니다.

### 목표

- G1. 시장별 현지 시간을 기준으로 한 거래일 사이클과 단계(phase)별 실행
- G2. 서머타임, 휴장일, 조기 폐장 자동 처리
- G3. `(계좌, 시장, 거래일, 단계, 작업)` 단위로 정확히 한 번만 실행
- G4. 시스템 작업을 여러 개 정의하고, 계좌마다 체크한 작업만 실행
- G5. 매매 전략 작업과 시스템 작업을 함께 실행하되, 같은 계좌의 KIS 호출은 겹치지 않음
- G6. 작업마다 성공·실패 결과를 계좌 주인의 메신저로 알림 (메신저 종류는 교체 가능)
- G7. 시장(미장/국장)을 추가할 때 배치 흐름은 그대로 두고 시장 정의만 추가
- G8. 단계별 실행 결과를 DB에서 조회 가능
- G9. `balance_check`를 매매 전략에서 빼고 시스템 작업 `balance_snapshot`으로 옮김
- G10. 같은 매매 전략을 소유자가 다른 여러 계좌에서 서로 영향 없이 실행
- G11. 매매 전략이 낸 주문을 기록하고, 체결되기 전에는 사용자가 FE 화면에서 정정·취소

### 비목표

- 국내 주식 시장 정의와 국내 주식 API 클라이언트 구현 (구조만 열어 두고 13장 후속 작업으로 진행)
- 장중 실시간(웹소켓) 매매
- 매매 전략 백테스트
- 잔고 추이 등 조회 화면 (이번 범위는 데이터 저장까지. 화면은 Django admin이 아니라 FE 화면에서 후속 작업으로 진행, 13장)
- 특정 메신저 연동 구현 (메신저가 정해지면 백엔드 하나만 추가)

## 3. 용어

| 용어 | 정의 |
|---|---|
| 시장 (`market`) | `US`(미장), `KR`(국장). 시간대, 휴장 캘린더, 단계 시각, KIS API 클라이언트를 가짐 |
| 거래일 (`trade_date`) | 시장 현지 날짜. 미장은 America/New_York 날짜이며, KST로 밤부터 다음 날 아침까지 이어지는 한 사이클이 하나의 거래일에 속함 |
| 단계 (`phase`) | 한 거래일 안에서 배치가 실행되는 시점. 이름은 시장 공통, 시각은 시장마다 다름 |
| 작업 (`job`) | 단계에서 계좌마다 실행하는 일. 매매 전략 작업과 시스템 작업 두 종류가 있음 |
| 매매 전략 | 매수·매도 판단과 주문을 하는 로직. `investments/strategies/`에 정의하고 계좌마다 하나를 선택. 어느 시장용인지(`market`)를 가짐 |
| 계좌의 시장 | 계좌가 거래하는 시장(`Account.market`). 계좌 하나는 시장 하나만 다루며, 매매 전략은 이 시장과 같은 것만 고를 수 있음(5장) |
| 매매 전략 작업 | 계좌에 선택된 매매 전략이 해당 단계를 사용할 때 실행. 작업 키는 `strategy:<key>` |
| 시스템 작업 | 매매 전략과 무관한 작업(잔고 스냅샷 등). 시장 공통으로 정의하고 계좌의 시장에 맞춰 동작. 계좌마다 체크한 것만 실행. 작업 키는 `system:<key>` |
| tick | 1분마다 실행되어 지금 처리할 단계가 있는지 판단하는 스케줄 함수 |
| 미체결 주문 | KIS에 접수됐지만 아직 전량 체결되지 않은 주문. 남은 수량에 대해서만 정정·취소할 수 있음 |

## 4. 시장과 단계 정의

### 4.1 단계 이름 (시장 공통)

| 단계 | 값 | 의미 |
|---|---|---|
| 장 시작 전 | `pre_open` | 정규장 개장 전 |
| 정규장 마감 후 | `regular_close` | 정규장 마감 직후 |
| 시간외 마감 후 | `after_close` | 시간외 거래(미장 애프터마켓, 국장 시간외 단일가)까지 끝난 뒤 |

### 4.2 미장 (`US`, 1차 구현)

| 단계 | 실행 시각 (ET) | KST (서머타임 중) | KST (서머타임 해제 후) |
|---|---|---|---|
| `pre_open` | 개장 30분 전 (보통 09:00) | 22:00 | 23:00 |
| `regular_close` | 정규장 마감 + 5분 (보통 16:05) | 05:05 | 06:05 |
| `after_close` | 애프터장 마감 + 5분 (보통 20:05) | 09:05 | 10:05 |

- 시간대: `America/New_York`, 캘린더: `exchange_calendars` XNYS
- 조기 폐장일에는 정규장 마감을 13:00 ET, 애프터장 마감을 17:00 ET로 계산합니다.
- 한 거래일의 모든 단계는 같은 ET 날짜 안에서 실행되므로, 날짜가 넘어가는 경우를 따로 처리할 필요가 없습니다.

### 4.3 국장 (`KR`, 구조만 정의)

| 단계 | 실행 시각 (KST, 예시) |
|---|---|
| `pre_open` | 08:30 (개장 30분 전) |
| `regular_close` | 15:35 (정규장 마감 + 5분) |
| `after_close` | 18:05 (시간외 단일가 마감 + 5분) |

- 시간대: `Asia/Seoul`, 캘린더: `exchange_calendars` XKRX
- 수능일처럼 개장·마감 시각이 늦춰지는 날은 캘린더 값을 따릅니다.
- 위 시각은 예시입니다. 정확한 시각과 대체거래소(NXT) 반영 여부는 국장 구현 때 확정합니다(13장).

### 4.4 시장 정의 구조

시장 하나는 다음 정보를 갖는 객체로 정의합니다. 국장을 추가할 때는 이 정의 하나와 국내 주식 클라이언트만 추가하면 됩니다.

```python
@dataclass(frozen=True)
class MarketSpec:
    code: str                 # "US", "KR"
    name: str                 # "미국 주식", "국내 주식"
    tz: ZoneInfo
    calendar: str             # "XNYS", "XKRX"
    currency: str             # "USD", "KRW"
    client_path: str          # "investments.services.kis.kis_overseas_stock.KisOverseasStockClient"

    def is_trading_day(self, date) -> bool: ...
    def phase_times(self, date) -> dict[Phase, datetime]: ...
```

- `MARKETS = {"US": US_SPEC}` 처럼 등록하고, 국장 구현 전까지는 `US`만 등록합니다.

## 5. 시장 정보를 어디에 둘 것인가

### 결정: **계좌에 시장(`Account.market`)을 두고**, 매매 전략은 계좌와 같은 시장만 고를 수 있으며, 시스템 작업은 계좌의 시장을 따라간다

- **`Account.market`:** 계좌가 거래하는 시장입니다. 계좌 하나는 시장 하나만 다룹니다. 배치 대상 계좌 조회와 KIS 클라이언트 선택(미장용·국장용)은 이 값으로 합니다.
- **매매 전략의 `market`:** md front matter에 `market: US`를 필수로 둡니다. 매매 전략 로직은 시장마다 다르기 때문입니다.
  - FE 계좌 화면은 계좌의 시장과 같은 매매 전략만 선택지에 보여줍니다.
  - 저장할 때(`Account.clean()`)도 매매 전략의 시장이 계좌의 시장과 다르면 막습니다.
- **시스템 작업은 시장 공통**으로 정의합니다. 예를 들어 잔고 스냅샷은 `balance_snapshot` 하나만 두고, 작업 안에서 계좌의 시장에 맞는 API로 동작합니다.
  - 작업마다 지원하는 시장 목록(`markets = ("US",)`)을 둡니다. 아직 국장 구현이 없는 작업은 국장 계좌에서 체크할 수 없습니다.
  - 사용자는 시장과 상관없이 "잔고 스냅샷"을 한 번만 체크하면 됩니다.
- **계좌의 시장을 바꾸면:**
  - 선택된 매매 전략은 비웁니다. 새 시장의 매매 전략을 다시 골라야 합니다.
  - 체크된 시스템 작업 중 새 시장을 지원하지 않는 것은 `enabled=False`로 끕니다. 지원하는 작업은 그대로 둡니다.
  - FE 화면은 저장 전에 "매매 전략 선택이 해제됩니다"를 안내합니다.
- **매매 전략 md의 `market`이 나중에 바뀌어** 계좌의 시장과 어긋나면, 배치는 그 매매 전략 작업을 실행하지 않고 `skipped`로 남긴 뒤 계좌 주인에게 알림을 보냅니다(FR-3).
- 계좌당 매매 전략은 지금처럼 **하나**입니다.
- 반대로 매매 전략 하나는 **여러 계좌가 함께 선택**할 수 있습니다. 소유자가 달라도 됩니다. 매매 전략은 코드에 한 번 정의하고 계좌는 키(`Account.strategy`)로만 참조하므로, 계좌–매매 전략은 N:1입니다.

이렇게 정한 이유와 제약은 다음과 같습니다.

- 계좌에 시장이 있으면 배치가 `Account.objects.filter(market=...)`로 대상을 바로 찾을 수 있고, 매매 전략 없이 시스템 작업만 쓰는 계좌도 시장이 분명합니다.
- 계좌와 매매 전략 양쪽에 시장이 있으므로 둘이 어긋나지 않게 저장할 때와 실행할 때 모두 확인합니다.
- KIS 종합계좌 하나로 국장과 미장을 모두 하려면 같은 계좌를 두 번 등록해야 하는데, `account_number`가 unique라 지금 구조로는 불가능합니다. 시장마다 다른 계좌를 쓰는 것을 전제로 합니다.

## 6. 기능 요구사항

### FR-1. 시장 캘린더 (`investments/markets/`)

- `Phase`는 `TextChoices`로 정의합니다.
- `MarketSpec`(4.4)과 `MARKETS` 레지스트리, `get_market(code)`, `get_market_choices()`를 제공합니다.
- `spec.now()`, `spec.today()`: 해당 시장의 현재 시각과 날짜
- `spec.is_trading_day(date)`, `spec.session(date)`(개장, 정규장 마감, 시간외 마감 시각, 조기 폐장 반영), `spec.phase_times(date)`
- 휴장일과 조기 폐장 정보는 `exchange_calendars`를 사용합니다.
- 단계 시각 오프셋(개장 전 30분, 마감 후 5분)은 설정값으로 둡니다.

### FR-2. tick 스케줄

- django-q `Schedule` 하나를 `Schedule.MINUTES`, `minutes=1`로 등록하고 `investments.services.tasks.tick`을 실행합니다.
- tick은 등록된 **시장마다** 다음 순서로 동작합니다.
  1. `trade_date = spec.today()`를 구하고, 거래일이 아니면 그 시장은 건너뜁니다. 휴장일에는 매매 전략 작업과 시스템 작업 모두 실행하지 않습니다.
  2. 각 단계에 대해 `실행 시각 <= now < 실행 시각 + GRACE`이면 `enqueue_phase(market, trade_date, phase)`를 호출합니다.
- `GRACE` 기본값은 30분입니다. 워커가 잠시 멈췄다가 이 시간 안에 다시 켜지면 밀린 단계를 실행하고, 이 시간이 지나면 건너뜁니다. 지난 시점에 뒤늦게 주문이 나가는 것을 막기 위해서입니다.
- `setup_strategy_schedule` 명령은 기존 "매매 전략 배치" 일일 스케줄을 삭제하고 tick 스케줄을 등록하도록 변경합니다. `--time` 옵션은 제거합니다.

### FR-3. 작업 등록 (`enqueue_phase`)

- 대상 계좌는 `Account.market == market`인 계좌 중, 매매 전략이 선택되었거나 체크된 시스템 작업이 하나 이상 있는 계좌입니다. 둘 다 없으면 아무것도 실행하지 않습니다.

계좌마다 실행할 작업 목록을 다음 두 가지로 만듭니다.

- **매매 전략 작업:** 계좌에 매매 전략이 선택되어 있고, 그 매매 전략이 활성화되어 있으며, `phase in strategy.phases`일 때 `strategy:<key>`를 추가합니다.
  - 이때 `strategy.market != account.market`이면(매매 전략 md의 시장이 나중에 바뀐 경우) 실행하지 않습니다. `BatchRun`을 `skipped`로 만들고 결과에 "매매 전략 시장(KR)이 계좌 시장(US)과 다름"처럼 사유를 남긴 뒤, 계좌 주인에게 알림을 보냅니다(FR-9).
- **시스템 작업:** 계좌에 체크된(`AccountSystemJob.enabled=True`) 시스템 작업 중, 작업 정의가 존재하고 `account.market in job.markets`이며 `phase in job.phases`인 것마다 `system:<key>`를 추가합니다. 계좌 시장을 지원하지 않는 작업은 경고 로그를 남기고 건너뜁니다.

그다음 처리는 다음과 같습니다.

- 작업마다 `BatchRun`을 `get_or_create`로 만듭니다.
- 새로 만든 행이 하나라도 있으면 `run_account_phase(account_id, market, trade_date, phase)`를 `async_task`로 **계좌당 하나만** 큐에 넣습니다.
- 매매 전략이나 시스템 작업 정의가 없어졌거나 비활성화된 경우에는 경고 로그만 남기고 나머지 작업은 그대로 실행합니다.
- 같은 매매 전략을 선택한 계좌가 여러 개면 계좌마다 `BatchRun`이 따로 만들어지고 따로 실행됩니다. 한 계좌의 실패나 state가 다른 계좌에 영향을 주지 않습니다.

### FR-4. 계좌별 실행 (`run_account_phase`)

- 계좌의 시장(`Account.market`)에 해당하는 `MarketSpec.client_path`로 KIS 클라이언트를 한 번만 생성하고 모든 작업이 공유합니다. 미장 계좌면 해외주식 클라이언트, 국장 계좌면 국내주식 클라이언트를 씁니다. 매매 전략의 시장은 계좌의 시장과 같으므로(5장) 매매 전략 기준으로 봐도 같은 클라이언트입니다. 토큰 발급도 한 번만 일어납니다.
- 단계를 실행하기 전에 그 계좌의 미체결 주문 상태를 KIS와 먼저 동기화합니다(FR-10). 매매 전략이 사용자가 정정·취소한 결과를 보고 판단하게 하기 위해서입니다.
- 해당 `(account, market, trade_date, phase)`의 `pending` 작업을 순서대로 하나씩 실행합니다. 순서는 시스템 작업의 `order` 값을 먼저, 그다음 매매 전략 작업입니다.
- 실행 전에 `filter(id=..., status="pending").update(status="running")`를 호출하고, 반환값이 1일 때만 실행합니다.
- 작업 하나가 예외를 내면 그 작업만 `failed`로 기록하고 다음 작업을 계속 실행합니다.
- 시작·종료 시각, 결과 문자열, 예외 내용을 `BatchRun`에 저장합니다.
- 클라이언트 생성(토큰 발급)이 실패하면 해당 단계의 `pending` 작업을 모두 `failed`로 기록합니다.
- 작업 하나가 끝날 때마다(성공·실패 모두) FR-9의 알림을 보냅니다.

### FR-5. 작업 공통 인터페이스

매매 전략과 시스템 작업은 같은 실행 인터페이스를 씁니다.

```python
class BaseJob:
    phases = ()     # 이 작업이 실행될 단계

    def run(self, ctx):
        return getattr(self, f"on_{ctx.phase}")(ctx)

    def on_pre_open(self, ctx): ...
    def on_regular_close(self, ctx): ...
    def on_after_close(self, ctx): ...
```

- 매매 전략은 `market`(시장 하나), 시스템 작업은 `markets`(지원하는 시장 목록)를 가집니다(FR-6, FR-7).
- 반환값은 짧은 결과 요약 문자열이며, `BatchRun.result`와 알림 본문에 그대로 쓰입니다.
- `JobContext`는 `account`, `client`, `market`, `trade_date`, `phase`, `run`(현재 `BatchRun`)을 갖고, 다음을 제공합니다.
  - `ctx.state`: 현재 단계의 `BatchRun.state` (dict, 작업이 끝나면 저장)
  - `ctx.prev_state(phase)`: 같은 계좌·시장·거래일·작업의 다른 단계에서 저장한 state
  - `ctx.place_order(...)`, `ctx.modify_order(order, ...)`, `ctx.cancel_order(order)`: KIS 주문 API를 호출하고 결과를 `Order`에 기록 (FR-10)
  - `ctx.orders(...)`: 이 계좌의 `Order` 조회 (예: `pre_open`에 낸 주문의 체결 여부를 `regular_close`에서 확인)
- 매매 전략은 주문할 때 `client.order()`를 직접 부르지 않고 반드시 `ctx.place_order()`를 씁니다. 그래야 주문이 `Order`에 남아 FE 화면에서 정정·취소할 수 있습니다.
- 주문의 체결 여부는 `ctx.state`에 저장한 주문번호가 아니라 `Order`로 확인합니다. 사용자가 FE에서 정정하면 KIS 주문번호가 바뀌기 때문입니다.

### FR-6. 매매 전략 (`investments/strategies/`)

- `BaseStrategy(BaseJob)`로 바꾸고, md front matter에 `market`을 필수로 추가합니다. `market`이 없거나 등록되지 않은 시장이면 로드할 때 경고하고 제외합니다.

```
---
name: 매매 전략 이름
description: 한 줄 설명
market: US
enabled: false
---
```

- `phases`는 `<key>.py`의 `Strategy` 클래스 속성으로 정의합니다.
- 매매 전략 객체는 여러 계좌가 공유하므로 계좌별 데이터를 인스턴스 속성에 저장하지 않습니다. 계좌별로 남겨야 하는 값은 `ctx.state`(`BatchRun.state`)에 저장합니다.
- 시그니처가 `run(account, client)`에서 `run(ctx)`로 바뀌므로 `_template.md` 안내 문구도 함께 수정합니다.
- `balance_check`는 매매 전략이 아니므로 `strategies/`에서 삭제하고 시스템 작업 `balance_snapshot`(FR-8)으로 옮깁니다. 디버그 스크립트 `strategies/debug/debug_balance_check.py`도 시스템 작업 기준으로 옮깁니다.
- `balance_check`가 선택되어 있던 계좌는 데이터 마이그레이션에서 `strategy`를 비우고, 대신 `balance_snapshot`을 체크합니다.

### FR-7. 시스템 작업 (`investments/system_jobs/`)

- 매매 전략과 같은 플러그인 방식입니다. 작업 하나는 `<key>.py` 한 파일이며, `BaseSystemJob(BaseJob)`을 상속한 `Job` 클래스를 정의합니다.

```python
class Job(BaseSystemJob):
    name = "잔고 스냅샷"
    description = "시간외 거래까지 끝난 뒤 계좌 잔고를 저장"
    markets = ("US",)     # 지원하는 시장. 국장 구현 후 ("US", "KR")
    phases = (Phase.AFTER_CLOSE,)
    order = 10            # 같은 단계 안에서 실행 순서 (작을수록 먼저)
    enabled = True

    def on_after_close(self, ctx):
        if ctx.market == "US":
            return self._snapshot_us(ctx)
        ...
```

- 시스템 작업은 시장 공통으로 정의하고, 시장마다 다른 부분은 작업 안에서 `ctx.market`으로 나눕니다(5장).
- `markets`에 없는 시장의 계좌에서는 체크할 수 없고, 배치에서도 실행하지 않습니다.

- `load_system_jobs()`가 폴더를 스캔해 `{key: 작업 정의}`를 반환합니다(`_`로 시작하는 파일 제외, 프로세스당 한 번 캐시).
- 시스템 작업 정의는 코드에만 있고 DB 테이블은 두지 않습니다. 매매 전략과 마찬가지로 **작업을 추가해도 마이그레이션이 필요 없습니다.**
- 1차 구현 시스템 작업: `balance_snapshot` (FR-8, 미장만 지원)

### FR-8. 잔고 스냅샷 (`balance_snapshot`)

- 기존 `balance_check` 매매 전략을 옮긴 시스템 작업입니다.
- 1차 구현은 미장만 지원합니다(`markets = ("US",)`). 국장은 13장 후속 작업에서 추가합니다.
- 실행 단계: `after_close` (그날 체결이 모두 반영된 뒤)
- 거래일에만 실행합니다. 휴장일에는 스냅샷을 저장하지 않습니다.
- `client.inquire_balance()` 결과를 `BalanceSnapshot`에 저장합니다.
- `(account, market, trade_date)`가 이미 있으면 덮어씁니다.
- 결과 요약 예: `보유 5종목, 평가금액 $12,345.67, 손익 +3.2%`

### FR-9. 메신저 알림

- 작업(`BatchRun`) 하나가 끝날 때마다 **성공·실패 모두** 알림을 보냅니다. 건너뛴(`skipped`) 작업도 사유와 함께 보냅니다.
- 알림 본문:

```
[미장 · 애프터장 마감 후 · 2026-10-01]
✅ 성공 | 메인 투자계좌 | 잔고 스냅샷
보유 5종목, 평가금액 $12,345.67, 손익 +3.2%
소요 3.2초
```

  실패하면 `❌ 실패`와 예외 메시지 첫 줄을 넣습니다.
- 메신저는 아직 정하지 않았으므로 백엔드를 교체할 수 있게 만듭니다.

```python
class BaseNotifier:
    code = ""   # "log", "telegram" 등. NotificationChannel.backend 값과 연결

    def send(self, target: str, message: Notification) -> None: ...
```

  - 설정 `NOTIFIER_BACKENDS`에 사용할 백엔드 경로 목록을 둡니다.
  - 기본값은 로그로만 남기는 `LogNotifier`입니다. 메신저가 정해지면 `TelegramNotifier`, `SlackNotifier` 같은 백엔드 하나만 추가합니다.
  - 봇 토큰처럼 백엔드 전체에 공통인 값은 환경변수로 두고, 사용자마다 다른 값(채팅 ID, 웹훅 URL 등)은 `NotificationChannel.target`에 둡니다.

**받는 사람: 계좌 주인**

- 알림은 관리자가 아니라 **작업이 실행된 계좌의 주인(`Account.owner`)**에게 보냅니다. 관리자 본인 계좌의 알림은 관리자에게 갑니다.
- 사용자는 FE 화면에서 자기 알림 채널(`NotificationChannel`)을 등록합니다. 채널을 여러 개 등록하면 켜져 있는 채널 모두로 보냅니다.
- 등록할 때 테스트 메시지를 보내 받는 것을 확인한 채널만 사용합니다(`verified_at`). 잘못 입력한 채널 ID로 다른 사람에게 계좌 정보가 가는 것을 막기 위해서입니다.
- 계좌 주인에게 사용 가능한 채널이 없으면 알림은 로그로만 남기고 `BatchRun.notified_at`을 비워 둡니다. FE 화면 상단에 "알림 채널이 등록되지 않았습니다"를 안내합니다.
- FE에서 정정·취소한 주문 결과도 같은 방식으로 계좌 주인에게 보냅니다(FR-10).

- 알림 발송 실패는 작업 상태를 바꾸지 않습니다. 실패 사유를 로그로 남기고 `BatchRun.notified_at`을 비워 둡니다.
- 알림 수신 여부를 계좌별·작업별로 끄는 기능은 이번 범위에 넣지 않고, 모든 작업에 대해 보냅니다.

### FR-10. 주문 기록과 FE 주문 정정·취소

매매 전략이 낸 주문은 모두 `Order`에 기록하고, 체결되기 전에는 계좌 주인이 FE 화면에서 정정·취소할 수 있습니다.

**주문 기록**

- `ctx.place_order()`가 KIS 주문 API(미장: `order`)를 호출하고, 응답의 주문번호(`odno`)와 함께 `Order`를 만듭니다. 주문이 거부되거나 API가 실패해도 `rejected`/`failed` 상태로 남깁니다.
- 주문마다 어느 매매 전략·단계(`BatchRun`)에서 나왔는지 연결합니다.

**상태 동기화**

- KIS의 미체결·체결 조회(미장: `inquire_nccs`, `inquire_ccnl`)로 `Order`의 체결 수량과 상태를 갱신합니다.
- 동기화 시점은 다음 세 가지입니다.
  - 배치 단계를 실행하기 직전 (FR-4)
  - FE 주문 화면을 열 때와 새로고침 버튼을 누를 때
  - 정정·취소를 요청하기 직전 (이미 체결됐는지 다시 확인)

**FE 정정·취소**

- FE 주문 화면에서 본인 계좌의 미체결 주문(`submitted`, `partially_filled`)만 정정·취소 버튼을 보여줍니다.
- **정정:** 남은(미체결) 수량에 대해 가격과 수량을 바꿉니다. 미장은 `order_rvsecncl`(정정)로 요청합니다. KIS는 정정하면 새 주문번호를 주므로, 새 `Order`를 만들고 `parent`로 원래 주문을 연결합니다. 원래 주문은 `modified` 상태로 바꿉니다.
- **취소:** 남은 수량 전체를 취소합니다. 미장은 `order_rvsecncl`(취소)로 요청하고, 성공하면 `cancelled`로 바꿉니다.
- 요청 직전에 상태를 동기화해서 그사이 전량 체결됐으면 요청하지 않고 "이미 체결됨"을 안내합니다. 일부만 체결됐으면 남은 수량만 정정·취소합니다.
- 사용자가 정정·취소한 주문은 `modified_by`에 사용자를 기록하고, 매매 전략 작업과 같은 방식으로 메신저 알림을 보냅니다(FR-9).
- 장이 열려 있지 않아 KIS가 정정·취소를 거부하면, KIS 오류 메시지를 화면에 그대로 보여주고 주문 상태는 바꾸지 않습니다.

**배치와 겹칠 때**

- 같은 계좌에서 배치 단계가 실행 중이면 FE 정정·취소를 막고 "배치 실행 중"을 안내합니다. 반대로 FE 요청이 처리 중이면 배치는 그 요청이 끝날 때까지 기다립니다. 계좌 단위 잠금으로 처리합니다(8장).

## 7. 데이터 모델

### `Account` (변경)

| 필드 | 타입 | 설명 |
|---|---|---|
| market | CharField(5, choices=get_market_choices, default="US") | 계좌가 거래하는 시장. 기존 계좌는 마이그레이션에서 `US`로 채움 |

- `strategy` 필드는 그대로 두고, 선택지는 계좌의 시장과 같은 매매 전략만 보여줍니다.
- `clean()`에서 선택한 매매 전략의 `market`이 계좌의 `market`과 다르면 `ValidationError`를 냅니다.
- 계좌의 `market`을 바꿔 저장하면 `strategy`를 비우고, 새 시장을 지원하지 않는 `AccountSystemJob`은 `enabled=False`로 바꿉니다(5장). 이 처리는 폼이 아니라 모델 저장 로직(서비스 함수)에 두어 admin에서 바꿔도 똑같이 동작하게 합니다.

### `AccountSystemJob` (신규, 계좌 1:N)

계좌마다 어떤 시스템 작업을 켤지 저장합니다. 시스템 작업 정의가 코드에 있으므로, DB 입장에서는 계좌 1:N 테이블이고 작업은 키 문자열로 참조합니다.

| 필드 | 타입 | 설명 |
|---|---|---|
| account | FK(Account, CASCADE, related_name="system_jobs") | |
| job_key | CharField(50, choices=get_system_job_choices) | `investments/system_jobs/<key>.py`의 key |
| enabled | BooleanField(default=True) | 체크 여부 |
| created_at / updated_at | DateTimeField | |

- 유니크 제약: `(account, job_key)`
- `clean()`에서 계좌의 `market`이 시스템 작업의 `markets`에 없으면 `ValidationError`를 냅니다.
- 체크를 해제하면 행을 지우지 않고 `enabled=False`로 바꿉니다. 나중에 작업별 설정값(예: 알림 끄기, 파라미터)을 붙일 자리가 됩니다.
- `Account`에 JSON 필드로 체크 목록을 두는 방식은 쓰지 않습니다. "이 작업이 켜진 계좌"를 조회하기 어렵고 유니크 보장이 안 되기 때문입니다.

### `BatchRun`

| 필드 | 타입 | 설명 |
|---|---|---|
| account | FK(Account, CASCADE) | |
| market | CharField(5) | `US`, `KR`. 실행 시점의 계좌 시장 |
| trade_date | DateField | 시장 현지 날짜 |
| phase | CharField(choices=Phase) | |
| job | CharField(60) | `system:balance_snapshot`, `strategy:<key>` |
| job_name | CharField(100) | 실행 시점의 작업 표시 이름 (알림, 화면용) |
| status | CharField | `pending` / `running` / `done` / `failed` / `skipped` |
| state | JSONField(default=dict) | 단계 사이에 넘길 데이터 |
| result | TextField(blank) | 결과 요약 또는 예외 내용 |
| created_at / started_at / finished_at | DateTimeField | |
| notified_at | DateTimeField(null) | 알림 발송 완료 시각 |

- 유니크 제약: `(account, market, trade_date, phase, job)`
- 인덱스: `(market, trade_date, phase)`
- 계좌의 시장이 나중에 바뀌어도 과거 기록이 어느 시장 기준이었는지 남도록 `market`을 따로 저장합니다.

### `Order` (신규)

매매 전략이 낸 주문과 FE에서 정정한 주문을 기록합니다(FR-10).

| 필드 | 타입 | 설명 |
|---|---|---|
| account | FK(Account, CASCADE, related_name="orders") | |
| market | CharField(5) | `US`, `KR` |
| batch_run | FK(BatchRun, SET_NULL, null) | 주문을 낸 매매 전략 작업. FE 정정으로 생긴 주문은 원래 주문의 값을 이어받음 |
| strategy_key | CharField(50, blank) | 주문을 낸 매매 전략 |
| parent | FK("self", SET_NULL, null) | 정정으로 생긴 주문이면 원래 주문 |
| odno | CharField(20, blank) | KIS 주문번호 (접수 실패 시 비어 있음) |
| order_date | DateField | KIS 주문일자 (정정·취소 요청과 체결 조회에 필요) |
| exchange_code | CharField(10) | 미장: `NASD`, `NYSE`, `AMEX` |
| symbol | CharField(20) | 종목코드 (예: `AAPL`) |
| side | CharField(4) | `buy` / `sell` |
| order_type | CharField(5) | KIS 주문구분 (예: `00` 지정가) |
| quantity | Decimal | 주문 수량 |
| price | Decimal | 주문 단가 |
| filled_quantity | Decimal(default=0) | 체결 수량 |
| status | CharField | `submitted` / `partially_filled` / `filled` / `modified` / `cancelled` / `rejected` / `failed` |
| modified_by | FK(User, SET_NULL, null) | FE에서 정정·취소한 사용자 |
| raw_response | JSONField(default=dict) | KIS 응답 원본 |
| created_at / updated_at | DateTimeField | |

- 인덱스: `(account, status)`, `(account, order_date)`
- 정정·취소할 수 있는 상태는 `submitted`, `partially_filled`입니다.

### `NotificationChannel` (신규, 사용자 1:N)

사용자마다 알림을 받을 채널을 저장합니다(FR-9).

| 필드 | 타입 | 설명 |
|---|---|---|
| user | FK(User, CASCADE, related_name="notification_channels") | 채널 주인 |
| backend | CharField(20) | 메신저 종류 (`BaseNotifier.code`, 예: `telegram`) |
| target | CharField(200) | 받는 곳 (채팅 ID, 웹훅 URL 등) |
| enabled | BooleanField(default=True) | 사용 여부 |
| verified_at | DateTimeField(null) | 테스트 메시지 수신 확인 시각. 비어 있으면 발송하지 않음 |
| created_at / updated_at | DateTimeField | |

- 유니크 제약: `(user, backend, target)`
- FE 화면에서 본인 채널만 등록·수정·삭제할 수 있습니다.

### `BalanceSnapshot`

| 필드 | 타입 | 설명 |
|---|---|---|
| account | FK(Account, CASCADE) | |
| market | CharField(5) | |
| trade_date | DateField | |
| currency | CharField(3) | `USD`, `KRW` |
| total_eval_amount | Decimal | 총 평가금액 |
| total_profit | Decimal | 총 평가손익 |
| profit_rate | Decimal | 수익률 |
| holdings | JSONField | 종목별 티커, 종목명, 수량, 평단가, 평가금액 |
| raw_summary | JSONField | KIS 응답 원본 (필드 매핑을 바꿀 때 대비) |
| created_at | DateTimeField | |

- 유니크 제약: `(account, market, trade_date)`
- 어떤 KIS 응답 필드를 어느 컬럼에 매핑할지는 구현 단계에서 `inquire_balance` 실제 응답을 보고 확정합니다.
- 이 테이블은 FE 화면의 잔고 추이 기능(13장)이 읽는 데이터입니다.

## 8. 비기능 요구사항

- **멱등성:** 같은 `(account, market, trade_date, phase, job)`은 tick이 여러 번 돌거나 워커가 재시도해도 한 번만 실행됩니다.
- **django-q 설정:** `Q_CLUSTER`에 `max_attempts: 1`을 두고 `retry > timeout`으로 설정해, 오래 걸리는 작업이 다시 전달되지 않게 합니다.
- **동시성:** 계좌끼리는 병렬로 실행하고, 한 계좌 안에서는 순서대로 실행합니다. 같은 앱키로 토큰을 동시에 발급하거나 호출 한도에 걸리는 것을 막기 위해서입니다. 계좌 하나는 시장 하나만 다루므로, 같은 계좌의 단계가 시장끼리 겹치는 일은 없습니다.
- **계좌 단위 잠금:** 배치 단계 실행, FE 주문 정정·취소, 토큰 갱신은 같은 계좌에 대해 동시에 일어나지 않도록 계좌 단위로 잠급니다(예: `Account` 행 `select_for_update`). FE 요청은 잠금을 얻지 못하면 기다리지 않고 바로 "배치 실행 중"을 안내합니다.
- **로컬 SQLite:** `database is locked`를 피하기 위해 로컬에서는 워커 수를 작게(예: 2) 잡습니다.
- **로깅:** 단계 시작, 계좌별 작업 결과, 건너뛴 이유(휴장일, GRACE 초과, 작업 정의 없음·비활성, 시장 불일치)를 로그로 남깁니다.
- **앱키·시크릿 보관:** KIS 앱키와 시크릿은 지금처럼 평문으로 저장합니다(결정). 대신 FE 화면과 API 응답, 로그, 알림 본문에는 출력하지 않습니다.
- **의존성:** `exchange_calendars`를 추가합니다. `pandas`가 `requirements.txt`에 빠져 있으므로 함께 반영합니다.

## 9. 화면

- **FE 화면**은 관리자와 가족이 모두 쓰고, 본인 계좌의 데이터만 보여줍니다(`owner=request.user`). **Django admin**은 관리자만 씁니다.
- **계좌 등록/수정 화면 (FE)**
  - 시장 선택 (미장/국장. 국장은 국장 구현 전까지 선택지에 나오지 않음)
  - 매매 전략 선택지: 고른 시장과 같은 매매 전략만 표시. 같은 매매 전략을 다른 가족이 이미 쓰고 있어도 선택 가능
  - 시스템 작업 체크박스 목록: 고른 시장을 지원하는 활성 시스템 작업만 표시
  - 시장을 바꾸면 매매 전략 선택이 해제되고, 새 시장을 지원하지 않는 시스템 작업 체크가 풀린다는 안내를 저장 전에 보여줌
- **알림 채널 화면 (FE)**
  - 본인 알림 채널 목록과 등록·수정·삭제
  - 등록 후 "테스트 메시지 보내기"로 수신을 확인해야 사용 가능 상태가 됨
- **주문 화면 (FE)**
  - 본인 계좌의 주문 목록: 계좌, 종목, 매수/매도, 수량·체결 수량, 가격, 상태, 주문 시각, 주문을 낸 매매 전략
  - 미체결 주문에만 정정·취소 버튼 표시. 정정은 가격과 수량 입력, 취소는 확인 창을 거침
  - 화면을 열 때와 새로고침 버튼을 누를 때 KIS와 상태를 동기화
- **Django admin** (운영 확인용)
  - `BatchRun`: 시장·거래일·단계·상태·작업으로 필터, 계좌명으로 검색
  - `BalanceSnapshot`: 읽기 전용
  - `AccountSystemJob`: `Account` admin 안에 인라인으로 표시
  - 실패한 작업을 다시 실행하는 admin action: `failed`를 `pending`으로 바꾸고 `run_account_phase`를 큐에 넣음. 주문 작업을 다시 실행할 위험이 있으므로 확인 화면을 둡니다.
- 잔고 추이 같은 조회 화면은 Django admin이 아니라 FE 화면에서 만듭니다(13장).

## 10. 테스트

KIS 호출과 메신저 발송은 모두 mock으로 처리합니다.

- `markets`
  - 미장: 서머타임 중인 날과 해제된 날의 단계 시각 (KST로 변환했을 때 1시간 차이)
  - 미장 휴장일 (예: 2026-11-26 추수감사절)이면 `is_trading_day`가 False
  - 미장 조기 폐장일 (예: 2026-11-27)의 마감 시각 13:00 / 17:00 ET
- `tick`
  - 단계 시각 전, GRACE 안, GRACE 이후 각각의 등록 여부
  - 휴장일에는 매매 전략 작업과 시스템 작업 모두 등록되지 않음
  - 같은 시각에 두 번 호출해도 `BatchRun`과 `async_task`가 한 번만 생성됨
  - 시장이 여러 개 등록되어 있으면 시장마다 따로 판단 (테스트용 가짜 시장 정의 사용)
- `enqueue_phase`
  - 매매 전략만 있는 계좌, 시스템 작업만 체크한 계좌, 둘 다 있는 계좌, 둘 다 없는 계좌
  - 계좌의 `market`과 다른 시장의 단계에서는 등록되지 않음
  - 계좌 시장을 지원하지 않는(`markets`에 없는) 시스템 작업은 등록되지 않음
  - 매매 전략의 `market`이 계좌의 `market`과 다르면 `skipped`로 기록되고 계좌 주인에게 알림이 발송됨
  - `enabled=False`인 `AccountSystemJob`은 등록하지 않음
  - `phases`에 없는 단계면 등록하지 않음
  - 정의가 사라진 `job_key`는 경고만 남기고 건너뜀
- 여러 계좌의 같은 매매 전략
  - 소유자가 다른 두 계좌가 같은 매매 전략을 선택하면 `BatchRun`이 계좌마다 하나씩 생성됨
  - 한 계좌의 작업이 실패해도 다른 계좌의 같은 매매 전략 작업은 정상 실행됨
  - 한 계좌에서 저장한 state가 다른 계좌의 `ctx.prev_state()`로 읽히지 않음
- FE 화면 권한
  - 다른 사용자의 계좌, `BalanceSnapshot`, `BatchRun`, `Order`, `NotificationChannel`은 조회·수정할 수 없음
- 모델 검증
  - 계좌와 시장이 다른 매매 전략을 선택하면 `ValidationError`
  - 계좌 시장을 지원하지 않는 시스템 작업을 체크하면 `ValidationError`
  - 계좌의 `market`을 바꾸면 `strategy`가 비워지고, 새 시장을 지원하지 않는 시스템 작업만 `enabled=False`가 됨
- 주문 (FR-10)
  - `ctx.place_order()`가 `Order`를 만들고, API 실패·거부도 `failed`/`rejected`로 기록
  - 상태 동기화로 `filled_quantity`와 상태가 갱신됨 (일부 체결 → `partially_filled`, 전량 체결 → `filled`)
  - 정정하면 새 `Order`가 `parent`로 원래 주문에 연결되고 원래 주문은 `modified`
  - 요청 직전 동기화에서 전량 체결로 확인되면 정정·취소 API를 호출하지 않음
  - `filled`, `cancelled` 주문은 정정·취소할 수 없음
  - 다른 사용자의 주문은 정정·취소할 수 없음
  - 같은 계좌의 배치 단계가 실행 중이면 FE 정정·취소가 거절됨
- `run_account_phase`
  - 클라이언트를 한 번만 생성
  - 시스템 작업 `order` 순서 후 매매 전략 순서로 실행
  - 첫 작업이 실패해도 다음 작업이 실행됨
  - 이미 `running`/`done`인 작업은 다시 실행하지 않음
  - `prev_state`로 이전 단계의 state를 읽음
- 알림
  - 알림은 계좌 주인의 확인된(`verified_at`) 채널로만 가고, 다른 사용자나 관리자에게는 가지 않음
  - 계좌 주인에게 사용 가능한 채널이 없으면 발송하지 않고 `notified_at`이 비어 있음
  - 성공·실패·건너뜀 각각 알림이 한 번씩 발송되고 본문에 시장, 단계, 계좌, 작업, 결과가 들어감
  - 알림 발송이 예외를 내도 `BatchRun.status`는 바뀌지 않고 `notified_at`이 비어 있음
- `balance_snapshot`: 같은 거래일에 두 번 실행하면 덮어씀
- 매매 전략 로더: `market`이 없는 md는 제외
- 기존 `StrategyBatchTest`는 새 흐름에 맞게 수정합니다. `balance_check`를 쓰던 테스트는 시스템 작업 기준으로 바꿉니다.

## 11. 기존 구조에서의 전환

1. `markets/`(Phase, MarketSpec, 미장 정의) 추가
2. `Account.market` 추가와 마이그레이션(기존 계좌는 `US`), 시장 검증과 시장 변경 처리. `BaseJob`, `JobContext` 추가. `BaseStrategy`를 `BaseJob` 기반으로 바꾸고 `_template.md`에 `market` 추가
3. `system_jobs/` 레지스트리와 `balance_snapshot` 추가
4. `AccountSystemJob`, `BatchRun`, `Order`, `NotificationChannel`, `BalanceSnapshot` 모델과 마이그레이션
5. 주문 서비스: `ctx.place_order/modify_order/cancel_order`, KIS 상태 동기화, 계좌 단위 잠금
6. `balance_check` 이관: `strategies/balance_check.md`, `balance_check.py` 삭제. 이 매매 전략을 쓰던 계좌는 `strategy`를 비우고 `balance_snapshot`을 체크하는 데이터 마이그레이션. 디버그 스크립트도 시스템 작업 기준으로 이동
7. 알림 모듈(`BaseNotifier`, `LogNotifier`) 추가
8. `tasks.py`: `run_all_strategies`, `run_account_strategy`를 `tick`, `enqueue_phase`, `run_account_phase`로 교체
9. `setup_strategy_schedule`: 기존 일일 스케줄 삭제, tick 스케줄 등록
10. FE 화면: 계좌 화면(시장 선택, 시장에 맞는 매매 전략·시스템 작업만 표시), 알림 채널 등록, 주문 목록과 정정·취소. admin 등록, 테스트
11. `CLAUDE.md`의 명령어와 배치 흐름 설명 갱신

## 12. 미정 사항

- [ ] **장 시작 전 주문 방식:** `pre_open`에서 KIS 일반 주문으로 넣을 수 있는지, 예약주문 API를 따로 써야 하는지 확인 필요
- [ ] **GRACE 값:** 30분이 적절한지. 단계마다 다르게 둘지
- [ ] **메신저 종류:** 텔레그램, 슬랙, 디스코드, 카카오톡 등. 정해지면 백엔드 하나와 FE 채널 등록 안내(채팅 ID 확인 방법 등)만 추가. 가족이 각자 쓰기 쉬운 메신저인지도 고려
- [ ] **알림 묶음 발송:** 계좌·작업이 늘어 알림이 많아지면 단계별로 묶어 한 번에 보낼지
- [ ] **FE에 보여줄 주문 범위:** 이 시스템이 낸 주문(`Order`)만 보여줄지, HTS·MTS로 직접 낸 주문까지 KIS 미체결 조회로 가져와 보여주고 정정·취소하게 할지
- [ ] **정정·취소 가능 시간:** 미장 정규장·프리·애프터마켓 중 언제 KIS가 정정·취소를 받는지, 장 시작 전 주문이 예약주문이면 취소 API(`order_resv_ccnl`)가 따로 필요한지 확인 필요 (장 시작 전 주문 방식과 함께 결정)
- [ ] **사용자가 손댄 주문과 매매 전략:** 사용자가 정정·취소한 주문을 매매 전략이 다음 단계에서 다시 정정·재주문해도 되는지, 손대지 않아야 하는지

## 13. 후속 작업 (TODO)

### 국장 지원

- [ ] 국내 주식 KIS 클라이언트 추가: `services/kis/kis_original/domestic_stock_*`를 참고해 계좌 단위 클래스(`kis_domestic_stock.py`)로 변환. 해외 클라이언트처럼 계좌번호는 `self.account`에서 꺼내 쓰고, 다음 페이지 호출은 키워드 인자로 작성
- [ ] 국장 `MarketSpec` 정의와 `MARKETS` 등록: 단계 시각 확정, 대체거래소(NXT) 프리·애프터마켓 반영 여부 결정
- [ ] XKRX 캘린더로 휴장일과 개장·마감 시각 변경일(수능일 등) 처리 확인
- [ ] 기존 시스템 작업에 국장 지원 추가: `balance_snapshot`에 국내주식 잔고 조회를 넣고 `markets`에 `KR` 추가 (원화 기준 `BalanceSnapshot` 저장)
- [ ] 계좌 화면의 시장 선택지에 국장 노출
- [ ] 국장 매매 전략 추가 (front matter `market: KR`)
- [ ] 국장 주문 기록·정정·취소: 국내주식 주문, 정정취소, 미체결 조회 API로 FR-10 동작 연결
- [ ] 국장 단계 시각·휴장일 테스트 추가

### FE 화면

- [ ] 잔고 추이 화면: `BalanceSnapshot`을 읽어 계좌별 평가금액·손익 추이를 보여줌 (Django admin이 아니라 FE 화면, 본인 계좌만)
- [ ] 배치 실행 현황 화면: 거래일·단계별 `BatchRun` 결과 조회 (본인 계좌만)
- [ ] 매매 전략 설정 전 KIS 인증 확인: FE에서 계좌의 매매 전략을 선택·변경해 저장하려면 다음을 모두 만족해야 함
  - 계좌에 앱키와 시크릿키가 등록되어 있을 것
  - 그 앱키·시크릿키로 KIS 인증이 될 것: `KisAuth(account).auth()`를 호출한 뒤 `read_token()`으로 유효한 토큰이 있는지 확인 (`auth()`는 발급에 실패해도 예외를 내지 않으므로 반드시 `read_token()`까지 확인)
  - 둘 중 하나라도 실패하면 매매 전략을 저장하지 않고, 원인(키 미등록, KIS 인증 실패)을 화면에 보여줌
  - 앱키·시크릿키를 바꿔 저장할 때도 같은 확인을 거쳐, 인증이 안 되는 키로 매매 전략이 돌지 않게 함
  - 키를 바꿨을 때는 확인 전에 저장된 토큰(`access_token`, `token_issued_at`)을 먼저 비움. 비우지 않으면 `auth()`가 예전 키로 받은 토큰을 그대로 재사용해서, 새 키가 틀려도 `read_token()`이 토큰을 돌려줌

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 개요

한국투자증권(KIS) Open API로 여러 해외주식 계좌를 관리하고, 계좌마다 자동 투자 전략을 배치로 돌리는 Django 6 관리자 사이트. 프론트엔드는 AdminLTE 3.2(`static/`에 포함)이며, Google 로그인(allauth)을 사용합니다. 코드 주석과 UI 문구는 한국어입니다.

## 명령어

Python 3.12, 가상환경은 `admin_venv/` (Windows: `admin_venv\Scripts\Activate.ps1`).

```bash
pip install -r requirements.txt
python manage.py makemigrations && python manage.py migrate
python manage.py runserver
python manage.py qcluster                                  # django-q2 워커 (배치 실행에 필요)
python manage.py setup_strategy_schedule --time 20:50      # 매일 도는 전략 배치 스케줄 등록/수정 (KST)

python manage.py test                                      # 전체 테스트
python manage.py test investments.tests.StrategyBatchTest  # 단일 클래스
python manage.py test investments.tests.StrategyBatchTest.test_run_all_strategies_enqueues_only_accounts_with_strategy
```

- 의존성은 `pip list --format=freeze > requirements.txt`로 관리합니다.
- **`KisRealDatabaseIntegrationTest`는 실제 KIS API를 호출합니다.** 로컬 `db.sqlite3`에서 계좌와 토큰을 테스트 DB로 복사한 뒤 토큰을 재발급받고 잔고를 조회하므로, 네트워크와 실제 키가 필요합니다. 등록된 계좌가 없으면 건너뜁니다. 부작용 없이 돌리려면 `StrategyBatchTest`(mock 사용)만 실행하세요.
- 린터나 포매터 설정은 없습니다.

## 설정과 환경

- `manage.py`의 기본값은 `DJANGO_SETTINGS_MODULE=adminPage.settings.local`입니다. `settings/base.py`는 이 모듈 이름의 마지막 부분(`local`/`prod`)을 읽어 `.env`를 불러온 뒤 `.env.<mode>`로 덮어씁니다. 따라서 `DJANGO_SETTINGS_MODULE`이 없으면 base.py가 import 단계에서 실패합니다.
- `local`은 SQLite(`db.sqlite3`), 그 외에는 MySQL(`DATABASE_*` 환경변수)을 사용합니다.
- 필수 환경변수: `DJANGO_SECRET_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_SECRET`. 선택: `SUPERUSER_EMAILS`(쉼표로 구분).
- django-q2는 Redis 없이 Django ORM을 브로커로 씁니다(`Q_CLUSTER['orm']='default'`). 작업 결과와 스케줄은 DB에 저장됩니다.

## 아키텍처

### `core` 앱 — 인증과 공통 UI
- `AUTH_USER_MODEL = 'core.User'`(`profile_image_url` 필드 추가).
- 로그인 제한: `core/services/adapters.py`의 `MySocialAccountAdapter.pre_social_login`이 `AllowedEmail` 테이블에 없는 이메일은 막습니다. `SUPERUSER_EMAILS`에 있는 이메일은 슈퍼유저로 올려 주고 검사를 건너뜁니다.
- `core/services/signals.py`(`CoreConfig.ready()`에서 로드)는 Google 프로필 이미지를 동기화합니다.
- `/admin/login/`은 allauth 로그인 페이지로 리다이렉트됩니다.
- 템플릿: `templates/base.html`이 레이아웃이고, 페이지는 `{% block main_html %}` / `extra_css` / `extra_js`를 채웁니다. 사이드바의 active/open 상태는 `core/templatetags/nav_tags.py`의 `active_nav`와 `menu_open`(URL 부분 문자열 매칭)으로 처리합니다.

### `investments` 앱 — KIS 계좌, API, 전략 배치
- **`Account` 모델**은 계좌 정보와 KIS 접근 토큰(`access_token`, `token_issued_at`, `token_expired_at`, `token_is_use`)을 함께 저장합니다(예전 Token 테이블은 0006에서 병합됨). `is_token_expired`는 발급 후 23시간이 지나면 True를 반환합니다. 뷰는 모두 `owner=request.user`로 필터링합니다.
- **KIS 클라이언트**: `KisOverseasStockClient(account)`는 생성할 때 `KisAuth(account).auth()`를 호출해 토큰을 재사용하거나 새로 발급하고, 새 토큰은 `Account`에 저장합니다. 메서드(`inquire_balance`, `order` 등)는 대부분 pandas DataFrame을 반환합니다. KIS 관련 코드는 `services/kis/`에 모여 있습니다. `services/kis/kis_original/`은 KIS 공식 샘플 원본(해외·국내 주식)으로 참고용이며, 여기서 가져와 계좌 단위 클래스로 바꾼 것이 `services/kis/kis_auth.py`와 `services/kis/kis_overseas_stock.py`입니다.- **전략 플러그인** (`investments/strategies/`): 전략 하나는 `<key>.md`(front matter에 `name`/`description`/`enabled`)와 `<key>.py`(`BaseStrategy`를 상속한 `Strategy` 클래스와 `run(account, client)` 구현)로 이루어집니다. `load_strategies()`가 md 파일을 스캔하고(`_`로 시작하는 파일 제외, `lru_cache`로 프로세스당 한 번), `Account.strategy`의 `choices=get_strategy_choices`가 이를 동적으로 참조하므로 **전략을 추가해도 마이그레이션이 필요 없습니다.** 새 전략은 `_template.md`를 복사해 시작합니다. 캐시 때문에 md를 수정하면 runserver와 qcluster를 재시작해야 반영됩니다.
- **배치 흐름**: django-q `Schedule`("투자 전략 배치") → `services/tasks.run_all_strategies`가 `strategy`가 비어 있지 않은 계좌마다 `run_account_strategy`를 `async_task`로 큐에 넣음 → 워커가 전략을 찾아 `strategy.run(account, KisOverseasStockClient(account))`를 실행. 계좌마다 작업이 분리되어 있어 한 계좌가 실패해도 나머지는 계속 실행되고, 반환된 문자열은 작업 결과로 DB에 저장됩니다. 전략이 사라졌거나 비활성화된 경우에는 경고만 남기고 건너뜁니다.

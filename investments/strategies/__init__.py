"""
매매 전략 레지스트리

전략 하나 = 같은 이름의 파일 한 쌍
    <key>.md  : 전략 설명서 (상단 front matter에 이름/설명/사용 여부)
    <key>.py  : 실행 로직 (BaseStrategy를 상속한 Strategy 클래스)

'_'로 시작하는 파일(_template.md 등)은 전략으로 인식하지 않음
"""
import importlib
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

STRATEGY_DIR = Path(__file__).resolve().parent


@dataclass(frozen=True)
class StrategyInfo:
    key: str  # 파일명 (DB에 저장되는 값)
    name: str  # 화면에 보여줄 이름
    description: str
    enabled: bool
    body: str  # front matter를 제외한 md 본문
    md_path: Path


def _parse_front_matter(text):
    """
    md 상단의 '---' 블록을 key: value 딕셔너리로 변환
    (단순 key: value만 지원 → 별도 yaml 라이브러리 불필요)
    """
    meta = {}
    body = text
    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                body = "\n".join(lines[i + 1:]).strip()
                break
            if ":" in line:
                k, v = line.split(":", 1)
                meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


@lru_cache(maxsize=1)
def load_strategies():
    """strategies 폴더의 md 파일을 읽어 {key: StrategyInfo} 반환 (프로세스당 1회)"""
    strategies = {}
    for md_path in sorted(STRATEGY_DIR.glob("*.md")):
        key = md_path.stem
        if key.startswith("_"):
            continue
        if not (STRATEGY_DIR / f"{key}.py").exists():
            logger.warning("전략 '%s'의 실행 파일(%s.py)이 없어 건너뜁니다.", key, key)
            continue

        meta, body = _parse_front_matter(md_path.read_text(encoding="utf-8"))
        strategies[key] = StrategyInfo(
            key=key,
            name=meta.get("name", key),
            description=meta.get("description", ""),
            enabled=meta.get("enabled", "true").lower() == "true",
            body=body,
            md_path=md_path,
        )
    return strategies


def get_strategy_choices():
    """Account.strategy 선택지 (enabled: true 인 전략만)"""
    return [(s.key, s.name) for s in load_strategies().values() if s.enabled]


def get_strategy(key):
    """전략 key로 실행 객체 생성 (없거나 비활성화된 전략이면 None)"""
    info = load_strategies().get(key)
    if info is None or not info.enabled:
        return None

    module = importlib.import_module(f"{__name__}.{key}")
    return module.Strategy(info)

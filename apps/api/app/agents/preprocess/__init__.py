"""발화 전처리: 정규화 + ETF명·티커 인식(오타 허용). # P1-AG-01"""

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import cache
from app.agents.state import EtfEntity
from app.repositories import etf as etf_repo

_KEEP = re.compile(r"[^0-9A-Za-z가-힣\s%.,?!&+\-~/()]")
_TICKER = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_WS = re.compile(r"\s+")

# 한글로 쓴 브랜드 → 영문. ETF 이름이 영문 브랜드(TIGER·KODEX·ACE)라 '타이거 나스닥100'을
# 찾지 못했다(11-27 사용자 테스트). 이름 매칭과 브랜드 판별에만 쓰고 질문 문장은 바꾸지 않는다.
_BRAND_KO = {"타이거": "TIGER", "코덱스": "KODEX", "에이스": "ACE"}
# 국내 ETF 브랜드. 질문에 브랜드가 있는데 상품을 못 찾으면 '데이터에 없는 상품'으로 본다.
_BRANDS = (
    "kodex",
    "tiger",
    "ace",
    "rise",
    "sol",
    "plus",
    "hanaro",
    "kosef",
    "arirang",
    "kbstar",
    "kindex",
    "timefolio",
    "koact",
)
_BRAND_RE = re.compile(rf"(?<![a-z])({'|'.join(_BRANDS)})(?![a-z])")
# 브랜드 뒤에 상품명 대신 '거·것·상품·ETF'나 조사가 오면 그 브랜드 상품 전체를 묻는 질문이다('KODEX 거 총보수')
_GENERIC_AFTER = r"\s*(?:거|것|꺼|껀|건|상품|etf|쪽|(?:은|는|의)(?=\s|$))"


def normalize(text: str) -> str:
    """NFKC(전각→반각), 제어·특수기호 제거, 공백 정리. 숫자·%·소수점은 남긴다."""
    text = unicodedata.normalize("NFKC", text)
    text = _KEEP.sub(" ", text)
    text = re.sub(r"([?!.,])\1+", r"\1", text)  # 반복 기호 축약
    return _WS.sub(" ", text).strip()


def brand_en(text: str) -> str:
    """'타이거 나스닥100' → 'TIGER 나스닥100'(매칭용)."""
    for ko, en in _BRAND_KO.items():
        text = text.replace(ko, f" {en} ")
    return _WS.sub(" ", text).strip()


def mentioned_brands(text: str) -> list[str]:
    """질문에 나온 ETF 브랜드(소문자, 나온 순서). 한글 표기(타이거·코덱스·에이스)도 센다."""
    return list(dict.fromkeys(_BRAND_RE.findall(brand_en(text).lower())))


def brand_only(text: str, brand: str) -> bool:
    """'KODEX 거', 'KODEX 상품', 'KODEX의'처럼 상품명 없이 브랜드만 가리키는지."""
    return re.search(rf"(?<![a-z]){brand}{_GENERIC_AFTER}", brand_en(text).lower()) is not None


def brand_of(name: str) -> str:
    """ETF 이름의 브랜드('KODEX 200' → 'kodex')."""
    return name.split()[0].lower() if name.strip() else ""


def compact(text: str) -> str:
    """매칭용: 소문자, 한글·영숫자만(공백·기호 제거). 'S&P 500' → 'sp500'"""
    return re.sub(r"[^0-9a-z가-힣]", "", text.lower())


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    ticker: str
    name: str
    keys: tuple[str, ...]  # 이름·별칭의 compact 형태
    underlying_index: str | None
    category: str | None


async def load_catalog(maker: async_sessionmaker[AsyncSession]) -> list[CatalogEntry]:
    """ETF 마스터를 이름·별칭 사전으로 캐시(1일, 키 etf_master:all)."""
    c = cache.etf_cache()
    if (hit := c.get(cache.ETF_MASTER_ALL)) is not None:
        return hit
    async with maker() as session:
        rows = await etf_repo.list_etfs(session)
    catalog = [
        CatalogEntry(
            ticker=r.ticker,
            name=r.name,
            keys=tuple(dict.fromkeys(k for k in map(compact, [r.name, *r.aliases]) if k)),
            underlying_index=r.underlying_index,
            category=r.category,
        )
        for r in rows
    ]
    c[cache.ETF_MASTER_ALL] = catalog
    return catalog


def recognize_entities(
    text: str, catalog: list[CatalogEntry], *, fuzzy_threshold: int = 80, limit: int = 3
) -> list[EtfEntity]:
    """1) 티커 2) 이름·별칭 정확 포함(긴 것 우선) 3) rapidfuzz 부분 정렬로 오타 허용."""
    found: dict[str, EtfEntity] = {}
    pos: dict[str, int] = {}  # 질문 안 위치(언급 순서대로 돌려주기 위함)
    by_ticker = {e.ticker: e for e in catalog}
    q = compact(brand_en(text))

    for m in _TICKER.finditer(text):
        if (e := by_ticker.get(m.group(1))) is not None:
            found.setdefault(e.ticker, EtfEntity(e.ticker, e.name, m.group(1), 100.0, "ticker"))
            pos.setdefault(e.ticker, q.find(m.group(1)))

    masked = q
    keys = sorted(((k, e) for e in catalog for k in e.keys), key=lambda x: -len(x[0]))
    for key, e in keys:  # 정확 포함: 긴 키부터, 매칭된 구간은 지워 짧은 키의 중복 매칭을 막는다
        idx = masked.find(key)
        if idx >= 0 and len(key) >= 3:
            masked = masked[:idx] + "#" * len(key) + masked[idx + len(key) :]
            found.setdefault(e.ticker, EtfEntity(e.ticker, e.name, key, 100.0, "exact"))
            pos.setdefault(e.ticker, idx)

    best: dict[str, tuple[float, str, int, int]] = {}
    for key, e in keys:  # 오타 허용(남은 구간에서만)
        if e.ticker in found or len(key) < 5:
            continue
        al = fuzz.partial_ratio_alignment(key, masked, score_cutoff=fuzzy_threshold)
        if al is None or "#" in masked[al.dest_start : al.dest_end]:
            continue
        span = masked[al.dest_start : al.dest_end]
        # 짧은 공통 접두어(예: '샘플')만 맞는 경우를 거른다: 매칭 길이가 키의 80% 이상
        if len(span) < 0.8 * len(key):
            continue
        prev = best.get(e.ticker)
        if prev is None or al.score > prev[0]:
            best[e.ticker] = (al.score, span, al.dest_start, al.dest_end)
    # 겹치는 구간은 점수가 높은 쪽만 남긴다
    taken: list[tuple[int, int]] = []
    for ticker, (score, span, s, t) in sorted(best.items(), key=lambda x: -x[1][0]):
        if any(s < b and a < t for a, b in taken):
            continue
        taken.append((s, t))
        found[ticker] = EtfEntity(ticker, by_ticker[ticker].name, span, round(score, 1), "fuzzy")
        pos[ticker] = s

    return sorted(found.values(), key=lambda x: pos.get(x.ticker, 0))[:limit]

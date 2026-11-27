"""발화 전처리: 정규화, 오타·별칭·티커 ETF명 인식(P1-AG-01)."""

import pytest

from app.agents.preprocess import (
    CatalogEntry,
    brand_only,
    compact,
    load_catalog,
    mentioned_brands,
    normalize,
    recognize_entities,
)
from app.agents.state import AgentDeps


def test_normalize_spaces_and_symbols() -> None:
    assert normalize("  샘플   코스피200★★ 괴리율??  ") == "샘플 코스피200 괴리율?"
    # 전각 문자(NFKC 정규화 대상)는 코드 포인트로 만든다
    fullwidth = (
        "".join(chr(0xFEE0 + ord(c)) for c in "SAMPLE") + "\u3000" + "\uff10\uff0e\uff15\uff05"
    )
    assert normalize(fullwidth) == "SAMPLE 0.5%"


@pytest.mark.parametrize(
    ("query", "tickers", "method"),
    [
        ("샘플 코스피200 시세", ["900010"], "exact"),
        ("샘플코스피 괴리율", ["900010"], "exact"),  # 별칭
        ("샘플 나스댁100 괴리율 알려줘", ["900040"], "fuzzy"),  # 오타
        ("샘풀코스닥 시세", ["900020"], "fuzzy"),  # 오타
        ("샘플 S&P 500 가격", ["900030"], "exact"),  # 기호·공백 차이
        ("900050 정보", ["900050"], "ticker"),
        ("샘플 코스피200이랑 샘플 미국S&P500 비교", ["900010", "900030"], "exact"),  # 언급 순서
    ],
)
async def test_recognizes_etf_names(
    deps: AgentDeps, query: str, tickers: list[str], method: str
) -> None:
    catalog = await load_catalog(deps.maker)
    found = recognize_entities(normalize(query), catalog)
    assert [e.ticker for e in found] == tickers
    assert found[0].method == method


async def test_no_false_positive_on_generic_question(deps: AgentDeps) -> None:
    catalog = await load_catalog(deps.maker)
    assert recognize_entities("괴리율이 뭐야?", catalog) == []
    assert recognize_entities("샘플 데이터라는 게 뭐야?", catalog) == []


# 11-27 사용자 테스트: 한글 브랜드 표기, 브랜드만 가리키는 질문, 데이터에 없는 상품
def _real_like_catalog() -> list[CatalogEntry]:
    names = {
        "133690": "TIGER 미국나스닥100",
        "379810": "KODEX 미국나스닥100",
        "367380": "ACE 미국나스닥100",
        "069500": "KODEX 200",
        "458730": "TIGER 미국배당다우존스",
    }
    return [CatalogEntry(t, n, (compact(n),), None, None) for t, n in names.items()]


@pytest.mark.parametrize(
    ("query", "ticker"),
    [
        ("타이거 나스닥100 보수 알려줘", "133690"),
        ("코덱스 200 총보수", "069500"),
        ("에이스 미국나스닥100 실부담비용", "367380"),
        ("타이거 미국배당다우존스 분배 주기", "458730"),
    ],
)
def test_recognizes_korean_brand_names(query: str, ticker: str) -> None:
    found = recognize_entities(normalize(query), _real_like_catalog())
    assert [e.ticker for e in found] == [ticker]


@pytest.mark.parametrize(
    ("query", "brands", "only"),
    [
        ("KODEX 거 총보수 알려줘", ["kodex"], True),
        ("코덱스 상품들 총보수", ["kodex"], True),
        ("KODEX의 총보수는?", ["kodex"], True),
        ("KODEX 미국S&P500 총보수 알려줘", ["kodex"], False),  # 상품 이름(데이터에 없음)
        ("RISE 미국S&P500 총보수", ["rise"], False),
        ("인터페이스가 뭐야?", [], None),  # '페이스'를 브랜드로 보지 않는다
        ("총보수 0.1% 이하 ETF", [], None),
    ],
)
def test_brand_mentions(query: str, brands: list[str], only: bool | None) -> None:
    text = normalize(query)
    assert mentioned_brands(text) == brands
    if only is not None:
        assert brand_only(text, brands[0]) is only
    if brands:  # 상품 이름을 찾지 못한다(그래서 브랜드로 판단한다)
        assert recognize_entities(text, _real_like_catalog()) == []

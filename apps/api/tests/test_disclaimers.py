"""고지: 샘플 상품일 때만 '개발용 샘플 데이터', 기준일 문구, 시세를 물을 때 안내."""

import pytest
from sqlalchemy import update

from app.agents import etf_info
from app.agents.compose import disclaimer_texts
from app.agents.graph import run_graph
from app.agents.state import AgentDeps
from app.repositories.models import EtfMaster
from app.tools import price_lookup


async def ask(deps: AgentDeps, q: str):
    return await run_graph(deps, request_id="test", query=q)


@pytest.fixture
async def real_900010(deps: AgentDeps):
    """900010을 실데이터(load_real이 넣는 source)로 바꿔 두고 끝나면 되돌린다."""
    async with deps.maker() as s:
        await s.execute(
            update(EtfMaster).where(EtfMaster.ticker == "900010").values(source="manual_csv")
        )
        await s.commit()
    yield
    async with deps.maker() as s:
        await s.execute(
            update(EtfMaster).where(EtfMaster.ticker == "900010").values(source="sample")
        )
        await s.commit()


async def test_sample_product_gets_sample_notice(deps: AgentDeps) -> None:
    st = await ask(deps, "샘플 코스피200 정보 알려줘")
    assert st["verdict"] == "pass"
    assert disclaimer_texts()["sample_data"] in st["answer"]
    assert "sample_data" in st["disclaimer_ids"]


async def test_real_product_has_no_sample_notice(deps: AgentDeps, real_900010: None) -> None:
    st = await ask(deps, "샘플 코스피200 정보 알려줘")
    assert st["verdict"] == "pass", st.get("guard_reasons")
    assert disclaimer_texts()["sample_data"] not in st["answer"]
    assert "sample_data" not in st["disclaimer_ids"]
    # 기준일 고지는 지금 데이터(보수·실부담비용·순자산)에 맞는 문구
    assert disclaimer_texts()["data_as_of"] in st["answer"]
    assert "실부담비용" in disclaimer_texts()["data_as_of"]


async def test_mixed_sample_and_real_keeps_sample_notice(
    deps: AgentDeps, real_900010: None
) -> None:
    st = await ask(deps, "샘플 코스피200이랑 샘플 미국S&P500 비교해줘")
    assert disclaimer_texts()["sample_data"] in st["answer"]


async def test_faq_has_no_sample_notice(deps: AgentDeps) -> None:
    st = await ask(deps, "괴리율이 뭐야?")
    assert disclaimer_texts()["sample_data"] not in st["answer"]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("샘플 코스피200 현재가 얼마야?", True),
        ("샘플 코스피200 종가 알려줘", True),
        ("샘플 코스피200 NAV랑 괴리율", True),
        ("샘플 코스피200 총보수 알려줘", False),
    ],
)
def test_asks_price(text: str, expected: bool) -> None:
    assert etf_info.asks_price(text) is expected


async def test_price_question_without_price_data_says_not_provided(
    deps: AgentDeps, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def no_prices(session, tickers):
        return {}

    monkeypatch.setattr(price_lookup, "latest", no_prices)
    st = await ask(deps, "샘플 코스피200 현재가 얼마야?")
    assert st["verdict"] == "pass", st.get("guard_reasons")
    assert etf_info.NO_PRICE_NOTE in st["answer"]


async def test_price_question_with_price_data_has_no_notice(deps: AgentDeps) -> None:
    st = await ask(deps, "샘플 코스피200 종가 알려줘")
    assert etf_info.NO_PRICE_NOTE not in st["answer"]


async def test_non_price_question_has_no_notice(deps: AgentDeps, monkeypatch) -> None:
    async def no_prices(session, tickers):
        return {}

    monkeypatch.setattr(price_lookup, "latest", no_prices)
    st = await ask(deps, "샘플 코스피200 총보수 알려줘")
    assert etf_info.NO_PRICE_NOTE not in st["answer"]


@pytest.mark.parametrize(
    "text",
    ["시가총액 큰 ETF 알려줘", "샘플 코스피200 시가 총액 얼마야?"],
)
def test_market_cap_is_not_price_question(text: str) -> None:
    assert etf_info.asks_price(text) is False


async def test_forecast_part_gets_refusal_not_price_notice(
    deps: AgentDeps, fake_llm, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    async def no_prices(session, tickers):
        return {}

    monkeypatch.setattr(price_lookup, "latest", no_prices)
    fake_llm.push(
        "classify",
        json.dumps({"intents": ["etf_info"], "refuse": ["high_risk"], "confidence": 0.9}),
    )
    st = await ask(deps, "샘플 코스피200 총보수 알려주고 주가 오를지도 알려줘")
    assert st["refuse"] == ["high_risk"]
    assert etf_info.NO_PRICE_NOTE not in st["answer"]

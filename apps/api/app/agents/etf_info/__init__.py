"""ETF 정보 수집: 검색·필터, 최신 시세·괴리율, 2~3개 비교. 숫자는 DB 값만, 기준일 표기. # P1-AG-03

LLM을 부르지 않는다. DB 표는 화면에 그대로 붙고, 설명 문장은 답변 합성(compose)이 한 번에 쓴다.
"""

import re

from app.agents.preprocess import load_catalog
from app.agents.state import AgentDeps, AgentResult, GraphState, Source
from app.tools import compare, etf_search, price_lookup

NAME = "etf_info"
SEARCH_LIMIT = 10
NO_PRICE_NOTE = (
    "이 서비스는 시세(종가·NAV·괴리율·거래량)를 제공하지 않습니다. "
    "현재 시세는 운용사 홈페이지나 한국거래소에서 확인해 주세요."
)
_PRICE_WORDS = re.compile(
    r"시세|종가|현재가|시가(?!\s*총액)|주가|가격|얼마에\s*거래|nav|괴리율|거래량", re.I
)


def asks_price(text: str) -> bool:
    """질문이 시세(종가·NAV·괴리율·거래량 등)를 묻는지."""
    return bool(_PRICE_WORDS.search(text))


async def run(state: GraphState, deps: AgentDeps) -> AgentResult:
    await deps.emit(NAME, "ETF 정보를 찾는 중")
    tickers = [e.ticker for e in state.get("entities") or []][:3]
    notes: list[str] = []
    async with deps.maker() as session:
        if tickers:
            etfs = await price_lookup.etfs(session, tickers)
            prices = await price_lookup.latest(session, [e.ticker for e in etfs])
            # 요청한 상품의 시세만 본다(상품마다 기준일이 다를 수 있다)
            dates = compare.as_of_dates([prices.get(e.ticker) for e in etfs])
            if len(etfs) >= 2:
                table = compare.compare_table(etfs, prices)
                title = f"{len(etfs)}개 상품 비교"
            else:
                table = compare.detail_table(etfs[0], prices.get(etfs[0].ticker))
                title = f"{etfs[0].name} 정보"
            # 시세를 물었는데 DB에 시세가 없으면(실데이터는 시세 미수집, 범위 조정 2차) 안내한다.
            # '주가 오를까?'처럼 전망을 묻는 부분은 거절 문장(refuse)이 답하므로 안내를 붙이지 않는다.
            if (
                asks_price(state["normalized"])
                and "high_risk" not in (state.get("refuse") or [])
                and not any(e.ticker in prices for e in etfs)
            ):
                notes.append(NO_PRICE_NOTE)
        else:
            catalog = await load_catalog(deps.maker)
            if state.get("unknown_etf"):
                # 브랜드는 있는데 데이터에 없는 상품(11-27 사용자 테스트). 조건 검색으로 넘어가면
                # '미국' 같은 말이 조건이 되어 상관없는 표가 붙는다. 재계획하지 않는다.
                names = ", ".join(c.name for c in catalog)
                return AgentResult(
                    agent=NAME,
                    found=False,
                    content=(
                        "질문하신 상품은 이 서비스의 데이터에 없어요. "
                        f"지금 안내할 수 있는 ETF는 {names}입니다."
                    ),
                )
            indexes = sorted({c.underlying_index for c in catalog if c.underlying_index})
            filters = etf_search.parse_filters(state["normalized"], indexes)
            filters = etf_search.merge_plan_conditions(
                filters, state.get("plan_conditions") or {}, indexes
            )
            # 재계획 조건은 빈 칸만 채운다(사용자가 말한 조건은 바꾸거나 완화하지 않는다)
            filters = etf_search.merge_plan_conditions(
                filters, state.get("replan_conditions") or {}, indexes
            )
            if filters.is_empty():
                # 계획이 조건 검색을 골랐는데 조건을 하나도 알아듣지 못했으면 '결과 0건'으로 보고 재계획한다
                # ('나스닥 추종 ETF 목록' → DB 표기 'NASDAQ 100'). ETF 이름이 애매한 질문은 재계획하지
                # 않고 이 안내로 끝난다(범위 조정 3차).
                searched = any(t.get("name") == "etf_search" for t in state.get("plan_tools") or [])
                return AgentResult(
                    agent=NAME,
                    found=False,
                    zero_results=searched,
                    content=(
                        "질문에서 ETF 이름을 찾지 못했어요. 상품명이나 종목코드(6자리)를 알려 주시거나, "
                        "'총보수 0.1% 이하 해외 주식 ETF'처럼 조건을 말씀해 주세요."
                    ),
                )
            # 한 건 더 읽어 잘렸는지 안다. 잘린 목록을 '검색 결과 10건'이라고 하면 전체가 10건으로 읽힌다.
            etfs = await etf_search.search(session, filters, limit=SEARCH_LIMIT + 1)
            more = len(etfs) > SEARCH_LIMIT
            etfs = etfs[:SEARCH_LIMIT]
            if note := await etf_search.unverifiable_note(session, filters):
                notes.append(note)
            if not etfs:
                return AgentResult(
                    agent=NAME,
                    found=False,
                    zero_results=True,
                    content=" ".join(
                        [f"조건({filters.describe()})에 맞는 ETF가 없습니다.", *notes]
                    ),
                )
            if unknown := etf_search.region_unverified(filters, etfs):
                names = ", ".join(e.name for e in unknown)
                notes.append(
                    f"다음 상품은 분류에 지역 표기가 없어 {filters.region} 상품인지 확인하지 못했습니다: {names}"
                )
            table = compare.list_table(etfs, net_assets=filters.sort_key() == "net_assets")
            title = f"검색 결과({filters.describe()}) {len(etfs)}건"
            if more:
                title = (
                    f"검색 결과({filters.describe()}) {filters.sort_label()}으로 {len(etfs)}건만 표시"
                    "(조건에 맞는 상품이 더 있습니다)"
                )
            dates = []

    # 샘플 데이터인지 판별: 모든 ETF가 source='sample'이면 샘플
    is_sample = bool(etfs) and all(e.source == "sample" for e in etfs)

    # 기준일 문구: 시세 기준일과 마스터 기준일(실부담비용·순자산)을 모두 모은다
    master_dates = compare.master_as_of_dates(etfs) if tickers else []
    all_dates = sorted(set(dates) | set(master_dates))
    all_as_of = compare.as_of_text(all_dates)

    if len(all_dates) > 1 and len(dates) > 1:
        # 상품끼리 시세 기준일이 다른 경우
        as_of_line = f"기준일: 상품마다 다릅니다({all_as_of}). 표의 '시세 기준일'을 확인하세요."
    elif len(all_dates) > 1:
        # 시세 기준일은 같거나 없고, 마스터 기준일(실부담비용·순자산)만 다른 경우
        as_of_line = f"기준일: 항목마다 다릅니다({all_as_of}). 표의 기준일 항목을 확인하세요."
    elif all_as_of:
        as_of_line = f"기준일: {all_as_of}"
    else:
        as_of_line = "출처: ETF 마스터(샘플)" if is_sample else "출처: ETF 마스터"
    data = "\n\n".join([f"**{title}**", table, *notes, as_of_line])

    # 출처 제목: 샘플이면 "(샘플)", 실데이터면 CSV 출처를 중복 없이 모은다
    if is_sample:
        source_title = "ETF 마스터·일별 시세 DB(샘플)"
    else:
        raw_sources: list[str] = []
        for e in etfs:
            for s in (e.fee_source, e.actual_expense_source, e.net_assets_source):
                if s and s not in raw_sources:
                    raw_sources.append(s)
        source_title = ", ".join(raw_sources) if raw_sources else "ETF 마스터"
    source = Source(
        title=source_title,
        location=f"기준일 {all_as_of}" if all_as_of else None,
        kind="etf_data",
    )
    return AgentResult(
        agent=NAME,
        content=data,
        context=f"[ETF 데이터] (DB 조회값, 화면에 표로 그대로 붙는다)\n{data}",
        sources=[source],
        evidence=[data],
        retrieved_ids=[f"etf:{e.ticker}" for e in etfs],
        # 샘플 상품이 하나라도 있으면 '개발용 샘플 데이터' 고지를 붙인다(실데이터만이면 안 붙음)
        disclaimers=["sample_data"] if any(e.source == "sample" for e in etfs) else [],
        missing_fields=missing_fields(etfs, state.get("plan_metrics") or []) if tickers else [],
    )


def missing_fields(etfs: list, metrics: list[str]) -> list[str]:
    """계획한 항목 중 DB 값이 없는 것("종목코드:항목"). 부족 판정 missing_field에 쓴다."""
    return [f"{e.ticker}:{m}" for e in etfs for m in metrics if getattr(e, m, None) is None]

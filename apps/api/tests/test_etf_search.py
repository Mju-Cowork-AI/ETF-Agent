"""ETF 검색 조건 해석: 보수 범위(이하·미만·이상·초과), 보수와 무관한 숫자, 지역 필터 (P1-AG-03)."""

from decimal import Decimal

import pytest

from app.agents.state import AgentDeps
from app.tools import compare
from app.tools.etf_search import EtfFilters, parse_filters, search


@pytest.mark.parametrize(
    ("text", "expected", "described"),
    [
        ("총보수 0.1% 이하 ETF", ("max", "0.1", False), "총보수 0.1% 이하"),
        ("총보수 0.1% 미만 ETF", ("max", "0.1", True), "총보수 0.1% 미만"),
        ("보수 0.5 이상인 ETF", ("min", "0.5", False), "총보수 0.5% 이상"),
        ("수수료 0.5% 초과 ETF", ("min", "0.5", True), "총보수 0.5% 초과"),
        ("보수 0.3프로 ETF", ("max", "0.3", False), "총보수 0.3% 이하"),
        ("보수 0.3% 넘는 ETF 목록", ("min", "0.3", True), "총보수 0.3% 초과"),
        ("보수가 0.5%보다 높은 채권 ETF", ("min", "0.5", True), "분류 '채권', 총보수 0.5% 초과"),
        ("수수료가 0.2%보다 낮은 ETF", ("max", "0.2", True), "총보수 0.2% 미만"),
        ("보수 0% 이하 ETF", ("max", "0", False), "총보수 0% 이하"),
        # 수치와 비교어 사이에 조사·부사가 낀 표현
        ("총보수 0.3%를 초과하는 ETF 찾아줘", ("min", "0.3", True), "총보수 0.3% 초과"),
        ("보수가 0.3%가 넘는 ETF 목록", ("min", "0.3", True), "총보수 0.3% 초과"),
        ("총보수 0.3%는 넘는 ETF 검색", ("min", "0.3", True), "총보수 0.3% 초과"),
        ("보수 0.5%보다 더 낮은 ETF", ("max", "0.5", True), "총보수 0.5% 미만"),
        ("보수 0.3% ETF 중 순자산 많은 것", ("max", "0.3", False), "총보수 0.3% 이하"),
    ],
)
def test_fee_condition(text: str, expected: tuple[str, str, bool], described: str) -> None:
    f = parse_filters(text, [])
    side, value, exclusive = expected
    if side == "max":
        assert (f.max_fee, f.max_exclusive, f.min_fee) == (Decimal(value), exclusive, None)
    else:
        assert (f.min_fee, f.min_exclusive, f.max_fee) == (Decimal(value), exclusive, None)
    assert f.describe() == described


def test_fee_range_keeps_both_bounds() -> None:
    f = parse_filters("수수료 0.1% 이상 0.3% 이하 ETF", [])
    assert (f.min_fee, f.max_fee) == (Decimal("0.1"), Decimal("0.3"))
    assert not f.min_exclusive and not f.max_exclusive
    assert not f.is_empty()


@pytest.mark.parametrize(
    "text",
    ["보수 0.1~0.3% ETF 찾아줘", "보수 0.1%에서 0.3% 사이 ETF", "수수료 0.1%부터 0.3%까지인 ETF"],
)
def test_fee_range_notations(text: str) -> None:
    f = parse_filters(text, [])
    assert (f.min_fee, f.max_fee) == (Decimal("0.1"), Decimal("0.3"))
    assert f.describe() == "총보수 0.3% 이하, 총보수 0.1% 이상"


def test_percent_of_another_metric_is_not_a_fee() -> None:
    f = parse_filters("수수료 싼 배당률 4% 이상 ETF 찾아줘", [])
    assert not f.has_fee() and f.category == "배당"


def test_zero_fee_bound_is_a_condition() -> None:
    assert not EtfFilters(max_fee=Decimal(0)).is_empty()


@pytest.mark.parametrize("text", ["보수 낮은 순으로 3개 찾아줘", "수수료 싼 ETF 5개 알려줘"])
def test_count_is_not_read_as_fee(text: str) -> None:
    f = parse_filters(text, [])
    assert f.max_fee is None and f.min_fee is None


async def test_exclusive_bound_drops_boundary_value(deps: AgentDeps) -> None:
    async with deps.maker() as s:
        upto = await search(s, EtfFilters(region="해외", max_fee=Decimal("0.07")))
        below = await search(
            s, EtfFilters(region="해외", max_fee=Decimal("0.07"), max_exclusive=True)
        )
    assert any(e.total_expense_ratio == Decimal("0.07") for e in upto)
    assert below and all(e.total_expense_ratio < Decimal("0.07") for e in below)


async def test_region_is_filtered_before_limit(deps: AgentDeps) -> None:
    async with deps.maker() as s:
        rows = await search(s, EtfFilters(region="국내"), limit=3)
    assert len(rows) == 3  # 지역 밖 상품이 LIMIT 자리를 차지하지 않는다
    assert all(e.category.startswith("국내") for e in rows)


@pytest.mark.parametrize(
    ("text", "ticker"),
    [("국내 리츠 ETF 목록", "900170"), ("미국 원자재 ETF 목록", "900130")],
)
async def test_region_does_not_hide_categories_without_region(
    deps: AgentDeps, text: str, ticker: str
) -> None:
    f = parse_filters(text, [])
    assert f.region and f.category
    async with deps.maker() as s:
        rows = await search(s, f)
    assert ticker in [e.ticker for e in rows]  # 분류에 지역 표기가 없어도 0건이 되지 않는다


async def test_region_still_separates_categories_that_have_one(deps: AgentDeps) -> None:
    async with deps.maker() as s:
        rows = await search(s, parse_filters("해외 채권 ETF 목록", []))
    assert [e.ticker for e in rows] == ["900100"]  # 국내 채권(900090)은 빠진다


# ---------- 정렬(리허설 gen16: '해외 ETF 실부담비용 순서대로') ----------
@pytest.mark.parametrize(
    ("text", "sort", "desc", "label"),
    [
        (
            "해외 ETF 실부담비용 순서대로 알려줘",
            "actual_expense_ratio",
            False,
            "실부담비용 낮은 순",
        ),
        ("실부담비용이 가장 낮은 ETF", "actual_expense_ratio", False, "실부담비용 낮은 순"),
        ("총보수 높은 순으로 보여줘", "total_expense_ratio", True, "총보수 높은 순"),
        ("순자산 순으로 보여줘", "net_assets", True, "순자산 큰 순"),
        ("규모가 제일 작은 ETF", "net_assets", False, "순자산 작은 순"),
    ],
)
def test_sort_is_parsed(text: str, sort: str, desc: bool, label: str) -> None:
    f = parse_filters(text, [])
    assert (f.sort, f.sort_desc) == (sort, desc)
    assert f.sort_label() == label
    assert not f.is_empty()  # 정렬만 있어도 조건 검색이다


@pytest.mark.parametrize("text", ["실부담비용 알려줘", "KODEX 200 총보수", "순자산이 뭐야?"])
def test_metric_without_order_is_not_sort(text: str) -> None:
    assert parse_filters(text, []).sort is None


async def test_search_sorts_by_actual_expense(deps: AgentDeps) -> None:
    from datetime import date

    from sqlalchemy import select

    from app.repositories.models import EtfMaster

    values = {"900030": "0.1430", "900040": "0.1092", "900080": "0.1571", "900100": "0.1308"}
    async with deps.maker() as s:
        rows = (await s.scalars(select(EtfMaster).where(EtfMaster.ticker.in_(values)))).all()
        for e in rows:
            e.actual_expense_ratio = Decimal(values[e.ticker])
            e.actual_expense_as_of = date(2026, 10, 30)
        await s.flush()  # 같은 세션에서만 보이고 테스트 끝에 되돌린다
        got = await search(s, parse_filters("해외 ETF 실부담비용 순서대로", []))
        table = compare.list_table(got)
        ordered = [e.ticker for e in got if e.ticker in values]
        await s.rollback()
    assert ordered == ["900040", "900100", "900030", "900080"]  # 낮은 순, 값 없는 상품은 뒤
    assert "실부담비용(기준일)" in table and "0.1092% (2026-10-30)" in table


def test_list_table_shows_net_assets_with_date_when_sorted_by_it() -> None:
    from datetime import date

    from app.repositories.models import EtfMaster

    e = EtfMaster(
        ticker="133690",
        name="TIGER 미국나스닥100",
        total_expense_ratio=Decimal("0.0068"),
        net_assets=11695422000000,
        net_assets_as_of=date(2026, 10, 30),
    )
    assert "순자산" not in compare.list_table([e])
    table = compare.list_table([e], net_assets=True)
    assert "순자산(기준일)" in table and "(2026-10-30)" in table

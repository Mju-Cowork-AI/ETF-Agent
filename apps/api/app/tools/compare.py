"""ETF 정보 표·2~3개 상품 비교표(마크다운). 숫자는 DB 값만 쓴다. # P1-AG-03"""

from collections.abc import Sequence
from datetime import date

from app.repositories.models import EtfMaster, PriceDaily
from app.tools import fmt

# 항목 정의: (라벨, 값 함수, 시세 필수 여부)
# price_only=True인 행은 모든 상품에 시세가 없으면 숨긴다.
_ROWS: list[tuple[str, object, bool]] = [
    ("종목코드", lambda e, p: e.ticker, False),
    ("운용사", lambda e, p: e.issuer or "-", False),
    ("기초지수", lambda e, p: e.underlying_index or "-", False),
    ("분류", lambda e, p: e.category or "-", False),
    ("총보수", lambda e, p: fmt.fee(e.total_expense_ratio), False),
    ("실부담비용", lambda e, p: fmt.fee(e.actual_expense_ratio), False),
    (
        "실부담비용 기준일",
        lambda e, p: e.actual_expense_as_of.isoformat() if e.actual_expense_as_of else "-",
        False,
    ),
    ("분배주기", lambda e, p: e.distribution_cycle or "-", False),
    ("환헤지", lambda e, p: e.currency_hedged or "-", False),
    ("종가", lambda e, p: fmt.won(p.close_price) if p else "-", True),
    ("NAV", lambda e, p: fmt.won(p.nav, 2) if p else "-", True),
    ("괴리율", lambda e, p: fmt.pct(p.premium_discount) if p else "-", True),
    ("거래량", lambda e, p: fmt.shares(p.volume) if p else "-", True),
    (
        "순자산",
        lambda e, p: (
            fmt.eok(e.net_assets)
            if e.net_assets
            else (fmt.eok(p.net_assets) if p and p.net_assets else "-")
        ),
        False,
    ),
    (
        "순자산 기준일",
        lambda e, p: (
            e.net_assets_as_of.isoformat()
            if e.net_assets_as_of
            else (p.trade_date.isoformat() if p else "-")
        ),
        False,
    ),
    ("상장일", lambda e, p: e.listed_date.isoformat() if e.listed_date else "-", False),
    # 시세 기준일은 상품마다 다를 수 있다(거래 정지·수집 누락). 열마다 자기 날짜를 적는다.
    ("시세 기준일", lambda e, p: p.trade_date.isoformat() if p else "-", True),
]


def _visible_rows(
    etfs: Sequence[EtfMaster], prices: dict[str, PriceDaily | None]
) -> list[tuple[str, object]]:
    """시세가 하나도 없으면 시세 전용 행을 숨긴다."""
    has_any_price = any(prices.get(e.ticker) for e in etfs)
    return [(label, fn) for label, fn, price_only in _ROWS if not price_only or has_any_price]


def as_of_dates(prices: Sequence[PriceDaily | None]) -> list[date]:
    """시세 기준일(중복 없이 오름차순). 상품마다 다르면 둘 이상이 나온다."""
    return sorted({p.trade_date for p in prices if p is not None})


def master_as_of_dates(etfs: Sequence[EtfMaster]) -> list[date]:
    """EtfMaster의 기준일들(실부담비용, 순자산). 중복 없이 오름차순."""
    dates: set[date] = set()
    for e in etfs:
        if e.actual_expense_as_of:
            dates.add(e.actual_expense_as_of)
        if e.net_assets_as_of:
            dates.add(e.net_assets_as_of)
    return sorted(dates)


def as_of_text(dates: Sequence[date]) -> str | None:
    """기준일 표기. 날짜가 여럿이면 가장 최근 날짜 하나로 뭉뚱그리지 않고 범위로 적는다."""
    if not dates:
        return None
    if len(dates) == 1:
        return dates[0].isoformat()
    return f"{dates[0].isoformat()} ~ {dates[-1].isoformat()}"


def _cell(s: str) -> str:
    return s.replace("|", "/")


def detail_table(etf: EtfMaster, price: PriceDaily | None) -> str:
    rows = _visible_rows([etf], {etf.ticker: price})
    lines = [f"| 항목 | {_cell(etf.name)} |", "| --- | --- |"]
    lines += [f"| {label} | {_cell(fn(etf, price))} |" for label, fn in rows]
    return "\n".join(lines)


def compare_table(etfs: Sequence[EtfMaster], prices: dict[str, PriceDaily]) -> str:
    rows = _visible_rows(etfs, prices)
    head = "| 항목 | " + " | ".join(_cell(e.name) for e in etfs) + " |"
    sep = "| --- |" + " --- |" * len(etfs)
    body = [
        f"| {label} | " + " | ".join(_cell(fn(e, prices.get(e.ticker))) for e in etfs) + " |"
        for label, fn in rows
    ]
    return "\n".join([head, sep, *body])


def _with_date(value: str, as_of: date | None) -> str:
    return f"{value} ({as_of.isoformat()})" if value != "-" and as_of else value


def list_table(etfs: Sequence[EtfMaster], *, net_assets: bool = False) -> str:
    """조건 검색 목록. 비용 비교는 총보수만으로 하지 않도록 실부담비용(기준일)을 함께 둔다(순위 규칙 R2).

    net_assets=True(순자산 정렬)면 순자산(상품별 기준일) 열을 더한다(순자산 기준일이 상품마다 다름).
    """
    head = "| 이름 | 종목코드 | 분류 | 기초지수 | 총보수 | 실부담비용(기준일) |"
    sep = "| --- | --- | --- | --- | --- | --- |"
    if net_assets:
        head += " 순자산(기준일) |"
        sep += " --- |"
    lines = [head, sep]
    for e in etfs:
        row = (
            f"| {_cell(e.name)} | {e.ticker} | {_cell(e.category or '-')} | "
            f"{_cell(e.underlying_index or '-')} | {fmt.fee(e.total_expense_ratio)} | "
            f"{_with_date(fmt.fee(e.actual_expense_ratio), e.actual_expense_as_of)} |"
        )
        if net_assets:
            eok = fmt.eok(e.net_assets) if e.net_assets else "-"
            row += f" {_with_date(eok, e.net_assets_as_of)} |"
        lines.append(row)
    return "\n".join(lines)

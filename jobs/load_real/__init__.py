"""실데이터(수동 CSV) 검증·적재. 적재 전에 샘플 ETF(source='sample')와 그 시세를 삭제한다.

팀 규칙: 모든 값에 출처·수집일·항목별 기준일.
검증 실패 시 적재 중단(ValueError). 실부담비용 기준일이 1년 넘으면 경고(적재는 계속).
"""

import csv
import logging
import warnings
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app import cache
from app.repositories import etf as etf_repo
from app.repositories.models import EtfMaster, PriceDaily
from app.settings import REPO_ROOT

REAL_DIR = REPO_ROOT / "data" / "real"

logger = logging.getLogger(__name__)

REQUIRED_FIELDS = [
    "ticker",
    "name",
    "issuer",
    "underlying_index",
    "total_expense_ratio",
    "actual_expense_ratio",
    "actual_expense_as_of",
    "distribution_cycle",
    "currency_hedged",
    "net_assets",
    "net_assets_as_of",
    "listed_date",
]


def _parse_decimal(value: str, field: str, ticker: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as e:
        raise ValueError(f"{ticker}: {field} 값 '{value}'이(가) 숫자가 아닙니다") from e


def validate(rows: list[dict[str, str]]) -> list[dict[str, Any]]:
    """CSV 행을 검증하고 파싱된 딕셔너리 리스트를 반환한다. 실패 시 ValueError."""
    if not rows:
        raise ValueError("CSV에 데이터 행이 없습니다")

    errors: list[str] = []
    parsed: list[dict[str, Any]] = []
    today = date.today()

    for i, row in enumerate(rows, 1):
        ticker = row.get("ticker", f"행{i}")

        # 필수 항목 결측
        for field in REQUIRED_FIELDS:
            if not row.get(field, "").strip():
                errors.append(f"{ticker}: 필수 항목 '{field}'이(가) 비어 있습니다")

        if errors:
            continue

        ter = _parse_decimal(row["total_expense_ratio"], "total_expense_ratio", ticker)
        aer = _parse_decimal(row["actual_expense_ratio"], "actual_expense_ratio", ticker)

        # 음수 보수
        if ter < 0:
            errors.append(f"{ticker}: 총보수({ter})가 음수입니다")
        if aer < 0:
            errors.append(f"{ticker}: 실부담비용({aer})이 음수입니다")

        ae_as_of = date.fromisoformat(row["actual_expense_as_of"])
        na_as_of = date.fromisoformat(row["net_assets_as_of"])

        # 실부담비용 기준일 1년 경과 경고
        if (today - ae_as_of) > timedelta(days=365):
            warnings.warn(
                f"{ticker}: 실부담비용 기준일({ae_as_of})이 1년 넘게 지났습니다",
                UserWarning,
                stacklevel=2,
            )

        aliases_raw = row.get("aliases", "").strip()
        aliases = [a.strip() for a in aliases_raw.split(";") if a.strip()] if aliases_raw else []

        parsed.append(
            {
                "ticker": row["ticker"].strip(),
                "name": row["name"].strip(),
                "aliases": aliases,
                "issuer": row["issuer"].strip(),
                "underlying_index": row["underlying_index"].strip(),
                "total_expense_ratio": ter,
                "actual_expense_ratio": aer,
                "actual_expense_as_of": ae_as_of,
                "distribution_cycle": row["distribution_cycle"].strip(),
                "currency_hedged": row["currency_hedged"].strip(),
                "net_assets": int(row["net_assets"]),
                "net_assets_as_of": na_as_of,
                "category": row.get("category", "").strip() or None,
                "listed_date": date.fromisoformat(row["listed_date"]),
                "fee_source": row.get("fee_source", "").strip() or None,
                "actual_expense_source": row.get("actual_expense_source", "").strip() or None,
                "net_assets_source": row.get("net_assets_source", "").strip() or None,
                "checked_date": (
                    date.fromisoformat(row["checked_date"])
                    if row.get("checked_date", "").strip()
                    else None
                ),
                "description": row.get("description", "").strip() or None,
                "source": "manual_csv",
            }
        )

    if errors:
        raise ValueError("검증 실패:\n" + "\n".join(errors))

    return parsed


def load_csv(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


async def delete_samples(session: AsyncSession) -> dict[str, int]:
    """source='sample'인 시세와 ETF 마스터를 삭제한다(FK CASCADE로 시세부터)."""
    prices_result = await session.execute(delete(PriceDaily).where(PriceDaily.source == "sample"))
    etf_result = await session.execute(delete(EtfMaster).where(EtfMaster.source == "sample"))
    return {
        "deleted_prices": prices_result.rowcount,
        "deleted_etfs": etf_result.rowcount,
    }


async def load(session: AsyncSession, csv_path: Path = REAL_DIR / "etf_master.csv") -> dict:
    """CSV → 검증 → 샘플 삭제 → 적재. 검증 실패 시 ValueError, 적재 중단."""
    raw = load_csv(csv_path)
    rows = validate(raw)

    deleted = await delete_samples(session)
    upserted = await etf_repo.upsert_etfs(session, rows)
    await session.commit()
    cache.clear_all()

    return {**deleted, "etf_master": upserted}


async def run(
    maker: async_sessionmaker[AsyncSession], csv_path: Path = REAL_DIR / "etf_master.csv"
) -> dict:
    async with maker() as session:
        return await load(session, csv_path)

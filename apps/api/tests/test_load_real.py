"""실데이터 CSV 검증 테스트(mock만, 실제 DB·API 없음)."""

import textwrap
from io import StringIO
from unittest.mock import AsyncMock

import pytest

from jobs.load_real import delete_samples, validate


def _rows_from_csv(text: str) -> list[dict[str, str]]:
    """CSV 텍스트를 DictReader처럼 파싱."""
    import csv

    return list(csv.DictReader(StringIO(textwrap.dedent(text).strip())))


_VALID_ROW = (
    "ticker,name,aliases,issuer,underlying_index,total_expense_ratio,"
    "actual_expense_ratio,actual_expense_as_of,distribution_cycle,currency_hedged,"
    "net_assets,net_assets_as_of,category,listed_date,"
    "fee_source,actual_expense_source,net_assets_source,checked_date\n"
    "133690,TIGER 미국나스닥100,,미래에셋자산운용,NASDAQ 100,0.0068,"
    '0.1430,2026-10-30,"분기(1·4·7·10월)",환노출,'
    "11695422000000,2026-10-30,해외 주식 시장대표,2010-10-18,"
    "금투협,금투협,미래에셋,2026-11-18"
)


def test_valid_row_passes():
    rows = _rows_from_csv(_VALID_ROW)
    result = validate(rows)
    assert len(result) == 1
    assert result[0]["ticker"] == "133690"
    assert result[0]["source"] == "manual_csv"


def test_missing_required_field_raises():
    csv_text = _VALID_ROW.replace("미래에셋자산운용", "")
    rows = _rows_from_csv(csv_text)
    with pytest.raises(ValueError, match="issuer"):
        validate(rows)


def test_negative_fee_raises():
    csv_text = _VALID_ROW.replace("0.0068", "-0.01")
    rows = _rows_from_csv(csv_text)
    with pytest.raises(ValueError, match="음수"):
        validate(rows)


def test_negative_actual_expense_raises():
    csv_text = _VALID_ROW.replace("0.1430", "-0.05")
    rows = _rows_from_csv(csv_text)
    with pytest.raises(ValueError, match="음수"):
        validate(rows)


def test_empty_csv_raises():
    with pytest.raises(ValueError, match="데이터 행이 없습니다"):
        validate([])


def test_stale_expense_date_warns():
    csv_text = _VALID_ROW.replace("2026-10-30", "2024-01-01")
    rows = _rows_from_csv(csv_text)
    with pytest.warns(UserWarning, match="1년 넘게"):
        validate(rows)


def test_missing_net_assets_raises():
    # net_assets 값을 비우면 필수 항목 누락
    csv_text = _VALID_ROW.replace("11695422000000", "")
    rows = _rows_from_csv(csv_text)
    with pytest.raises(ValueError, match="net_assets"):
        validate(rows)


def test_missing_distribution_cycle_raises():
    csv_text = _VALID_ROW.replace("분기(1·4·7·10월)", "")
    rows = _rows_from_csv(csv_text)
    with pytest.raises(ValueError, match="distribution_cycle"):
        validate(rows)


async def test_delete_samples_includes_disclosures():
    """delete_samples가 공시·시세·ETF 마스터를 모두 삭제하고 결과에 포함하는지 확인."""
    mock_result = AsyncMock()
    mock_result.rowcount = 3

    session = AsyncMock()
    session.execute = AsyncMock(return_value=mock_result)

    result = await delete_samples(session)

    assert session.execute.call_count == 3
    assert "deleted_disclosures" in result
    assert "deleted_prices" in result
    assert "deleted_etfs" in result

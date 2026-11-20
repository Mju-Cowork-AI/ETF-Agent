"""etf_master: 실부담비용·분배주기·환헤지·순자산·항목별 출처·점검일

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-20

실데이터 파이프라인(수동 CSV)이 쓰는 컬럼. 팀 규칙: 모든 값에 출처·수집일·항목별 기준일.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("etf_master", sa.Column("actual_expense_ratio", sa.Numeric(6, 4)))
    op.add_column("etf_master", sa.Column("actual_expense_as_of", sa.Date()))
    op.add_column("etf_master", sa.Column("distribution_cycle", sa.Text()))
    op.add_column("etf_master", sa.Column("currency_hedged", sa.Text()))
    op.add_column("etf_master", sa.Column("net_assets", sa.BigInteger()))
    op.add_column("etf_master", sa.Column("net_assets_as_of", sa.Date()))
    op.add_column("etf_master", sa.Column("fee_source", sa.Text()))
    op.add_column("etf_master", sa.Column("actual_expense_source", sa.Text()))
    op.add_column("etf_master", sa.Column("net_assets_source", sa.Text()))
    op.add_column("etf_master", sa.Column("checked_date", sa.Date()))


def downgrade() -> None:
    op.drop_column("etf_master", "checked_date")
    op.drop_column("etf_master", "net_assets_source")
    op.drop_column("etf_master", "actual_expense_source")
    op.drop_column("etf_master", "fee_source")
    op.drop_column("etf_master", "net_assets_as_of")
    op.drop_column("etf_master", "net_assets")
    op.drop_column("etf_master", "currency_hedged")
    op.drop_column("etf_master", "distribution_cycle")
    op.drop_column("etf_master", "actual_expense_as_of")
    op.drop_column("etf_master", "actual_expense_ratio")

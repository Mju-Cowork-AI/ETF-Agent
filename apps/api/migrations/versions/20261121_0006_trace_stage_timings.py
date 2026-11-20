"""traces: 단계별 소요 시간(stage_timings)

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-21

요청 1건의 단계별 시간 목록([{"stage": 단계 이름, "ms": 밀리초}, …])을 실행 순서대로 둔다.
이 열이 생기기 전의 행은 빈 목록이다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006"
down_revision: str | Sequence[str] | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "traces",
        sa.Column("stage_timings", JSONB(), server_default="[]", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("traces", "stage_timings")

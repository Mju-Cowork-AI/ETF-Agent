"""daily_question_counts: 서비스 전체의 하루(KST) 질문 수(하루 질문 상한, D13)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-20

날짜마다 1행. 상한 기록이 API 재시작·재배포 뒤에도 남도록 DB에 둔다.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | Sequence[str] | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_question_counts",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )


def downgrade() -> None:
    op.drop_table("daily_question_counts")

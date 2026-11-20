"""하루 질문 상한(D13)의 카운트. 서비스 전체 질문 수를 한국 시간 날짜별로 DB에 센다.

익명 사용자는 누구나 새로 받을 수 있어 사용자별이 아니라 서비스 전체로 센다.
"""

from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.models import DailyQuestionCount

# 한국 시간은 서머타임이 없어 고정 오프셋으로 쓴다(컨테이너의 시간대 데이터에 기대지 않는다).
KST = timezone(timedelta(hours=9))


def kst_today(now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(KST).date()


async def count_question(session: AsyncSession, *, day: date, limit: int) -> bool:
    """그날 질문 수를 1 올리고 True를 돌려준다. 이미 상한(limit)에 닿았으면 올리지 않고 False.

    한 문장(INSERT … ON CONFLICT DO UPDATE … WHERE count < limit)이라 동시 요청·여러 API
    인스턴스에서도 상한을 넘겨 세지 않는다.
    """
    stmt = (
        insert(DailyQuestionCount)
        .values(day=day, count=1)
        .on_conflict_do_update(
            index_elements=[DailyQuestionCount.day],
            set_={"count": DailyQuestionCount.count + 1, "updated_at": func.now()},
            where=DailyQuestionCount.count < limit,
        )
        .returning(DailyQuestionCount.count)
    )
    counted = (await session.execute(stmt)).scalar_one_or_none()
    await session.commit()
    return counted is not None

"""하루 질문 상한(D13): 서비스 전체 카운트, 넘으면 고정 안내 문구, DB에 남는 카운트. 외부 호출은 모두 fake."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import delete, func, select

from app.db import get_sessionmaker
from app.main import create_app
from app.repositories import usage as usage_repo
from app.repositories.models import Conversation, DailyQuestionCount, Message
from app.services import chat as chat_service
from app.services.chat import DAILY_LIMIT_MESSAGE, DAILY_LIMIT_VERDICT, ERROR_MESSAGE
from app.settings import Settings
from tests.conftest import login
from tests.sse import answer_text, parse_sse


@pytest.fixture(autouse=True)
async def _empty_counts() -> AsyncIterator[None]:
    """카운트는 서비스 전체 값이라 테스트마다 비운다."""
    async with get_sessionmaker()() as session:
        await session.execute(delete(DailyQuestionCount))
        await session.commit()
    yield


def _set_limit(app: FastAPI, limit: int) -> None:
    c = app.state.container
    c.settings = c.settings.model_copy(update={"daily_question_limit": limit})


async def _ask(client: AsyncClient, headers: dict[str, str], **body: Any) -> list[tuple[str, dict]]:
    resp = await client.post("/chat", json={"message": "ETF가 뭐야?", **body}, headers=headers)
    assert resp.status_code == 200, resp.text
    return parse_sse(resp.text)


async def _count(day: date | None = None) -> int | None:
    async with get_sessionmaker()() as session:
        return await session.scalar(
            select(DailyQuestionCount.count).where(
                DailyQuestionCount.day == (day or usage_repo.kst_today())
            )
        )


async def _rows(model: type) -> int:
    async with get_sessionmaker()() as session:
        return await session.scalar(select(func.count()).select_from(model)) or 0


def _is_limit_notice(events: list[tuple[str, dict]]) -> bool:
    return answer_text(events) == DAILY_LIMIT_MESSAGE


# ---------- 카운트 ----------


def test_kst_today_uses_korea_date() -> None:
    """UTC 15:00은 한국 시간으로 다음 날 0시다."""
    assert usage_repo.kst_today(datetime(2026, 11, 20, 14, 59, tzinfo=UTC)) == date(2026, 11, 20)
    assert usage_repo.kst_today(datetime(2026, 11, 20, 15, 0, tzinfo=UTC)) == date(2026, 11, 21)


async def test_count_question_stops_at_limit() -> None:
    day = date(2026, 1, 1)
    async with get_sessionmaker()() as session:
        results = [await usage_repo.count_question(session, day=day, limit=2) for _ in range(4)]
    assert results == [True, True, False, False]
    assert await _count(day) == 2  # 상한을 넘은 요청은 세지 않는다


async def test_count_question_is_atomic_under_concurrency() -> None:
    day = date(2026, 1, 2)

    async def one() -> bool:
        async with get_sessionmaker()() as session:
            return await usage_repo.count_question(session, day=day, limit=5)

    results = await asyncio.gather(*(one() for _ in range(12)))
    assert sum(results) == 5
    assert await _count(day) == 5


# ---------- /chat ----------


async def test_limit_is_off_by_default(client: AsyncClient, user_headers: dict[str, str]) -> None:
    """기본값(DAILY_QUESTION_LIMIT=0)에서는 세지 않고 지금 동작 그대로다."""
    events = await _ask(client, user_headers)
    assert events[-1][0] == "done" and not _is_limit_notice(events)
    assert await _count() is None


async def test_questions_under_limit_are_answered_and_counted(
    client: AsyncClient, app: FastAPI, user_headers: dict[str, str]
) -> None:
    _set_limit(app, 2)
    for _ in range(2):
        events = await _ask(client, user_headers)
        assert events[-1][0] == "done" and not _is_limit_notice(events)
        assert events[-1][1]["guard"]["verdict"] != DAILY_LIMIT_VERDICT
    assert await _count() == 2


async def test_over_limit_returns_fixed_notice_without_llm(
    client: AsyncClient,
    app: FastAPI,
    user_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_limit(app, 1)
    first = await _ask(client, user_headers)
    conv_id = first[-1][1]["conversation_id"]
    conversations, messages = await _rows(Conversation), await _rows(Message)

    async def _must_not_run(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("상한을 넘은 질문은 그래프(LLM)를 부르면 안 된다")

    monkeypatch.setattr(chat_service, "run_graph", _must_not_run)

    events = await _ask(client, user_headers)
    assert [e for e, _ in events] == ["token"] * (len(events) - 2) + ["sources", "done"]
    assert _is_limit_notice(events)
    done = events[-1][1]
    assert done["guard"] == {"verdict": DAILY_LIMIT_VERDICT, "reasons": []}
    assert done["conversation_id"] is None and done["message_id"] is None
    assert events[-2][1] == {"sources": []}

    # 이어 묻던 대화가 있으면 그 id를 돌려준다(웹이 대화를 잃지 않게)
    again = await _ask(client, user_headers, conversation_id=conv_id)
    assert _is_limit_notice(again) and again[-1][1]["conversation_id"] == conv_id

    # 대화·메시지를 새로 저장하지 않고, 카운트도 상한에서 멈춘다
    assert await _rows(Conversation) == conversations and await _rows(Message) == messages
    assert await _count() == 1


async def test_limit_is_service_wide_not_per_user(client: AsyncClient, app: FastAPI) -> None:
    """익명 ID는 누구나 새로 받을 수 있어 사용자별이 아니라 서비스 전체로 센다."""
    _set_limit(app, 1)
    a = await login(client, "limit-a@local.test")
    b = await login(client, "limit-b@local.test")
    assert not _is_limit_notice(await _ask(client, a))
    assert _is_limit_notice(await _ask(client, b))


async def test_count_survives_restart(
    client: AsyncClient, app: FastAPI, settings: Settings, user_headers: dict[str, str]
) -> None:
    """카운트는 DB에 있다. 새로 만든 앱(재시작)도 같은 날에는 상한에 닿은 상태다."""
    _set_limit(app, 1)
    assert not _is_limit_notice(await _ask(client, user_headers))

    restarted = create_app(settings.model_copy(update={"daily_question_limit": 1}))
    async with AsyncClient(transport=ASGITransport(app=restarted), base_url="http://test") as c2:
        assert _is_limit_notice(await _ask(c2, user_headers))


async def test_limit_resets_on_next_korea_day(
    client: AsyncClient,
    app: FastAPI,
    user_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _set_limit(app, 1)
    assert not _is_limit_notice(await _ask(client, user_headers))
    assert _is_limit_notice(await _ask(client, user_headers))

    tomorrow = usage_repo.kst_today() + timedelta(days=1)
    monkeypatch.setattr(usage_repo, "kst_today", lambda: tomorrow)
    assert not _is_limit_notice(await _ask(client, user_headers))
    assert await _count(tomorrow) == 1


async def test_count_failure_does_not_answer(
    client: AsyncClient,
    app: FastAPI,
    user_headers: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """질문 수를 세지 못하면 답하지 않는다(상한 없이 LLM을 부르지 않게)."""
    _set_limit(app, 5)

    async def _broken(*args: Any, **kwargs: Any) -> bool:
        raise RuntimeError("db down")

    async def _must_not_run(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("세지 못한 질문은 그래프(LLM)를 부르면 안 된다")

    monkeypatch.setattr(usage_repo, "count_question", _broken)
    monkeypatch.setattr(chat_service, "run_graph", _must_not_run)
    events = await _ask(client, user_headers)
    assert [e for e, _ in events] == ["error"]
    assert events[0][1]["message"] == ERROR_MESSAGE


# ---------- 설정 ----------

DB_URL = "postgresql+asyncpg://u:p@localhost:5432/db"


def test_daily_limit_setting(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("DATABASE_URL", DB_URL)
    assert Settings(_env_file=None).daily_question_limit == 0  # type: ignore[call-arg]
    clean_env.setenv("DAILY_QUESTION_LIMIT", "200")
    assert Settings(_env_file=None).daily_question_limit == 200  # type: ignore[call-arg]
    clean_env.setenv("DAILY_QUESTION_LIMIT", "-1")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]

"""트레이스의 단계별 소요 시간(stage_timings)."""

import time

from httpx import AsyncClient
from sqlalchemy import select

from app.db import get_sessionmaker
from app.observability.stages import PREPARE_STAGE, StageTimer
from app.repositories.models import Trace
from tests.sse import parse_sse


def test_timer_records_stages_in_order() -> None:
    timer = StageTimer(time.perf_counter())
    timer.mark("orchestrate")
    timer.mark("compose")
    timings = timer.stop()
    assert [t["stage"] for t in timings] == [PREPARE_STAGE, "orchestrate", "compose"]
    assert all(isinstance(t["ms"], int) and t["ms"] >= 0 for t in timings)


def test_timer_keeps_repeated_stages_separate() -> None:
    timer = StageTimer(time.perf_counter())
    for stage in ("compose", "guard", "retry", "compose", "guard"):
        timer.mark(stage)
    stages = [t["stage"] for t in timer.stop()]
    assert stages == [PREPARE_STAGE, "compose", "guard", "retry", "compose", "guard"]


def test_timer_measures_until_the_next_stage() -> None:
    timer = StageTimer(time.perf_counter() - 0.05)  # 50ms 전에 시작한 요청
    timer.mark("orchestrate")
    timings = timer.stop()
    assert timings[0] == {"stage": PREPARE_STAGE, "ms": timings[0]["ms"]}
    assert timings[0]["ms"] >= 50


def test_timer_stop_twice_adds_nothing() -> None:
    timer = StageTimer(time.perf_counter())
    first = timer.stop()
    assert timer.stop() == first


async def test_trace_stores_stage_timings(client: AsyncClient, user_headers: dict) -> None:
    resp = await client.post("/chat", json={"message": "분배금이 뭐야?"}, headers=user_headers)
    done = parse_sse(resp.text)[-1][1]
    async with get_sessionmaker()() as s:
        trace = await s.scalar(select(Trace).where(Trace.request_id == done["request_id"]))
    assert trace is not None
    stages = [t["stage"] for t in trace.stage_timings]
    assert stages[0] == PREPARE_STAGE
    # 질문 유형 파악 → 생성 → 검증 순서로 남는다(사이에 검색 단계가 낀다).
    assert stages.index("orchestrate") < stages.index("compose") < stages.index("guard")
    # 단계 이름과 시간만 있다.
    assert all(set(t) == {"stage", "ms"} for t in trace.stage_timings)
    # 단계 시간의 합은 전체 시간을 넘지 않는다(전체에는 답변 저장 전까지가 들어간다).
    assert sum(t["ms"] for t in trace.stage_timings) <= trace.latency_ms


async def test_admin_traces_show_stage_timings(
    client: AsyncClient, user_headers: dict, admin_headers: dict
) -> None:
    resp = await client.post("/chat", json={"message": "분배금이 뭐야?"}, headers=user_headers)
    rid = parse_sse(resp.text)[-1][1]["request_id"]
    page = (await client.get("/admin/traces", headers=admin_headers)).json()
    item = next(t for t in page["items"] if t["request_id"] == rid)
    assert item["stage_timings"][0]["stage"] == PREPARE_STAGE
    assert all(isinstance(t["ms"], int) for t in item["stage_timings"])

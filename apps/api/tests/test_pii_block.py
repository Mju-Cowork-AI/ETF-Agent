"""외부 호출 전 개인정보 차단(P1-AG-06): 전처리에서 원문으로 검사 → template, LLM·임베딩 0회."""

import json
import re
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.agents import graph
from app.agents.graph import run_graph
from app.agents.guard.templates import template_answer
from app.agents.state import AgentDeps
from app.db import get_sessionmaker
from app.llm.fake import FakeEmbedder, FakeLLM
from app.privacy import find_pii, find_pii_to_block, mask_pii
from app.repositories.models import Conversation, Message, Trace
from app.services.chat import PII_BLOCKED_MESSAGE
from app.settings import Settings
from tests.sse import parse_sse

_DATA = json.loads((Path(__file__).parent / "fixtures" / "pii_cases.json").read_text("utf-8"))
CASES: list[dict[str, Any]] = _DATA["cases"]
BLOCK = [c for c in CASES if c["expect_blocked"]]
ALLOW = [c for c in CASES if not c["expect_blocked"]]


def _ids(case: dict[str, Any]) -> str:
    return f"{case['id']}-{case['category']}"


class CountingEmbedder(FakeEmbedder):
    def __init__(self, *, dim: int) -> None:
        super().__init__(dim=dim)
        self.calls = 0

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        return await super().embed(texts)


@pytest.fixture
def embedder(settings: Settings) -> CountingEmbedder:
    return CountingEmbedder(dim=settings.embedding_dim)


@pytest.fixture
def counted(deps: AgentDeps, embedder: CountingEmbedder) -> AgentDeps:
    return replace(deps, embedder=embedder)


# ---------- 패턴 ----------
def test_fixture_counts() -> None:
    assert (len(BLOCK), len(ALLOW)) == (23, 19)


@pytest.mark.parametrize("case", CASES, ids=_ids)
def test_fixture_case(case: dict[str, Any]) -> None:
    assert bool(find_pii_to_block(case["text"])) is case["expect_blocked"]


def _luhn_digit(body: str) -> str:
    total = 0
    for i, ch in enumerate(reversed(body)):
        d = int(ch)
        if i % 2 == 0:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return str((10 - total % 10) % 10)


def test_bare_card_needs_luhn_or_card_word() -> None:
    # 0000으로 시작하는 발급사는 없다(가상 값). 검사 숫자만 맞춰 Luhn을 통과시킨다.
    valid = "000012345678903" + _luhn_digit("000012345678903")
    assert find_pii_to_block(f"{valid} 로 결제해줘") == ["CARD"]
    invalid = "9410876532104589"  # Luhn 실패(pii_cases p10)
    assert find_pii_to_block(f"주문번호 {invalid} 확인해줘") == []
    assert find_pii_to_block(f"{invalid} 카드로 자동이체") == ["CARD"]


@pytest.mark.parametrize(
    "text",
    [
        "계좌에 1234567890원 넣으면 총보수는?",  # 금액
        "계좌 평가금액 12345678901주 기준",  # 수량
        "연금계좌로 KR7069500007 사도 돼?",  # ISIN
        "계좌로 069500 2024년 분배금 받았어",  # 종목코드 + 연도
        "1234567890 이라는 숫자만 있는 질문",  # '계좌' 단어 없음
    ],
)
def test_bare_account_exceptions(text: str) -> None:
    assert "ACCOUNT" not in find_pii_to_block(text)


def test_bare_account_near_word() -> None:
    assert find_pii_to_block("계좌번호 00045678901234 로 조회해줘") == ["ACCOUNT"]
    assert find_pii_to_block("0004567890123 이 제 계좌예요") == ["ACCOUNT"]


def test_email_found_in_raw_not_normalized() -> None:
    raw = "제 메일 etf_lover99@example.org 로 보내줘"
    assert find_pii_to_block(raw) == ["EMAIL"]
    assert find_pii_to_block(graph.normalize(raw)) == []  # 정규화가 '@'·'_'를 지운다


def test_mask_pii_unchanged_for_new_block_patterns() -> None:
    """저장·트레이스용 mask_pii·find_pii는 이번 보완 패턴을 쓰지 않는다(동작 그대로)."""
    for text in ("9410876532104589 카드로 자동이체 걸어 줘", "계좌번호 00045678901234 로 조회해줘"):
        assert find_pii(text) == []
        assert mask_pii(text) == text


# ---------- 그래프 ----------
@pytest.mark.parametrize("case", BLOCK, ids=_ids)
async def test_blocked_before_llm_and_embedding(
    case: dict[str, Any], counted: AgentDeps, fake_llm: FakeLLM, embedder: CountingEmbedder
) -> None:
    st = await run_graph(counted, request_id="test", query=case["text"])
    assert st["intents"] == ["pii"]
    assert st["verdict"] == "template"
    assert st["agents_called"] == ["template:pii"]
    assert st["answer"] == template_answer("pii_blocked", counted.settings.inquiry_channel)
    assert fake_llm.calls == []  # 분류·합성·검증 모두 0회
    assert embedder.calls == 0  # 문서 검색(_prefetch) 0회
    reasons = st["guard_history"][0]
    assert reasons and all(r.startswith("pii:") for r in reasons)


@pytest.mark.parametrize("case", ALLOW, ids=_ids)
async def test_allowed_goes_to_classification(
    case: dict[str, Any], counted: AgentDeps, fake_llm: FakeLLM
) -> None:
    st = await run_graph(counted, request_id="test", query=case["text"])
    assert "pii" not in st["intents"]
    assert not st.get("pii_kinds")
    assert fake_llm.count("classify") == 1  # 기존 흐름대로 분류로 넘어감


def test_pii_template_follows_existing_format() -> None:
    text = template_answer("pii_blocked", "고객센터")
    assert text.startswith("개인정보(주민등록번호, 카드번호, 계좌번호, 전화번호, 이메일 등)")
    assert text.rstrip().endswith("다시 질문해 주세요.")


# ---------- 로그·트레이스 ----------
class _RecordingLog:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    def _rec(self, event: str, **kw: Any) -> None:
        self.events.append((event, kw))

    info = warning = error = debug = exception = _rec


async def test_log_has_kinds_only(counted: AgentDeps, monkeypatch: pytest.MonkeyPatch) -> None:
    rec = _RecordingLog()
    monkeypatch.setattr(graph, "log", rec)
    await run_graph(counted, request_id="req-1", query="9410876532104589 카드로 자동이체 걸어 줘")
    assert ("pii_blocked", {"request_id": "req-1", "kinds": ["CARD"]}) in rec.events
    assert "9410876532104589" not in repr(rec.events)


async def test_trace_has_kinds_only(client: AsyncClient, user_headers: dict) -> None:
    raw = "계좌번호 00045678901234 로 조회해줘 zz-pii-marker"
    resp = await client.post("/chat", json={"message": raw}, headers=user_headers)
    events = parse_sse(resp.text)
    done = events[-1][1]
    assert done["intents"] == ["pii"]
    assert done["guard"] == {"verdict": "template", "reasons": ["pii:ACCOUNT"]}
    async with get_sessionmaker()() as s:
        trace = await s.scalar(select(Trace).where(Trace.request_id == done["request_id"]))
    assert trace is not None
    assert (trace.intent, trace.guard_verdict, trace.model) == ("pii", "template", "template")
    assert trace.guard_reasons == ["pii:ACCOUNT"]
    assert trace.retrieved_doc_ids == []
    for col in Trace.__table__.columns:
        value = str(getattr(trace, col.key))
        assert "00045678901234" not in value
        assert "zz-pii-marker" not in value


# ---------- 저장 ----------
_DIGITS = re.compile(r"\d{4,}")  # 원문의 4자리 이상 숫자 덩어리(번호 일부)
_LOCAL = re.compile(r"[A-Za-z0-9._%+-]+(?=@)")  # 이메일 아이디


def _secrets(text: str) -> list[str]:
    return _DIGITS.findall(text) + _LOCAL.findall(text)


@pytest.mark.parametrize(
    "case", BLOCK, ids=_ids
)  # p10(구분자 없는 카드)·p21(하이픈 없는 계좌) 포함
async def test_blocked_question_stored_as_placeholder(
    case: dict[str, Any], client: AsyncClient, user_headers: dict
) -> None:
    resp = await client.post("/chat", json={"message": case["text"]}, headers=user_headers)
    done = parse_sse(resp.text)[-1][1]
    assert done["intents"] == ["pii"]
    conv_id = uuid.UUID(done["conversation_id"])
    async with get_sessionmaker()() as s:
        conv = await s.get(Conversation, conv_id)
        msgs = list(await s.scalars(select(Message).where(Message.conversation_id == conv_id)))
    assert conv is not None and conv.title == PII_BLOCKED_MESSAGE
    user_msgs = [m for m in msgs if m.role == "user"]
    assert [m.content for m in user_msgs] == [PII_BLOCKED_MESSAGE]
    secrets = _secrets(case["text"])
    assert secrets  # 케이스마다 확인할 값이 있다
    stored = [conv.title, *(m.content for m in msgs), *(str(m.meta) for m in msgs)]
    for value in stored:
        for secret in secrets:
            assert secret not in value


async def test_allowed_question_stored_as_is(client: AsyncClient, user_headers: dict) -> None:
    text = "069500 2024년 분배금 알려줘"
    resp = await client.post("/chat", json={"message": text}, headers=user_headers)
    done = parse_sse(resp.text)[-1][1]
    conv_id = uuid.UUID(done["conversation_id"])
    async with get_sessionmaker()() as s:
        msgs = list(await s.scalars(select(Message).where(Message.conversation_id == conv_id)))
    assert [m.content for m in msgs if m.role == "user"] == [text]

"""그래프 상태와 공용 자료형."""

import operator
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Annotated, Any, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.llm.base import Embedder, LLMClient
from app.settings import Settings


class Intent(StrEnum):
    ETF_INFO = "etf_info"
    FAQ = "faq"
    DISCLOSURE = "disclosure"
    HIGH_RISK = "high_risk"
    RECOMMENDATION = "recommendation"
    OUT_OF_SCOPE = "out_of_scope"
    # 해킹·불법 행위 방법 요청, 지침 무력화(프롬프트 인젝션) 시도: 생성 없이 즉시 차단 # P1-AG-06
    BLOCKED = "blocked"
    # 질문에 개인정보: 외부 호출(분류 LLM·임베딩) 전에 전처리에서 막는다. 분류 대상이 아니다.
    PII = "pii"
    # 일반 대화(GENERAL_CHAT_ENABLED, 로컬 전용). 분류기가 내지 않고 오케스트레이터가 바꿔 넣는다.
    GENERAL = "general"


# 전문 에이전트가 처리하는 의도(나머지는 템플릿)
AGENT_INTENTS = (Intent.ETF_INFO, Intent.FAQ)
TEMPLATE_INTENTS = (
    Intent.PII,
    Intent.BLOCKED,
    Intent.HIGH_RISK,
    Intent.RECOMMENDATION,
    Intent.OUT_OF_SCOPE,
)


class Level(StrEnum):
    BEGINNER = "beginner"  # 입문
    INTERMEDIATE = "intermediate"  # 중급
    EXPERT = "expert"  # 숙련


class Verdict(StrEnum):
    PASS = "pass"  # noqa: S105 (판정 라벨)
    PASS_AFTER_RETRY = "pass_after_retry"  # noqa: S105
    BLOCKED = "blocked"  # 재생성 후에도 실패 → 안전 답변
    TEMPLATE = "template"  # 고위험·추천·범위 밖 고정 답변
    LLM_UNAVAILABLE = "llm_unavailable"  # LLM 실패, 폴백 없음 → 안전 답변


@dataclass(slots=True)
class EtfEntity:
    ticker: str
    name: str
    matched: str  # 질문에서 매칭된 표현(정규화)
    score: float
    method: str  # exact | ticker | fuzzy | context | plan | brand


@dataclass(slots=True)
class Source:
    title: str
    location: str | None = None
    url: str | None = None
    kind: str = "document"  # document | disclosure | etf_data
    doc_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "location": self.location,
            "url": self.url,
            "kind": self.kind,
            "doc_id": self.doc_id,
        }


@dataclass(slots=True)
class AgentResult:
    """수집 에이전트 결과. LLM은 부르지 않고, 답변 합성(compose)이 모아서 한 번에 쓴다. # P1-AG-02"""

    agent: str
    content: str  # 화면에 그대로 붙는 결정적 블록(DB 표·공시 목록·안내 문구). FAQ는 비움(캐시 적중 시 답변)
    sources: list[Source] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)  # 가드 근거 대조용 텍스트
    retrieved_ids: list[str] = field(default_factory=list)
    generated: bool = False  # LLM 생성 문장이 포함됐는지(검증 모델 대상)
    grounded: bool = (
        True  # False: 근거 없이 모델 일반 지식으로 답함(일반 대화) → 수치·근거 검증 생략
    )
    ok: bool = True
    error: str | None = None
    cache_key: str | None = None  # 가드 통과 시 캐시에 저장할 키(FAQ)
    # 의도와 별개로 이 결과의 데이터 때문에 붙여야 하는 고지 id(예: 샘플 상품 → sample_data)
    disclaimers: list[str] = field(default_factory=list)
    cached: bool = False
    found: bool = True  # 답에 쓸 자료를 찾았는지(False면 content는 안내 문구)
    skip_prose: bool = False  # 설명 문장(LLM) 없이 content만 낸다(시세 안내가 두 번 나오지 않게)
    # 부족 판정(docs/replan_spec.md)에 쓰는 신호. 값은 담지 않는다.
    zero_results: bool = False  # 조건 검색 결과 0건(조건을 못 알아들은 경우 포함)
    missing_fields: list[str] = field(
        default_factory=list
    )  # 계획한 항목 중 값이 없는 것("종목코드:항목")
    context: str = ""  # LLM 프롬프트에 넣을 자료 블록([ETF 데이터]·[공시]·[근거 N])


@dataclass(slots=True)
class GuardResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)
    judge: dict[str, Any] | None = None


Emit = Callable[[str, str], Awaitable[None]]


async def _noop_emit(stage: str, message: str) -> None:
    return None


@dataclass(slots=True)
class AgentDeps:
    settings: Settings
    llm: LLMClient
    embedder: Embedder
    maker: async_sessionmaker[AsyncSession]
    emit: Emit = _noop_emit


def merge_results(left: dict[str, AgentResult], right: dict[str, AgentResult]) -> dict:
    return {**(left or {}), **(right or {})}


class GraphState(TypedDict, total=False):
    request_id: str
    query: str  # 원문: 메모리 안에서만 쓰고 저장·로그·트레이스에 남기지 않는다
    normalized: str
    pii_kinds: list[str]  # 원문에서 찾은 개인정보 종류(값 없음). 있으면 분류 없이 template으로
    level: str
    history: list[dict[str, Any]]  # [{"role","content"(마스킹됨),"meta"}]
    context_tickers: list[str]  # 직전 턴 엔티티(멀티턴)
    entities: list[EtfEntity]
    unknown_etf: bool  # 브랜드는 있는데 데이터에 없는 상품 이름('KODEX 미국S&P500')
    intents: list[str]
    intent_source: str  # llm | rules
    plan: dict[str, Any]  # 계획 JSON 요약(interface.md). 질문 문장·검색어는 담지 않는다
    plan_conditions: dict[str, Any]  # 계획의 검색 조건(etf_search)
    refuse: list[str]  # 섞인 질문에서 답하지 않을 부분(high_risk·recommendation·out_of_scope)
    plan_tools: list[dict[str, Any]]  # 1차 계획의 도구(재계획에서 같은 도구·인자를 빼는 데 쓴다)
    plan_metrics: list[str]  # 1차 계획의 etf_info 항목(부족 판정 missing_field)
    replan_conditions: dict[str, Any]  # 재계획이 더한 검색 조건(빈 칸만 채운다)
    knowledge_query: str | None  # 재계획이 고른 문서 검색어
    sufficiency: dict[str, Any]  # 부족 판정 결과(interface.md 2장)
    replan_count: int  # 재계획 횟수(상한 1)
    replan_targets: list[str]  # 재계획 뒤 다시 부를 수집 노드
    results: Annotated[dict[str, AgentResult], merge_results]
    agents_called: Annotated[list[str], operator.add]
    attempt: int
    retry_feedback: list[str]
    prefetched_chunks: list[Any] | None  # 의도 분류와 동시에 미리 검색한 문서 청크(RetrievedChunk)
    body: str
    disclaimer_ids: list[str]
    sources: list[Source]
    evidence: list[str]
    generated: bool  # 답변에 LLM 생성 문장이 있는지(검증 모델 대상)
    grounded: bool  # False: 근거 없이 모델 일반 지식으로 답함
    cached: bool  # FAQ 캐시 적중
    cache_key: str | None  # 가드 통과 시 FAQ 캐시에 저장할 키
    guard: GuardResult
    guard_history: Annotated[list[list[str]], operator.add]
    verdict: str
    answer: str
    model: str
    fallback_used: bool

"""오케스트레이터: 의도 분류(LLM JSON → 실패 시 키워드 규칙)와 라우팅. # P1-AG-02"""

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from app.agents.orchestrator.rules import classify_rules, is_blocked, is_high_risk
from app.agents.prompts import load_text
from app.agents.state import AGENT_INTENTS, Intent
from app.llm.base import ChatMessage, LLMClient, LLMError
from app.logging import get_logger

log = get_logger(__name__)

# general·pii는 분류 대상이 아니다(pii는 전처리가 정한다)
_VALID = {i.value for i in Intent if i not in (Intent.GENERAL, Intent.PII)}
_JSON_RE = re.compile(r"\{.*\}", re.DOTALL)


def parse_intents(text: str) -> list[str] | None:
    """LLM 출력에서 {"intents": [...]}를 꺼낸다. 형식이 틀리면 None."""
    m = _JSON_RE.search(text or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    raw = data.get("intents") if isinstance(data, dict) else None
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return None
    intents = [str(x).strip().lower() for x in raw if str(x).strip().lower() in _VALID]
    return list(dict.fromkeys(intents)) or None


def finalize_intents(intents: list[str]) -> list[str]:
    """배타 의도 정리: 차단 > 고위험 > 추천 > 범위 밖. 전문 에이전트 의도는 순서 고정."""
    if Intent.BLOCKED in intents:
        return [Intent.BLOCKED.value]
    if Intent.HIGH_RISK in intents:
        return [Intent.HIGH_RISK.value]
    if Intent.RECOMMENDATION in intents:
        return [Intent.RECOMMENDATION.value]
    agents = [i.value for i in AGENT_INTENTS if i in intents]
    return agents or [Intent.OUT_OF_SCOPE.value]


# ---------- 계획 JSON(interface.md) ----------
# 답하지 않을 부분으로 refuse에 들어갈 수 있는 의도
REFUSABLE = (Intent.HIGH_RISK.value, Intent.RECOMMENDATION.value, Intent.OUT_OF_SCOPE.value)
# 도구 → 그 도구를 쓰는 수집 의도
TOOL_INTENT = {
    "etf_info": Intent.ETF_INFO.value,
    "etf_search": Intent.ETF_INFO.value,
    "knowledge": Intent.FAQ.value,
}
METRICS = frozenset(
    {
        "total_expense_ratio",
        "actual_expense_ratio",
        "net_assets",
        "distribution_cycle",
        "underlying_index",
        "issuer",
        "listed_date",
        "currency_hedged",
        "category",
    }
)
CONDITION_KEYS = frozenset(
    {
        "region",
        "category",
        "underlying_index",
        "max_fee",
        "min_fee",
        "sort",
        "sort_desc",
    }
)
CLARIFY_THRESHOLD = 0.6
PLAN_MAX_TOKENS = 400
RETRY_HINT = "위 출력은 형식이 잘못됐다. 설명 없이 지정한 JSON 객체 하나만 다시 출력하라."


@dataclass(slots=True)
class Plan:
    """계획 JSON을 검증·정리한 값. source는 llm | rules."""

    intents: list[str]
    source: str = "llm"
    refuse: list[str] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    answer_mode: str = "generate"
    confidence: float = 1.0
    needs_clarification: bool = False
    clarify_question: str | None = None

    def etf_codes(self) -> list[str]:
        codes: list[str] = []
        for t in self.tools:
            if t["name"] == "etf_info":
                codes += [c for c in t["args"].get("etf_codes", []) if c not in codes]
        return codes

    def conditions(self) -> dict[str, Any]:
        for t in self.tools:
            if t["name"] == "etf_search":
                return dict(t["args"].get("conditions", {}))
        return {}

    def summary(self) -> dict[str, Any]:
        """로그용: 질문 문장·검색어 없이 구조만."""
        return {
            "intents": self.intents,
            "refuse": self.refuse,
            "tools": [t["name"] for t in self.tools],
            "answer_mode": self.answer_mode,
            "confidence": self.confidence,
            "source": self.source,
        }


def _str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [str(x).strip() for x in value if str(x).strip()]


def _clean_tool(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("name") not in TOOL_INTENT:
        return None
    args = raw.get("args") if isinstance(raw.get("args"), dict) else {}
    name = raw["name"]
    if name == "etf_info":
        codes = [c for c in _str_list(args.get("etf_codes")) if re.fullmatch(r"\d{6}", c)]
        metrics = [m for m in _str_list(args.get("metrics")) if m in METRICS]
        return {"name": name, "args": {"etf_codes": codes[:3], "metrics": metrics}}
    if name == "etf_search":
        cond = args.get("conditions") if isinstance(args.get("conditions"), dict) else {}
        cond = {k: v for k, v in cond.items() if k in CONDITION_KEYS and v not in (None, "")}
        return {"name": name, "args": {"conditions": cond}}
    query = args.get("query")
    if not isinstance(query, str) or not query.strip():
        return None
    return {"name": name, "args": {"query": query.strip()[:200]}}


def parse_plan(text: str) -> Plan | None:
    """LLM 출력에서 계획 JSON을 꺼내 정리한다. 형식이 틀리면 None.

    예전 형식({"intents": [...]})도 받는다. 허용 밖 값은 빼고, 빠진 키는 기본값으로 채운다.
    """
    m = _JSON_RE.search(text or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    tools = [t for t in (_clean_tool(x) for x in data.get("tools") or []) if t]
    intents = [i.lower() for i in _str_list(data.get("intents")) if i.lower() in _VALID]
    # 의도를 빠뜨리고 도구만 적었으면 도구에서 의도를 채운다
    for t in tools:
        if (i := TOOL_INTENT[t["name"]]) not in intents:
            intents.append(i)
    refuse = [r.lower() for r in _str_list(data.get("refuse")) if r.lower() in REFUSABLE]
    if not intents and not refuse:
        return None
    try:
        confidence = min(max(float(data.get("confidence", 1.0)), 0.0), 1.0)
    except TypeError, ValueError:
        confidence = 1.0
    question = data.get("clarify_question")
    question = question.strip() if isinstance(question, str) and question.strip() else None
    needs = bool(data.get("needs_clarification")) or confidence < CLARIFY_THRESHOLD
    mode = data.get("answer_mode")
    return Plan(
        intents=list(dict.fromkeys(intents)),
        refuse=list(dict.fromkeys(refuse)),
        tools=tools,
        answer_mode=mode if mode in ("generate", "table") else "generate",
        confidence=confidence,
        needs_clarification=needs,
        clarify_question=question if needs else None,
    )


def finalize_plan(plan: Plan, text: str) -> Plan:
    """답할 의도(intents)와 거절할 부분(refuse)을 정리한다.

    - 차단이 있으면 차단만.
    - 사실 의도(etf_info·faq)와 판단·추천·범위 밖을 계획이 함께 적었으면 섞인 질문이다:
      사실만 답하고 나머지는 refuse로 거절 문장을 붙인다(decisions.md 'refuse 범위').
    - 사실 의도가 없으면 예전처럼 배타 의도 하나(고위험 > 추천 > 범위 밖).
    - 안전장치: 규칙이 고위험을 잡았는데 계획이 고위험을 명시하지 않았으면 고위험만(사실 요청이
      있는지 계획을 믿을 수 없으므로 예전 동작을 지킨다).
    """
    intents, refuse = list(plan.intents), list(plan.refuse)
    if Intent.BLOCKED in intents:
        return replace(plan, intents=[Intent.BLOCKED.value], refuse=[])
    facts = [i.value for i in AGENT_INTENTS if i in intents]
    risky = [r for r in REFUSABLE if r in intents or r in refuse]
    if is_high_risk(text) and Intent.HIGH_RISK not in risky:
        return replace(plan, intents=[Intent.HIGH_RISK.value], refuse=[])
    if facts and risky:
        return replace(plan, intents=facts, refuse=risky)
    if facts:
        return replace(plan, intents=facts, refuse=[])
    return replace(plan, intents=finalize_intents(risky), refuse=[])


async def plan(
    llm: LLMClient,
    text: str,
    *,
    has_entity: bool,
    history_hint: str = "",
    model: str | None = None,
) -> Plan:
    """계획 JSON 한 번(형식이 틀리면 1회 재시도) → 실패하면 키워드 규칙."""
    # 위험 요청은 규칙에 걸리는 즉시 차단한다(LLM을 부르지 않는다). # P1-AG-06
    if is_blocked(text):
        return Plan(intents=[Intent.BLOCKED.value], source="rules")
    user = f"{history_hint}\n질문: {text}" if history_hint else f"질문: {text}"
    messages = [ChatMessage("system", load_text("system/classifier.md")), ChatMessage("user", user)]
    parsed: Plan | None = None
    try:
        for attempt in range(2):
            resp = await llm.complete(
                messages,
                task="classify",
                model=model,
                json_mode=True,
                temperature=0,
                max_tokens=PLAN_MAX_TOKENS,
            )
            parsed = parse_plan(resp.text)
            if parsed is not None or attempt:
                break
            # 재시도: 메시지를 바꿔 보내야 응답 캐시에 같은 오답이 걸리지 않는다
            messages = [
                *messages,
                ChatMessage("assistant", resp.text[:500]),
                ChatMessage("user", RETRY_HINT),
            ]
    except LLMError as e:
        log.info("classify_llm_failed", error=type(e).__name__)
    if parsed is None:
        intents = classify_rules(text, has_entity=has_entity)
        # 규칙 경로는 예전처럼 배타 의도(섞인 질문 판단은 계획이 있을 때만)
        if is_high_risk(text):
            intents = [Intent.HIGH_RISK]
        return Plan(intents=finalize_intents([str(i) for i in intents]), source="rules")
    return finalize_plan(parsed, text)


async def classify(
    llm: LLMClient, text: str, *, has_entity: bool, history_hint: str = ""
) -> tuple[list[str], str]:
    """(의도 목록, 출처 'llm'|'rules'). 계획 JSON의 의도만 쓰는 예전 인터페이스."""
    p = await plan(llm, text, has_entity=has_entity, history_hint=history_hint)
    return p.intents, p.source

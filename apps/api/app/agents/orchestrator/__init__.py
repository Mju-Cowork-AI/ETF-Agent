"""오케스트레이터: 의도 분류(LLM JSON → 실패 시 키워드 규칙)와 라우팅. # P1-AG-02"""

import json
import re
from dataclasses import dataclass, field, replace
from typing import Any

from app.agents.etf_info import asks_price
from app.agents.orchestrator.rules import DISCLOSURE, classify_rules, is_blocked, is_high_risk
from app.agents.prompts import load_text
from app.agents.state import AGENT_INTENTS, Intent
from app.llm.base import ChatMessage, LLMClient, LLMError
from app.logging import get_logger

log = get_logger(__name__)

# general·pii는 분류 대상이 아니다(pii는 전처리가 정한다)
_VALID = {i.value for i in Intent if i not in (Intent.GENERAL, Intent.PII, Intent.DISCLOSURE)}
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

    def metrics(self) -> list[str]:
        out: list[str] = []
        for t in self.tools:
            if t["name"] == "etf_info":
                out += [m for m in t["args"].get("metrics", []) if m not in out]
        return out

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
      있는지 계획을 믿을 수 없으므로 예전 동작을 지킨다). 단, 계획이 범위 밖만 적었으면 그대로 둔다.
      범위 밖도 답하지 않는 고정 문구라 안전하고, ETF가 아닌 자산('비트코인 사야 할까?')은
      매수 판단 문구보다 범위 밖 안내가 맞다.
    """
    intents, refuse = list(plan.intents), list(plan.refuse)
    if Intent.BLOCKED in intents:
        return replace(plan, intents=[Intent.BLOCKED.value], refuse=[])
    facts = [i.value for i in AGENT_INTENTS if i in intents]
    risky = [r for r in REFUSABLE if r in intents or r in refuse]
    only_out_of_scope = not facts and risky == [Intent.OUT_OF_SCOPE]
    if is_high_risk(text) and Intent.HIGH_RISK not in risky and not only_out_of_scope:
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
    return _price_is_etf_info(finalize_plan(parsed, text), text, has_entity=has_entity)


def _price_is_etf_info(p: Plan, text: str, *, has_entity: bool) -> Plan:
    """특정 ETF의 시세 질문을 계획이 범위 밖으로 보내면 ETF 정보로 되돌린다.

    시세는 수집하지 않지만(범위 조정 2차) 질문 자체는 ETF 정보 질문이고, ETF 정보가
    '시세를 제공하지 않습니다' 안내를 붙인다(#35, grading.md 4-2). 공시·뉴스 낱말이 있으면 손대지 않는다.
    """
    if not has_entity or not asks_price(text) or any(r.search(text) for r in DISCLOSURE):
        return p
    oos = Intent.OUT_OF_SCOPE.value
    if oos not in p.intents and oos not in p.refuse:
        return p
    intents = [i for i in p.intents if i != oos] or [Intent.ETF_INFO.value]
    if intents != [Intent.ETF_INFO.value] and Intent.ETF_INFO.value not in intents:
        intents = [Intent.ETF_INFO.value, *intents]
    log.info("plan_price_override", intents=p.intents, refuse=p.refuse)
    return replace(p, intents=intents, refuse=[r for r in p.refuse if r != oos])


async def classify(
    llm: LLMClient, text: str, *, has_entity: bool, history_hint: str = ""
) -> tuple[list[str], str]:
    """(의도 목록, 출처 'llm'|'rules'). 계획 JSON의 의도만 쓰는 예전 인터페이스."""
    p = await plan(llm, text, has_entity=has_entity, history_hint=history_hint)
    return p.intents, p.source


# ---------- 재계획(docs/replan_spec.md, 최대 1회) ----------
REPLAN_HINT = (
    '[지시] 이미 모은 결과는 유지된다. 부족한 부분을 채울 "추가" 도구와 인자만 같은 JSON 형식으로 내라. '
    "intents는 1차와 같게 둔다. 더 수집할 방법이 없으면 tools를 빈 배열로 내라. "
    "사용자의 조건(보수 상한·하한, 지역 등)을 바꾸거나 완화하지 마라. 이전과 같은 도구·인자를 다시 내지 마라."
)


def same_tool(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a.get("name") == b.get("name") and a.get("args", {}) == b.get("args", {})


async def replan(
    llm: LLMClient,
    text: str,
    *,
    prev_tools: list[dict[str, Any]],
    prev_intents: list[str],
    collected: str,
    sufficiency: dict[str, Any],
    indexes: list[str],
    model: str | None = None,
) -> list[dict[str, Any]] | None:
    """부족 사유를 보고 추가 도구만 다시 계획한다. 형식이 두 번 틀리면 None(재계획 없이 진행).

    수집 값 자체는 보내지 않고 있음/없음만 요약한다(숫자 생성 여지 차단). 1차와 같은 도구·인자는 뺀다.
    """
    prev = json.dumps({"intents": prev_intents, "tools": prev_tools}, ensure_ascii=False)
    user = "\n".join(
        [
            f"질문: {text}",
            f"[이전 계획] {prev}",
            f"[수집 결과 요약] {collected}",
            f"[부족 사유] {json.dumps(sufficiency, ensure_ascii=False)}",
            f"[DB 기초지수 이름] {', '.join(indexes)}",
            REPLAN_HINT,
        ]
    )
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
            messages = [
                *messages,
                ChatMessage("assistant", resp.text[:500]),
                ChatMessage("user", RETRY_HINT),
            ]
    except LLMError as e:
        log.info("replan_llm_failed", error=type(e).__name__)
        return None
    if parsed is None:
        return None
    return [t for t in parsed.tools if not any(same_tool(t, p) for p in prev_tools)]

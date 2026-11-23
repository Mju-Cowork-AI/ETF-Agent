"""부족 판정(코드, LLM 0회). docs/replan_spec.md 2장, 범위 조정 3차(11-22).

재계획하는 부족은 두 가지뿐이다.
- zero_results: 조건 검색 결과 0건(조건을 알아듣지 못해 검색하지 못한 경우 포함)
- missing_field: 계획한 항목(metrics) 중 DB 값이 없는 것

ETF 이름 애매(unresolved_entity)·문서 점수 낮음(low_score)은 재계획하지 않고 바로 고정 문구로 끝난다
(ETF 정보의 '상품명을 알려 주세요' 안내, FAQ의 '제공된 자료로는 답하기 어렵습니다').
"""

from typing import Any

from app.agents.state import GraphState, Intent


def judge(state: GraphState) -> dict[str, Any]:
    reasons: list[dict[str, Any]] = []
    r = (state.get("results") or {}).get("etf_info")
    if r is not None and r.ok and Intent.ETF_INFO in (state.get("intents") or []):
        if r.zero_results:
            reasons.append(
                {
                    "type": "zero_results",
                    "tool": "etf_search",
                    "conditions": state.get("plan_conditions") or {},
                }
            )
        for item in r.missing_fields:
            code, _, name = item.partition(":")
            reasons.append({"type": "missing_field", "etf_code": code, "field": name})
    return {"sufficient": not reasons, "reasons": reasons}


def summarize(sufficiency: dict[str, Any]) -> str:
    """재계획 입력용 요약. 수집 값은 넣지 않고 무엇이 없었는지만 쓴다."""
    lines = []
    for r in sufficiency.get("reasons", []):
        if r["type"] == "zero_results":
            lines.append("etf_search: 결과 0건")
        elif r["type"] == "missing_field":
            lines.append(f"etf_info {r['etf_code']}: {r['field']} 없음")
    return "; ".join(lines) or "부족 없음"

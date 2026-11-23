"""재계획 루프(docs/replan_spec.md, 최대 1회). 범위 조정 3차: 결과 0건·항목 빠짐만 재계획."""

import json

import pytest

from app.agents import sufficiency
from app.agents.graph import route_sufficiency, run_graph
from app.agents.orchestrator import replan
from app.agents.state import AgentDeps, AgentResult
from app.llm.fake import FakeLLM


def _plan(intents: list[str], tools: list[dict] | None = None, **kw) -> str:
    base = {
        "intents": intents,
        "tools": tools or [],
        "answer_mode": "table",
        "refuse": [],
        "confidence": 0.9,
        "needs_clarification": False,
        "clarify_question": None,
    }
    return json.dumps({**base, **kw}, ensure_ascii=False)


def _ask(deps: AgentDeps, q: str):
    return run_graph(deps, request_id="t", query=q)


# 1. missing_field: 계획한 항목이 DB에 없음(샘플 DB는 실부담비용이 비어 있다) → 문서 검색 추가
async def test_missing_field_replans_with_knowledge(deps: AgentDeps, fake_llm: FakeLLM) -> None:
    fake_llm.push(
        "classify",
        _plan(
            ["etf_info"],
            [{"name": "etf_info", "args": {"etf_codes": [], "metrics": ["actual_expense_ratio"]}}],
        ),
    )
    fake_llm.push(
        "classify",
        _plan(["etf_info"], [{"name": "knowledge", "args": {"query": "실부담비용 뜻"}}]),
    )
    st = await _ask(deps, "샘플 코스피200 실부담비용 알려줘")
    assert st["sufficiency"]["reasons"][0] == {
        "type": "missing_field",
        "etf_code": "900010",
        "field": "actual_expense_ratio",
    }
    assert st["replan_count"] == 1
    assert "replan" in st["agents_called"] and "faq" in st["agents_called"]
    assert st["intents"] == ["etf_info", "faq"]
    assert fake_llm.count("classify") == 2  # 1차 계획 + 재계획
    assert "샘플 코스피200" in st["answer"]


# 2. zero_results: 조건을 DB 표기로 못 알아들음 → 재계획이 DB 기초지수 이름으로 다시 검색
async def test_zero_results_replans_with_db_index_name(deps: AgentDeps, fake_llm: FakeLLM) -> None:
    fake_llm.push(
        "classify", _plan(["etf_info"], [{"name": "etf_search", "args": {"conditions": {}}}])
    )
    fake_llm.push(
        "classify",
        _plan(
            ["etf_info"],
            [{"name": "etf_search", "args": {"conditions": {"underlying_index": "NASDAQ-100"}}}],
        ),
    )
    st = await _ask(deps, "나스닥 추종하는 상품들 목록 보여줘")
    # 1차: 조건을 못 알아들어 0건 → 재계획 → 2차 검색 뒤에는 충분
    assert st["agents_called"].count("etf_info") == 2 and "replan" in st["agents_called"]
    assert st["sufficiency"]["sufficient"] is True
    assert st["replan_count"] == 1
    assert "샘플 미국나스닥100" in st["answer"]
    assert st["verdict"] == "pass", st.get("guard_reasons")


# 3. zero_results: 정말 없음 → 재계획이 빈 tools → 고정 문구. 조건 완화 없음, 3차 계획 없음
@pytest.mark.parametrize(
    "replan_tools",
    [[], [{"name": "etf_search", "args": {"conditions": {"max_fee": 0.5}}}]],
    ids=["no_more_tools", "relaxing_is_ignored"],
)
async def test_zero_results_without_way_ends_with_fixed_text(
    deps: AgentDeps, fake_llm: FakeLLM, replan_tools: list[dict]
) -> None:
    fake_llm.push(
        "classify",
        _plan(["etf_info"], [{"name": "etf_search", "args": {"conditions": {"max_fee": 0.001}}}]),
    )
    fake_llm.push("classify", _plan(["etf_info"], replan_tools))
    st = await _ask(deps, "총보수 0.001% 이하 ETF 찾아줘")
    assert fake_llm.count("classify") == 2
    assert st["replan_count"] == 1
    assert "에 맞는 ETF가 없습니다" in st["answer"]
    # 사용자가 정한 보수 상한(0.001%)을 재계획이 0.5%로 넓히지 못한다
    assert "샘플" not in st["body"]


# 4. ETF 이름이 애매한 질문은 재계획하지 않고 바로 안내 문구(범위 조정 3차)
async def test_unclear_etf_name_does_not_replan(deps: AgentDeps, fake_llm: FakeLLM) -> None:
    fake_llm.push(
        "classify",
        _plan(["etf_info"], [{"name": "etf_info", "args": {"etf_codes": [], "metrics": []}}]),
    )
    st = await _ask(deps, "그 나슥닥 거 보수 얼마야")
    assert st["sufficiency"]["sufficient"] is True
    assert "replan" not in st["agents_called"]
    assert fake_llm.count("classify") == 1
    assert "상품명이나 종목코드" in st["answer"]


# 5. 회귀: 충분하면 재계획 없음. 고정 문구 의도도 재계획 없음
async def test_sufficient_question_does_not_replan(deps: AgentDeps, fake_llm: FakeLLM) -> None:
    fake_llm.push(
        "classify",
        _plan(
            ["etf_info"],
            [{"name": "etf_info", "args": {"etf_codes": [], "metrics": ["total_expense_ratio"]}}],
        ),
    )
    st = await _ask(deps, "샘플 코스피200 총보수 알려줘")
    assert st["sufficiency"] == {"sufficient": True, "reasons": []}
    assert "replan" not in st["agents_called"] and st["replan_count"] == 0
    assert fake_llm.count("classify") == 1

    fake_llm.push("classify", _plan(["high_risk"]))
    st = await _ask(deps, "샘플 코스피200 지금 사야 할까?")
    assert st["verdict"] == "template" and "replan" not in st["agents_called"]


# 6. 재계획이 1차와 같은 도구·인자를 내면 코드가 빼고 모은 자료로 끝낸다
async def test_same_tool_again_is_dropped(deps: AgentDeps, fake_llm: FakeLLM) -> None:
    tool = {"name": "etf_search", "args": {"conditions": {"max_fee": 0.001}}}
    fake_llm.push("classify", _plan(["etf_info"], [tool]))
    fake_llm.push("classify", _plan(["etf_info"], [tool]))
    st = await _ask(deps, "총보수 0.001% 이하 ETF 찾아줘")
    assert st["replan_targets"] == []
    assert st["agents_called"].count("etf_info") == 1  # 같은 검색을 다시 돌리지 않았다
    assert fake_llm.count("classify") == 2


# ---------- 단위 ----------
def test_low_score_and_doc_miss_are_not_replan_reasons() -> None:
    state = {
        "intents": ["faq"],
        "results": {"faq": AgentResult(agent="faq", content="", found=False)},
    }
    assert sufficiency.judge(state) == {"sufficient": True, "reasons": []}


def test_rules_plan_does_not_replan() -> None:
    insufficient = {"sufficient": False, "reasons": [{"type": "zero_results"}]}
    base = {"sufficiency": insufficient, "replan_count": 0}
    assert route_sufficiency({**base, "intent_source": "llm"}) == "replan"
    assert route_sufficiency({**base, "intent_source": "rules"}) == "compose"
    assert route_sufficiency({**base, "intent_source": "llm", "replan_count": 1}) == "compose"


def test_summary_has_no_values() -> None:
    s = {
        "sufficient": False,
        "reasons": [
            {"type": "missing_field", "etf_code": "900010", "field": "net_assets"},
            {"type": "zero_results", "tool": "etf_search", "conditions": {"max_fee": 0.001}},
        ],
    }
    assert sufficiency.summarize(s) == "etf_info 900010: net_assets 없음; etf_search: 결과 0건"


class _CapturingLLM(FakeLLM):
    """재계획 입력 메시지를 확인하려고 마지막 메시지를 남긴다."""

    async def complete(self, messages, **kw):
        self.last_messages = messages
        return await super().complete(messages, **kw)


async def test_replan_input_has_reasons_and_db_names_but_no_values() -> None:
    llm = _CapturingLLM(
        script={
            "classify": [
                _plan(
                    ["etf_info"],
                    [
                        {"name": "etf_search", "args": {"conditions": {}}},
                        {"name": "etf_search", "args": {"conditions": {"region": "해외"}}},
                    ],
                )
            ]
        }
    )
    s = {"sufficient": False, "reasons": [{"type": "zero_results", "tool": "etf_search"}]}
    tools = await replan(
        llm,
        "나스닥 추종 목록",
        prev_tools=[{"name": "etf_search", "args": {"conditions": {}}}],
        prev_intents=["etf_info"],
        collected=sufficiency.summarize(s),
        sufficiency=s,
        indexes=["KOSPI 200", "NASDAQ-100"],
        model="plan-model",
    )
    msg = llm.last_messages[-1].content
    assert "[부족 사유]" in msg and "NASDAQ-100" in msg and "etf_search: 결과 0건" in msg
    assert llm.calls[-1]["model"] == "plan-model"
    # 1차와 같은 도구·인자는 빠지고 새 조건만 남는다
    assert tools == [{"name": "etf_search", "args": {"conditions": {"region": "해외"}}}]

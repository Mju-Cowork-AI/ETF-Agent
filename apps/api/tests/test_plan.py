"""계획 JSON(docs/interface.md): 정리·검증, 섞인 질문의 refuse, 계획 모델, 그래프 연결."""

import json

import pytest

from app.agents import etf_info
from app.agents.compose import refusal_texts, with_refusals
from app.agents.graph import run_graph
from app.agents.guard import rules
from app.agents.orchestrator import Plan, finalize_plan, parse_plan, plan
from app.agents.state import AgentDeps
from app.llm.fake import FakeLLM
from app.tools import etf_search, price_lookup


def _plan_json(**kw) -> str:
    base = {
        "intents": [],
        "tools": [],
        "answer_mode": "generate",
        "refuse": [],
        "confidence": 0.9,
        "needs_clarification": False,
        "clarify_question": None,
    }
    return json.dumps({**base, **kw}, ensure_ascii=False)


# ---------- parse_plan ----------
def test_parse_plan_cleans_tools_and_args() -> None:
    p = parse_plan(
        _plan_json(
            intents=["etf_info", "모름"],
            tools=[
                {
                    "name": "etf_info",
                    "args": {"etf_codes": ["900010", "abc"], "metrics": ["net_assets", "x"]},
                },
                {"name": "etf_search", "args": {"conditions": {"region": "해외", "foo": 1}}},
                {"name": "shell", "args": {}},
                {"name": "knowledge", "args": {"query": "  괴리율  "}},
            ],
            answer_mode="table",
        )
    )
    assert p is not None
    assert p.tools == [
        {"name": "etf_info", "args": {"etf_codes": ["900010"], "metrics": ["net_assets"]}},
        {"name": "etf_search", "args": {"conditions": {"region": "해외"}}},
        {"name": "knowledge", "args": {"query": "괴리율"}},
    ]
    # 도구만 적고 의도를 빠뜨린 faq도 채운다
    assert p.intents == ["etf_info", "faq"]
    assert p.answer_mode == "table"
    assert p.etf_codes() == ["900010"]
    assert p.conditions() == {"region": "해외"}


def test_parse_plan_accepts_legacy_and_rejects_garbage() -> None:
    legacy = parse_plan('{"intents": ["faq"]}')
    assert legacy is not None and legacy.intents == ["faq"] and legacy.refuse == []
    assert parse_plan("분류 불가") is None
    assert parse_plan('{"intents": []}') is None
    assert parse_plan('["faq"]') is None


def test_low_confidence_means_clarify() -> None:
    p = parse_plan(
        _plan_json(intents=["faq"], confidence=0.4, clarify_question="무엇을 비교할까요?")
    )
    assert p is not None and p.needs_clarification
    assert p.clarify_question == "무엇을 비교할까요?"
    sure = parse_plan(_plan_json(intents=["faq"], clarify_question="쓸모없는 질문"))
    assert sure is not None and not sure.needs_clarification and sure.clarify_question is None


# ---------- finalize_plan ----------
def test_mixed_question_answers_facts_and_refuses_rest() -> None:
    p = finalize_plan(
        Plan(intents=["etf_info"], refuse=["high_risk"]), "샘플 코스피200 보수랑 다음 달에 오를까?"
    )
    assert (p.intents, p.refuse) == (["etf_info"], ["high_risk"])
    # 계획이 판단 의도를 intents에 같이 적어도 같은 결과
    p = finalize_plan(Plan(intents=["faq", "out_of_scope"]), "괴리율 뜻이랑 오늘 날씨")
    assert (p.intents, p.refuse) == (["faq"], ["out_of_scope"])


def test_blocked_wins_and_judgment_only_stays_exclusive() -> None:
    p = finalize_plan(Plan(intents=["etf_info", "blocked"], refuse=["high_risk"]), "x")
    assert (p.intents, p.refuse) == (["blocked"], [])
    p = finalize_plan(Plan(intents=["recommendation", "out_of_scope"]), "하나 골라 줘")
    assert (p.intents, p.refuse) == (["recommendation"], [])


def test_rule_high_risk_overrides_plan_that_missed_it() -> None:
    # 규칙은 매수 판단을 잡았는데 계획은 사실 질문으로만 봤다 → 예전처럼 고위험 고정 답변
    p = finalize_plan(Plan(intents=["etf_info"]), "샘플 코스피200 지금 사야 할까?")
    assert (p.intents, p.refuse) == (["high_risk"], [])


# ---------- plan() ----------
async def test_plan_uses_plan_model_and_retries_bad_format_once() -> None:
    llm = FakeLLM(script={"classify": ["형식 틀림", _plan_json(intents=["faq"])]})
    p = await plan(llm, "괴리율이 뭐야?", has_entity=False, model="plan-model")
    assert (p.intents, p.source) == (["faq"], "llm")
    assert [c["model"] for c in llm.calls] == ["plan-model", "plan-model"]
    assert all(c["json_mode"] for c in llm.calls)


async def test_plan_falls_back_to_rules_after_two_bad_outputs() -> None:
    llm = FakeLLM(script={"classify": ["형식 틀림", "또 틀림"]})
    p = await plan(llm, "괴리율이 뭐야?", has_entity=False)
    assert (p.intents, p.source, p.refuse) == (["faq"], "rules", [])
    assert llm.count("classify") == 2


# ---------- 거절 문장 ----------
def test_refusal_lines_pass_guard_rules() -> None:
    for key, text in refusal_texts().items():
        assert rules.find_banned(text) == [], key
        assert rules.find_ranking(text) == [], key
        assert rules.extract_numbers(text) == [], key


def test_with_refusals_appends_known_lines_once() -> None:
    out = with_refusals("본문", ["high_risk", "high_risk", "모름"])
    assert out == "본문\n\n" + refusal_texts()["high_risk"]
    assert with_refusals("본문", []) == "본문"


# ---------- 계획 조건 → 조건 검색 ----------
def test_plan_conditions_fill_only_missing_and_known_values() -> None:
    f = etf_search.parse_filters("국내 ETF 보여줘", ["KOSPI 200"])
    f = etf_search.merge_plan_conditions(
        f,
        {
            "region": "해외",  # 질문에서 찾은 '국내'가 우선
            "category": "미국 대형주",  # DB에 없는 분류는 버린다
            "underlying_index": "KOSPI 200",
            "max_fee": "0.2%",
            "sort": "net_assets",
            "sort_desc": True,
        },
        ["KOSPI 200"],
    )
    assert f.region == "국내" and f.category is None
    assert f.underlying_index == "KOSPI 200"
    assert str(f.max_fee) == "0.2" and f.min_fee is None
    assert (f.sort, f.sort_desc) == ("net_assets", True)
    bad = etf_search.merge_plan_conditions(etf_search.EtfFilters(), {"max_fee": "많이"}, [])
    assert bad.max_fee is None and bad.is_empty()


# ---------- 그래프 ----------
async def test_graph_mixed_question_answers_table_and_refusal(
    deps: AgentDeps, fake_llm: FakeLLM
) -> None:
    fake_llm.push(
        "classify",
        _plan_json(
            intents=["etf_info"],
            tools=[{"name": "etf_info", "args": {"etf_codes": [], "metrics": []}}],
            refuse=["high_risk"],
            answer_mode="table",
        ),
    )
    st = await run_graph(
        deps, request_id="t", query="샘플 코스피200 정보 알려주고 다음 달에 오를까?"
    )
    assert st["intents"] == ["etf_info"]
    assert st["refuse"] == ["high_risk"]
    assert st["verdict"] == "pass", st.get("guard_reasons")
    assert "샘플 코스피200" in st["answer"]
    assert refusal_texts()["high_risk"] in st["answer"]
    assert "원금 손실이 발생할 수 있습니다" in st["answer"]  # 고지는 거절 문장 뒤에 그대로
    # 계획은 계획 모델 설정(PLAN_MODEL, 비우면 LLM_MODEL)으로 부른다
    plan_calls = [c for c in fake_llm.calls if c["task"] == "classify"]
    assert plan_calls[0]["model"] == deps.settings.plan_model_name


async def test_graph_plan_etf_codes_pick_etf_when_name_missing(
    deps: AgentDeps, fake_llm: FakeLLM
) -> None:
    fake_llm.push(
        "classify",
        _plan_json(
            intents=["etf_info"],
            tools=[{"name": "etf_info", "args": {"etf_codes": ["900030", "123456"]}}],
        ),
    )
    st = await run_graph(deps, request_id="t", query="미국 대표지수 따라가는 그 상품 보수 알려줘")
    assert [e.ticker for e in st["entities"]] == ["900030"]  # DB에 없는 코드는 버린다
    assert "샘플 미국S&P500" in st["answer"]


async def test_graph_plan_conditions_drive_search(deps: AgentDeps, fake_llm: FakeLLM) -> None:
    fake_llm.push(
        "classify",
        _plan_json(
            intents=["etf_info"],
            tools=[{"name": "etf_search", "args": {"conditions": {"region": "해외"}}}],
            answer_mode="table",
        ),
    )
    st = await run_graph(deps, request_id="t", query="바다 건너 상장된 지수 따라가는 것들 보여줘")
    assert "검색 결과(" in st["answer"]
    assert "샘플 코스피200" not in st["answer"]


@pytest.mark.parametrize("q", ["샘플 코스피200 지금 사도 될까?"])
async def test_graph_judgment_only_keeps_template(
    deps: AgentDeps, fake_llm: FakeLLM, q: str
) -> None:
    fake_llm.push("classify", _plan_json(intents=["high_risk"]))
    st = await run_graph(deps, request_id="t", query=q)
    assert st["intents"] == ["high_risk"] and st["verdict"] == "template"
    assert st.get("refuse") == []


# ---------- 시세 질문은 범위 밖이 아니라 ETF 정보(11-22 배포 확인) ----------
@pytest.mark.parametrize(
    "q", ["샘플 코스피200 지금 얼마에 거래돼?", "샘플 코스피200 현재가 알려줘"]
)
async def test_price_question_planned_out_of_scope_becomes_etf_info(
    deps: AgentDeps, fake_llm: FakeLLM, monkeypatch: pytest.MonkeyPatch, q: str
) -> None:
    async def no_prices(session, tickers):
        return {}

    monkeypatch.setattr(price_lookup, "latest", no_prices)
    fake_llm.push("classify", _plan_json(intents=["out_of_scope"]))
    st = await run_graph(deps, request_id="t", query=q)
    assert st["intents"] == ["etf_info"]
    assert st["refuse"] == []
    assert etf_info.NO_PRICE_NOTE in st["answer"]
    assert "ETF 정보와 ETF 관련 지식만" not in st["answer"]


async def test_price_part_in_refuse_is_dropped() -> None:
    llm = FakeLLM(script={"classify": [_plan_json(intents=["etf_info"], refuse=["out_of_scope"])]})
    p = await plan(llm, "샘플 코스피200 현재가 알려줘", has_entity=True)
    assert (p.intents, p.refuse) == (["etf_info"], [])


async def test_price_override_keeps_news_and_no_entity_cases() -> None:
    news = FakeLLM(script={"classify": [_plan_json(intents=["out_of_scope"])]})
    p = await plan(news, "샘플 코스피200 가격 관련 뉴스 알려줘", has_entity=True)
    assert p.intents == ["out_of_scope"]
    other = FakeLLM(script={"classify": [_plan_json(intents=["out_of_scope"])]})
    p = await plan(other, "비트코인 현재가 알려줘", has_entity=False)
    assert p.intents == ["out_of_scope"]

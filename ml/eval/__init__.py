"""오프라인 평가: data/eval-sets를 읽어 그래프를 직접 실행하고 지표를 낸다. # P1-OP-03

지표
- answer_accuracy: 골든셋 기대 키워드·수치가 모두 답변에 있고 의도도 일치한 비율
- intent_accuracy: 의도 집합 일치 비율
- entity_f1: ETF명 인식 마이크로 P/R/F1
- violation_recall: 위반 문장 탐지 재현율(가드 룰, 선택적으로 검증 모델), 오탐률 함께
- items(general·redteam·normal): 개발용 문항을 그래프로 돌려 문항별 답변과 자동 판정을 남긴다.
  채점표에 id로 붙여 쓰는 원본이다(docs/grading.md). 자동 판정은 참고용이고 최종 채점은 사람이 한다.

수치는 문자열 일치가 아니라 숫자 대조 규칙(반올림·버림, 상대 오차 5%, 단위 환산)으로 본다(채점 기준 8장 3번).
"""

import json
import time
import unicodedata
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.agents.graph import run_graph
from app.agents.guard.judge import UNVERIFIED, judge
from app.agents.guard.rules import find_banned, find_ranking, missing_numbers
from app.agents.preprocess import load_catalog, normalize, recognize_entities
from app.agents.state import AgentDeps
from app.privacy import find_pii
from app.settings import REPO_ROOT

DEFAULT_SETS = REPO_ROOT / "data" / "eval-sets"
# 문항별 결과를 남기는 평가셋. 시험용(split=test)은 private/에 같은 이름으로 둔다(data/eval-sets/README.md)
ITEM_SETS = ("general.jsonl", "redteam.jsonl", "normal.jsonl")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


@dataclass
class Report:
    metrics: dict[str, Any] = field(default_factory=dict)
    failures: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    items: list[dict[str, Any]] = field(default_factory=list)  # 문항별 결과(통과 문항 포함)

    def add(self, name: str, value: Any, failures: list[dict[str, Any]]) -> None:
        self.metrics[name] = value
        self.failures[name] = failures


async def eval_golden(deps: AgentDeps, rows: list[dict]) -> tuple[dict, list[dict]]:
    ok, fails, latencies = 0, [], []
    for r in rows:
        t0 = time.perf_counter()
        st = await run_graph(
            deps,
            request_id=f"eval-{uuid.uuid4().hex[:8]}",
            query=r["question"],
            level=r.get("level"),
        )
        latencies.append(time.perf_counter() - t0)
        ans = st.get("answer", "")
        missing = [k for k in r.get("expected_keywords", []) if k not in ans]
        missing += missing_numbers(ans, r.get("expected_numbers", []))
        intent_ok = sorted(st.get("intents", [])) == sorted(r.get("expected_intents", []))
        if not missing and intent_ok:
            ok += 1
        else:
            fails.append(
                {
                    "id": r.get("id"),
                    "missing": missing,
                    "intents": st.get("intents"),
                    "verdict": st.get("verdict"),
                }
            )
    n = len(rows) or 1
    return {
        "answer_accuracy": round(ok / n, 4),
        "n": len(rows),
        "avg_latency_s": round(sum(latencies) / n, 3),
    }, fails


async def eval_intents(deps: AgentDeps, rows: list[dict]) -> tuple[dict, list[dict]]:
    ok, fails = 0, []
    for r in rows:
        st = await run_graph(deps, request_id=f"eval-{uuid.uuid4().hex[:8]}", query=r["question"])
        got = sorted(st.get("intents", []))
        if got == sorted(r["intents"]):
            ok += 1
        else:
            fails.append({"question": r["question"], "expected": r["intents"], "got": got})
    return {"intent_accuracy": round(ok / (len(rows) or 1), 4), "n": len(rows)}, fails


async def eval_aliases(deps: AgentDeps, rows: list[dict]) -> tuple[dict, list[dict]]:
    catalog = await load_catalog(deps.maker)
    tp = fp = fn = 0
    fails = []
    for r in rows:
        got = {e.ticker for e in recognize_entities(normalize(r["question"]), catalog)}
        exp = set(r["tickers"])
        tp += len(got & exp)
        fp += len(got - exp)
        fn += len(exp - got)
        if got != exp:
            fails.append({"question": r["question"], "expected": sorted(exp), "got": sorted(got)})
    p = tp / (tp + fp) if tp + fp else 1.0
    rc = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * p * rc / (p + rc) if p + rc else 0.0
    return {
        "entity_precision": round(p, 4),
        "entity_recall": round(rc, 4),
        "entity_f1": round(f1, 4),
    }, fails


async def eval_violations(
    deps: AgentDeps, rows: list[dict], *, with_judge: bool
) -> tuple[dict, list[dict]]:
    """위반 문장 탐지. 검증 모델은 '투자 권유' 판정만 쓴다.

    평가셋에는 문장만 있고 근거가 없어 근거 일치(grounded)는 판정할 수 없다. 근거 없이 물으면
    정상 문장도 '근거 없음'이 되어 오탐률이 부풀려진다. 판정을 받지 못한 행(호출·해석 실패)은
    차단으로 세지 않고 judge_unverified로 따로 센다.
    """
    tp = fn = fp = tn = unverified = 0
    fails = []
    for r in rows:
        reasons = find_banned(r["text"]) + [f"pii:{k}" for k in find_pii(r["text"])]
        if with_judge and not reasons:
            jr, _ = await judge(
                deps.llm,
                model=deps.settings.judge_model_name,
                answer=r["text"],
                evidence=[],
            )
            if UNVERIFIED.intersection(jr):
                unverified += 1
            reasons += [x for x in jr if x == "judge:solicitation"]
        blocked = bool(reasons)
        if r["should_block"]:
            tp, fn = (tp + 1, fn) if blocked else (tp, fn + 1)
        else:
            fp, tn = (fp + 1, tn) if blocked else (fp, tn + 1)
        if blocked != r["should_block"]:
            fails.append(
                {
                    "text": r["text"],
                    "should_block": r["should_block"],
                    "reasons": reasons,
                }
            )
    return {
        "violation_recall": round(tp / (tp + fn), 4) if tp + fn else 1.0,
        "false_positive_rate": round(fp / (fp + tn), 4) if fp + tn else 0.0,
        "with_judge": with_judge,
        "judge_unverified": unverified,
    }, fails


def read_items(sets_dir: Path, split: str) -> list[dict[str, Any]]:
    """general·redteam·normal에서 split이 맞는 문항. private/의 같은 이름 파일도 읽는다(시험용)."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for file in ITEM_SETS:
        for path in (sets_dir / file, sets_dir / "private" / file):
            for r in read_jsonl(path):
                if r.get("split") == split and r.get("id") not in seen:
                    seen.add(r.get("id"))
                    rows.append(r)
    return rows


# 자동으로 볼 수 없어 사람이 채점할 필드(채점 기준 3장·5장)
_MANUAL_FIELDS = (
    "expected_answer",
    "criteria",
    "expected_behavior",
    "must_not_contain",
)


def judge_item(r: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
    """문항 하나의 자동 판정. 의도·키워드·수치·금지 범주 사유를 따로 남긴다."""
    ans = st.get("answer", "")
    got = sorted(st.get("intents", []))
    # 금지 표현·순위 규칙은 고지를 뺀 본문으로 본다(채점 기준 8장 8번). 본문이 없으면 답변 전체
    body = st.get("body") or ans
    rule_reasons = find_banned(body) + find_ranking(body)
    # 범주 id가 ranking이면 순위 규칙 사유(banned:ranking_*) 모두가 해당한다(guard_rules.md)
    forbidden = [f"banned:{c}" for c in r.get("forbidden_categories", [])]
    auto = {
        "intent_ok": got == sorted(r.get("expected_intents", [])),
        "missing_keywords": [k for k in r.get("expected_keywords", []) if k not in ans],
        "missing_numbers": missing_numbers(ans, r.get("expected_numbers", [])),
        "rule_reasons": rule_reasons,
        "forbidden_hits": [
            x for x in rule_reasons if any(x == f or x.startswith(f"{f}_") for f in forbidden)
        ],
    }
    auto["passed"] = (
        auto["intent_ok"]
        and not auto["missing_keywords"]
        and not auto["missing_numbers"]
        and not auto["forbidden_hits"]
    )
    return auto


async def eval_items(
    deps: AgentDeps, rows: list[dict[str, Any]]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """문항마다(통과 포함) id·답변·의도·자동 판정을 남긴다. 한 문항이 실패해도 나머지는 계속 돈다."""
    items: list[dict[str, Any]] = []
    for r in rows:
        item: dict[str, Any] = {
            "id": r.get("id"),
            "kind": r.get("kind"),
            "split": r.get("split"),
            "type": r.get("category") or r.get("attack_type"),
            "expected_intents": r.get("expected_intents", []),
            "manual": [f for f in _MANUAL_FIELDS if r.get(f)],
        }
        t0 = time.perf_counter()
        try:
            st = await run_graph(
                deps, request_id=f"eval-{uuid.uuid4().hex[:8]}", query=r["question"]
            )
        except Exception as e:  # 실제 모델 호출 실패 등. 문항을 오답으로 남기고 다음으로
            item.update(
                {
                    "answer": "",
                    "intents": [],
                    "error": type(e).__name__,
                    "auto": {
                        "passed": False,
                        "intent_ok": False,
                        "missing_numbers": list(r.get("expected_numbers", [])),
                    },
                }
            )
        else:
            guard = st.get("guard")
            item.update(
                {
                    "answer": st.get("answer", ""),
                    "intents": sorted(st.get("intents", [])),
                    "intent_source": st.get("intent_source"),
                    "agents_called": st.get("agents_called", []),
                    "verdict": st.get("verdict"),
                    # 재작성·안전 답변으로 끝나면 최종 guard에는 사유가 없어서, 반려 이력을 함께 남긴다
                    "guard_reasons": [r for rs in st.get("guard_history") or [] for r in rs]
                    or list(getattr(guard, "reasons", []) or []),
                    "model": st.get("model"),
                    "auto": judge_item(r, st),
                }
            )
        item["latency_s"] = round(time.perf_counter() - t0, 3)
        items.append(item)
    return summarize_items(items, rows), items


def summarize_items(items: list[dict[str, Any]], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """평가셋별(general·redteam·normal) 자동 판정 요약. 문항 원문은 담지 않는다."""
    expected = {r.get("id"): r.get("expected_numbers", []) for r in rows}
    out: dict[str, Any] = {}
    for kind in dict.fromkeys(i["kind"] for i in items):
        group = [i for i in items if i["kind"] == kind]
        n = len(group)
        auto = [i["auto"] for i in group]
        total_numbers = sum(len(expected.get(i["id"]) or []) for i in group)
        missed_numbers = sum(len(a.get("missing_numbers", [])) for a in auto)
        out[kind] = {
            "n": n,
            "auto_pass_rate": round(sum(a["passed"] for a in auto) / n, 4),
            "intent_accuracy": round(sum(bool(a.get("intent_ok")) for a in auto) / n, 4),
            "number_accuracy": (
                round((total_numbers - missed_numbers) / total_numbers, 4)
                if total_numbers
                else None
            ),
            "forbidden_hit_items": sum(bool(a.get("forbidden_hits")) for a in auto),
            "errors": sum("error" in i for i in group),
            "avg_latency_s": round(sum(i["latency_s"] for i in group) / n, 3),
        }
    return out


ALL_SETS = ("golden", "intents", "aliases", "violations", "items")


async def run_all(
    deps: AgentDeps,
    sets_dir: Path = DEFAULT_SETS,
    *,
    with_judge: bool = False,
    split: str = "dev",
    only: tuple[str, ...] = ALL_SETS,
) -> Report:
    rep = Report()
    for name, fn, file in (
        ("golden", eval_golden, "golden.jsonl"),
        ("intents", eval_intents, "intents.jsonl"),
        ("aliases", eval_aliases, "aliases.jsonl"),
    ):
        if name in only:
            metrics, fails = await fn(deps, read_jsonl(sets_dir / file))
            rep.add(name, metrics, fails)
    if "violations" in only:
        metrics, fails = await eval_violations(
            deps, read_jsonl(sets_dir / "violations.jsonl"), with_judge=with_judge
        )
        rep.add("violations", metrics, fails)
    if "items" in only:
        rows = read_items(sets_dir, split)
        by_kind, rep.items = await eval_items(deps, rows)
        for kind, metrics in by_kind.items():
            fails = [
                {"id": i["id"], "error": i["error"]}
                if "error" in i
                else {"id": i["id"], **i["auto"]}
                for i in rep.items
                if i["kind"] == kind and not i["auto"]["passed"]
            ]
            rep.add(f"{kind}({split})", metrics, fails)
    return rep


def _width(s: str) -> int:
    return sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in s)


def _pad(s: str, w: int) -> str:
    return s + " " * (w - _width(s))


def render_table(rep: Report) -> str:
    rows = [("평가셋", "지표", "값")]
    for name, metrics in rep.metrics.items():
        for k, v in metrics.items():
            rows.append((name, k, str(v)))
    w = [max(_width(r[i]) for r in rows) for i in range(3)]
    line = "+".join("-" * (x + 2) for x in w)
    out = [line]
    for i, r in enumerate(rows):
        out.append("|".join(f" {_pad(c, w[j])} " for j, c in enumerate(r)))
        if i == 0:
            out.append(line)
    out.append(line)
    return "\n".join(out)


def render_items(items: list[dict[str, Any]]) -> str:
    """문항별 자동 판정 한 줄씩(답변 원문 없음). 채점표에 붙이기 전 훑어보는 용도."""
    rows = [("id", "자동", "사유")]
    for i in items:
        a = i["auto"]
        why: list[str] = []
        if "error" in i:
            why.append(f"오류:{i['error']}")
        if a.get("intent_ok") is False and "error" not in i:
            why.append(f"의도:{','.join(i['intents']) or '-'}")
        why += [f"키워드:{k}" for k in a.get("missing_keywords", [])]
        why += [f"수치:{n}" for n in a.get("missing_numbers", []) if "error" not in i]
        why += a.get("forbidden_hits", [])
        if i.get("manual"):
            why.append("사람 채점:" + ",".join(i["manual"]))
        rows.append((str(i["id"]), "통과" if a["passed"] else "실패", " ".join(why)))
    w = [max(_width(r[c]) for r in rows) for c in range(2)]
    return "\n".join(f"{_pad(r[0], w[0])}  {_pad(r[1], w[1])}  {r[2]}" for r in rows)

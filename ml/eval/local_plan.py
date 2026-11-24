"""D3 로컬 LLM 실측: 계획(의도 분류) 단계만 다른 모델로 바꿔 정확도와 응답 시간을 잰다.

그래프 전체가 아니라 `app.agents.orchestrator.plan`만 부른다. 생성·검증·임베딩·DB는 쓰지 않으므로
Azure 호출(비용)이 없고 Docker 없이 호스트에서 돈다. 모델은 평소처럼 환경변수로만 바꾼다(코드 변경 없음).

    cd apps/api
    DATABASE_URL=postgresql+asyncpg://unused LLM_PROVIDER=openai_compat \
      LLM_BASE_URL=http://localhost:11434/v1 LLM_API_KEY=ollama \
      LLM_MODEL=exaone3.5:2.4b PLAN_MODEL=exaone3.5:2.4b FALLBACK_PROVIDER=none \
      OPENAI_MAX_TOKENS_PARAM=max_tokens OPENAI_OMIT_TEMPERATURE=false OPENAI_REASONING_EFFORT=off \
      PYTHONPATH=../.. uv run python -m ml.eval.local_plan --out ../../eval/results/d3_exaone.json

- 문항: `general.jsonl`의 split=dev(20문항). ETF 인식은 DB 대신 `data/real/etf_master.csv`로 한다.
- `--rules-only`: LLM 없이 키워드 규칙만(계획 모델이 죽었을 때의 동작). 비교 기준으로 쓴다.
- 결과(문항별 의도·시간)는 `--out`에만 남기고 커밋하지 않는다(eval/results/는 .gitignore).
"""

import argparse
import asyncio
import csv
import json
import statistics
import time
from pathlib import Path
from typing import Any

from app.agents.orchestrator import Plan, finalize_intents
from app.agents.orchestrator import plan as make_plan
from app.agents.orchestrator.rules import classify_rules
from app.agents.preprocess import CatalogEntry, compact, normalize, recognize_entities
from app.llm import build_llm
from app.llm.base import ChatMessage, LLMClient, LLMError, LLMResponse
from app.settings import REPO_ROOT, get_settings
from ml.eval import DEFAULT_SETS, read_jsonl

MASTER_CSV = REPO_ROOT / "data" / "real" / "etf_master.csv"


def load_csv_catalog(path: Path = MASTER_CSV) -> list[CatalogEntry]:
    """실데이터 CSV → 이름·별칭 사전(jobs.load_real과 같은 별칭 구분자 ';')."""
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        aliases = [a.strip() for a in (r.get("aliases") or "").split(";") if a.strip()]
        keys = tuple(dict.fromkeys(k for k in map(compact, [r["name"], *aliases]) if k))
        out.append(
            CatalogEntry(r["ticker"], r["name"], keys, r.get("underlying_index"), r.get("category"))
        )
    return out


class CountingLLM(LLMClient):
    """호출 수·실패 수·토큰만 센다(질문 원문은 남기지 않는다)."""

    def __init__(self, inner: LLMClient) -> None:
        self.inner = inner
        self.model = inner.model
        self.calls = 0
        self.errors = 0
        self.completion_tokens = 0

    async def complete(self, messages: list[ChatMessage], **kwargs: Any) -> LLMResponse:
        self.calls += 1
        try:
            resp = await self.inner.complete(messages, **kwargs)
        except LLMError:
            self.errors += 1
            raise
        self.completion_tokens += resp.usage.get("completion_tokens", 0)
        return resp


def _pct(values: list[float], q: float) -> float:
    """가장 가까운 순위 방식 백분위(문항 수가 적어 보간하지 않는다)."""
    s = sorted(values)
    return s[min(len(s) - 1, max(0, round(q * len(s) + 0.5) - 1))]


def summarize(items: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(items) or 1
    lat = [i["latency_s"] for i in items] or [0.0]
    by_cat: dict[str, list[bool]] = {}
    for i in items:
        by_cat.setdefault(i["category"], []).append(i["intent_ok"])
    return {
        "n": len(items),
        "intent_accuracy": round(sum(i["intent_ok"] for i in items) / n, 4),
        "by_category": {k: f"{sum(v)}/{len(v)}" for k, v in by_cat.items()},
        # 계획 JSON 형식이 두 번 틀리거나 호출이 실패해 키워드 규칙으로 넘어간 문항 수
        "rules_fallback": sum(i["source"] == "rules" for i in items),
        "format_retries": sum(max(0, i["llm_calls"] - 1) for i in items),
        "llm_errors": sum(i["llm_errors"] for i in items),
        "latency_s": {
            "mean": round(statistics.fmean(lat), 2),
            "median": round(statistics.median(lat), 2),
            "p90": round(_pct(lat, 0.9), 2),
            "max": round(max(lat), 2),
        },
    }


async def run(rows: list[dict[str, Any]], llm: CountingLLM | None, model: str | None) -> list[dict]:
    catalog = load_csv_catalog()
    items = []
    for r in rows:
        text = normalize(r["question"])
        has_entity = bool(recognize_entities(text, catalog))
        before = (llm.calls, llm.errors) if llm else (0, 0)
        t0 = time.perf_counter()
        if llm is None:
            intents = finalize_intents(
                [str(i) for i in classify_rules(text, has_entity=has_entity)]
            )
            p = Plan(intents=intents, source="rules")
        else:
            p = await make_plan(llm, text, has_entity=has_entity, model=model)
        dt = time.perf_counter() - t0
        expected = sorted(r.get("expected_intents", []))
        items.append(
            {
                "id": r["id"],
                "category": r.get("category", ""),
                "expected_intents": expected,
                "intents": sorted(p.intents),
                "refuse": p.refuse,
                "tools": [t["name"] for t in p.tools],
                "intent_ok": sorted(p.intents) == expected,
                "source": p.source,
                "llm_calls": llm.calls - before[0] if llm else 0,
                "llm_errors": llm.errors - before[1] if llm else 0,
                "latency_s": round(dt, 3),
            }
        )
    return items


async def main() -> None:
    parser = argparse.ArgumentParser(description="D3: 계획 단계만 바꿔 정확도·응답 시간 측정")
    parser.add_argument("--sets", type=Path, default=DEFAULT_SETS)
    parser.add_argument("--out", type=Path, help="JSON 결과 저장 경로(eval/results/ 아래)")
    parser.add_argument("--rules-only", action="store_true", help="LLM 없이 키워드 규칙만")
    args = parser.parse_args()

    rows = [
        r
        for r in read_jsonl(args.sets / "general.jsonl")
        if r.get("split") == "dev" and r.get("kind") == "general"
    ]
    s = get_settings()
    model = "rules" if args.rules_only else s.plan_model_name
    llm = None if args.rules_only else CountingLLM(build_llm(s, model=model))
    warmup_s = None
    if llm is not None:
        # 모델을 메모리에 올리는 시간은 문항 시간에서 뺀다(따로 적는다)
        t0 = time.perf_counter()
        await llm.complete([ChatMessage("user", "ok")], task="warmup", max_tokens=1)
        warmup_s = round(time.perf_counter() - t0, 2)
        llm.calls = 0
    items = await run(rows, llm, None if args.rules_only else model)
    report = {
        "model": model,
        "base_url": None if args.rules_only else s.llm_base_url,
        "warmup_s": warmup_s,
        **summarize(items),
        "items": items,
    }
    print(json.dumps({k: v for k, v in report.items() if k != "items"}, ensure_ascii=False))
    for i in items:
        if not i["intent_ok"]:
            print(
                f"  오답 {i['id']}({i['category']}): 기대 {i['expected_intents']} → {i['intents']}"
            )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())

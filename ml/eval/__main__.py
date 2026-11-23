"""CLI: python -m ml.eval [--sets data/eval-sets] [--out report.json] [--with-judge]
[--split dev|test] [--only items,golden,...]

개발용 평가 예: python -m ml.eval --only items --out eval/results/dev.json
--out에는 문항별 답변·자동 판정(items)까지 모두 남고, 화면에는 지표와 문항별 한 줄 요약만 나온다.
"""

import argparse
import asyncio
import json
from dataclasses import asdict
from pathlib import Path

from app.agents.state import AgentDeps
from app.db import dispose_engine, get_sessionmaker
from app.llm import build_embedder, build_llm
from app.settings import get_settings
from ml.eval import ALL_SETS, DEFAULT_SETS, render_items, render_table, run_all


async def main() -> None:
    parser = argparse.ArgumentParser(description="ETF Agent 오프라인 평가")
    parser.add_argument("--sets", type=Path, default=DEFAULT_SETS)
    parser.add_argument("--out", type=Path, help="JSON 리포트 저장 경로")
    parser.add_argument("--with-judge", action="store_true", help="위반 탐지에 검증 모델도 사용")
    parser.add_argument(
        "--split", default="dev", choices=["dev", "test"], help="general·redteam·normal 문항 구분"
    )
    parser.add_argument(
        "--only",
        default=",".join(ALL_SETS),
        help=f"돌릴 평가(쉼표로 구분). 기본 전부: {','.join(ALL_SETS)}",
    )
    args = parser.parse_args()
    only = tuple(x.strip() for x in args.only.split(",") if x.strip())
    unknown = set(only) - set(ALL_SETS)
    if unknown:
        parser.error(f"--only에 없는 이름: {', '.join(sorted(unknown))}")

    s = get_settings()
    deps = AgentDeps(
        settings=s, llm=build_llm(s), embedder=build_embedder(s), maker=get_sessionmaker()
    )
    print(f"LLM={s.llm_provider.value}:{deps.llm.model}  embedding={deps.embedder.model}")
    try:
        rep = await run_all(
            deps, args.sets, with_judge=args.with_judge, split=args.split, only=only
        )
    finally:
        await dispose_engine()
    report = {"llm": deps.llm.model, "embedding": deps.embedder.model, **asdict(rep)}
    # 화면에는 답변 원문을 찍지 않는다(문항별 답변은 --out 파일에만)
    print(
        json.dumps({k: v for k, v in report.items() if k != "items"}, ensure_ascii=False, indent=2)
    )
    print(render_table(rep))
    if rep.items:
        print(render_items(rep.items))
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"저장: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())

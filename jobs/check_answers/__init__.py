"""일반 평가셋 정답값을 DB(EtfMaster)와 대조한다.

읽기 전용: DB에 쓰지 않는다.
결과 파일을 만들지 않는다. eval-sets 파일을 수정하지 않는다.
"""

import json
import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.repositories.models import EtfMaster
from app.settings import REPO_ROOT

logger = logging.getLogger(__name__)

EVAL_DIR = REPO_ROOT / "data" / "eval-sets"

ITEM_COLUMN: dict[str, str] = {
    "총보수": "total_expense_ratio",
    "실부담비용": "actual_expense_ratio",
    "상장일": "listed_date",
    "분배주기": "distribution_cycle",
    "기초지수": "underlying_index",
    "운용사": "issuer",
    "환헤지": "currency_hedged",
}

AS_OF_COLUMN: dict[str, str] = {
    "실부담비용": "actual_expense_as_of",
    "순자산": "net_assets_as_of",
}

NUMERIC_ITEMS = {"총보수", "실부담비용"}
TEXT_ITEMS = {"분배주기", "기초지수", "운용사", "환헤지"}
DATE_ITEMS = {"상장일"}

# sources.item 의 부분 문자열로 항목을 인식한다.
# "실부담비용"이 "총보수"에 걸리지 않도록 긴 이름부터 매칭한다.
_ITEM_MATCH_ORDER: list[str] = sorted(ITEM_COLUMN, key=len, reverse=True)


@dataclass
class CheckResult:
    question_id: str
    split: str  # "dev" | "test"
    item: str
    expected: str
    db_value: str
    match: bool
    note: str = ""


# ---- File I/O ----


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                items.append(json.loads(stripped))
    return items


def load_items(
    eval_dir: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    """Return (dev_items, test_items, warnings)."""
    base = eval_dir or EVAL_DIR
    warns: list[str] = []

    dev_items = read_jsonl(base / "general.jsonl")
    for it in dev_items:
        it["_split"] = "dev"

    test_items: list[dict[str, Any]] = []
    private_dir = base / "private"
    found = False
    for fname in ("general.jsonl", "general_test.jsonl"):
        p = private_dir / fname
        if p.exists():
            found = True
            for it in read_jsonl(p):
                it["_split"] = "test"
                test_items.append(it)
    if not found:
        warns.append(f"시험용 파일 없음: {private_dir}")

    return dev_items, test_items, warns


# ---- ETF matching ----


def _combined_text(item: dict[str, Any]) -> str:
    return " ".join(
        [
            item.get("question", ""),
            " ".join(item.get("expected_keywords", [])),
            item.get("expected_answer", ""),
        ]
    )


def find_etfs(text: str, all_etfs: list[EtfMaster]) -> list[EtfMaster]:
    """question + expected_keywords + expected_answer 전체에서 ETF 이름·별칭을 찾는다."""
    matched: list[EtfMaster] = []
    for etf in all_etfs:
        names = [etf.name, *list(etf.aliases or [])]
        if any(n and n in text for n in names):
            matched.append(etf)
    return matched


# ---- Item detection ----


def _normalize_item_name(raw: str) -> str | None:
    """sources.item 의 부분 문자열에서 표준 항목 이름을 찾는다.

    긴 이름("실부담비용")부터 매칭해 "총보수"와 섞이지 않게 한다.
    """
    if raw in ITEM_COLUMN:
        return raw
    for canonical in _ITEM_MATCH_ORDER:
        if canonical in raw:
            return canonical
    return None


def _sources_items(item: dict[str, Any]) -> list[str]:
    seen: list[str] = []
    for src in item.get("sources", []):
        name = _normalize_item_name(src.get("item", ""))
        if name and name not in seen:
            seen.append(name)
    return seen


def _detect_fee_items(item: dict[str, Any]) -> tuple[set[str], bool]:
    """Return (item_names, is_guess).

    item_names 는 {"총보수"}, {"실부담비용"}, {"총보수", "실부담비용"}, 또는 빈 집합.
    is_guess=True 일 때는 sources·keywords 에서 판별 불가, 빈 집합이 돌아온다.
    """
    found: set[str] = set()
    for src in item.get("sources", []):
        normed = _normalize_item_name(src.get("item", ""))
        if normed and normed in NUMERIC_ITEMS:
            found.add(normed)
    kw = set(item.get("expected_keywords", []))
    if "총보수" in kw:
        found.add("총보수")
    if "실부담비용" in kw:
        found.add("실부담비용")
    if found:
        return found, False
    return set(), True


# ---- Comparison helpers ----


def _parse_pct(s: str) -> Decimal | None:
    try:
        return Decimal(s.replace("%", "").strip())
    except InvalidOperation, ValueError:
        return None


def _fmt_dec(d: Decimal | None) -> str:
    if d is None:
        return ""
    return f"{d:.4f}%"


def _try_pair(
    answer: str,
    numbers: list[str],
    etfs: list[EtfMaster],
) -> dict[str, str] | None:
    """expected_answer 안에서 'ETF전체이름 … 숫자%' 위치로 짝짓기. 실패 시 None."""
    events: list[tuple[int, str, str]] = []

    for etf in etfs:
        for m in re.finditer(re.escape(etf.name), answer):
            events.append((m.start(), "etf", etf.name))

    if not any(t == "etf" for _, t, _ in events):
        return None

    for num_str in numbers:
        raw = num_str.rstrip("%").rstrip()
        pattern = re.escape(raw) + r"\s*%"
        found = False
        for m in re.finditer(pattern, answer):
            events.append((m.start(), "num", num_str))
            found = True
            break
        if not found:
            return None

    events.sort(key=lambda x: x[0])

    pairs: dict[str, str] = {}
    cur_etf: str | None = None
    for _, typ, val in events:
        if typ == "etf":
            cur_etf = val
        else:
            if cur_etf is None:
                return None
            if cur_etf in pairs:
                return None
            pairs[cur_etf] = val

    if len(set(pairs.values())) != len(numbers):
        return None
    return pairs


def _text_match(
    expected: str,
    db_value: str,
    keywords: list[str],
    item_name: str,
    etf_names: list[str],
) -> bool:
    """분배주기·기초지수·운용사 유연 비교."""
    if not db_value:
        return False
    if expected in db_value or db_value in expected:
        return True
    # DB 값을 괄호·구분자로 나눈 조각(2글자 이상)이 정답에 하나라도 있으면 일치
    tokens = re.split(r"[()·,\s]+", db_value)
    if any(len(t) >= 2 and t in expected for t in tokens):
        return True
    skip = set(etf_names)
    remaining = [
        kw for kw in keywords if kw not in skip and kw not in item_name and item_name not in kw
    ]
    return bool(remaining) and all(kw in db_value for kw in remaining)


# ---- Number-to-item assignment (문제 1) ----

_ITEM_LABEL_RE = re.compile(r"총보수|실부담비용")


def _assign_numbers_to_items(
    numbers: list[str],
    answer: str,
    etfs: list[EtfMaster],
    fee_items: set[str],
) -> list[tuple[str, str, bool]]:
    """각 숫자에 항목을 대응시킨다.

    Returns list of (number_str, item_name, is_guess) — 순서는 numbers 와 동일.
    """
    result: list[tuple[str, str, bool]] = []
    for nstr in numbers:
        raw = nstr.rstrip("%").rstrip()
        pattern = re.escape(raw) + r"\s*%"
        m = re.search(pattern, answer)
        assigned: str | None = None
        is_guess = False

        # 1) expected_answer 에서 숫자 바로 앞 가장 가까운 항목 낱말
        if m:
            before = answer[: m.start()]
            best_label: str | None = None
            best_pos = -1
            for lm in _ITEM_LABEL_RE.finditer(before):
                if lm.group() in fee_items and lm.end() > best_pos:
                    best_pos = lm.end()
                    best_label = lm.group()
            assigned = best_label

        # 2) 못 정하면 DB 값 비교 → 맞는 쪽 + "(추정)"
        if not assigned:
            exp = _parse_pct(nstr)
            if exp is not None:
                for fi in fee_items:
                    col = ITEM_COLUMN[fi]
                    if any(getattr(e, col, None) == exp for e in etfs):
                        assigned = fi
                        is_guess = True
                        break

        # 3) 어느 컬럼과도 안 맞으면 첫 번째 항목으로 태깅(불일치)
        if not assigned:
            assigned = sorted(fee_items)[0]

        result.append((nstr, assigned, is_guess))

    return result


# ---- Check builders ----


def _check_numbers(
    item: dict[str, Any],
    etfs: list[EtfMaster],
    numbers: list[str],
    col: str,
    label: str,
    is_guess: bool,
) -> list[CheckResult]:
    qid = item["id"]
    split: str = item["_split"]
    answer: str = item.get("expected_answer", "")
    tag = f"{label}(추정)" if is_guess else label

    if not etfs:
        return [CheckResult(qid, split, tag, n, "", False, "대조 불가") for n in numbers]

    # 여러 숫자 + 여러 ETF → 짝짓기 시도
    if len(numbers) > 1 and len(etfs) > 1:
        pairs = _try_pair(answer, numbers, etfs)
        if pairs:
            etf_map = {e.name: e for e in etfs}
            results: list[CheckResult] = []
            for ename, nstr in pairs.items():
                etf = etf_map.get(ename)
                if not etf:
                    results.append(CheckResult(qid, split, tag, nstr, "", False, "대조 불가"))
                    continue
                db = getattr(etf, col, None)
                exp = _parse_pct(nstr)
                results.append(
                    CheckResult(
                        qid,
                        split,
                        tag,
                        nstr,
                        _fmt_dec(db),
                        db is not None and exp is not None and exp == db,
                    )
                )
            return results

        # 짝짓기 실패 → 아무 ETF 값과 맞으면 일치
        db_map = {e.name: getattr(e, col, None) for e in etfs}
        results = []
        for nstr in numbers:
            exp = _parse_pct(nstr)
            matched_name = next(
                (n for n, v in db_map.items() if v is not None and exp is not None and exp == v),
                None,
            )
            if matched_name is not None:
                results.append(
                    CheckResult(qid, split, tag, nstr, _fmt_dec(db_map[matched_name]), True)
                )
            else:
                all_db = ", ".join(f"{n}={_fmt_dec(v)}" for n, v in db_map.items() if v is not None)
                results.append(CheckResult(qid, split, tag, nstr, all_db, False))
        return results

    # 단일 ETF
    if len(etfs) == 1:
        etf = etfs[0]
        db = getattr(etf, col, None)
        return [
            CheckResult(
                qid,
                split,
                tag,
                nstr,
                _fmt_dec(db),
                db is not None and _parse_pct(nstr) is not None and _parse_pct(nstr) == db,
            )
            for nstr in numbers
        ]

    # 여러 ETF, 단일 숫자 → 아무 ETF 값과 맞으면 일치
    results = []
    for nstr in numbers:
        exp = _parse_pct(nstr)
        found = False
        for etf in etfs:
            db = getattr(etf, col, None)
            if db is not None and exp is not None and exp == db:
                results.append(CheckResult(qid, split, tag, nstr, _fmt_dec(db), True))
                found = True
                break
        if not found:
            vals = ", ".join(
                f"{e.name}={_fmt_dec(getattr(e, col, None))}"
                for e in etfs
                if getattr(e, col, None) is not None
            )
            results.append(CheckResult(qid, split, tag, nstr, vals, False))
    return results


def build_checks(item: dict[str, Any], all_etfs: list[EtfMaster]) -> list[CheckResult] | None:
    """문항 하나에 대한 대조 결과. 대조할 항목이 없으면 None."""
    combined = _combined_text(item)
    etfs = find_etfs(combined, all_etfs)

    src_items = _sources_items(item)
    numbers: list[str] = item.get("expected_numbers", [])
    answer: str = item.get("expected_answer", "")
    keywords: list[str] = item.get("expected_keywords", [])

    has_numeric = bool(numbers)
    has_text = any(si in TEXT_ITEMS for si in src_items)
    has_date = any(si in DATE_ITEMS for si in src_items)
    has_as_of = any(src.get("as_of") for src in item.get("sources", []))

    if not has_numeric and not has_text and not has_date and not has_as_of:
        return None

    results: list[CheckResult] = []
    qid: str = item["id"]
    split: str = item["_split"]
    etf_names = [e.name for e in etfs]

    # -- 수치 --
    if has_numeric:
        fee_items, is_guess = _detect_fee_items(item)
        if fee_items and not is_guess:
            if len(fee_items) == 1:
                fi = next(iter(fee_items))
                results.extend(_check_numbers(item, etfs, numbers, ITEM_COLUMN[fi], fi, False))
            else:
                # 항목이 둘(총보수+실부담비용) → 숫자마다 항목 배정
                assignments = _assign_numbers_to_items(numbers, answer, etfs, fee_items)
                for fi in fee_items:
                    nums_for_fi = [n for n, a, _ in assignments if a == fi]
                    guesses = {n: g for n, a, g in assignments if a == fi}
                    if nums_for_fi:
                        for nstr in nums_for_fi:
                            results.extend(
                                _check_numbers(
                                    item, etfs, [nstr], ITEM_COLUMN[fi], fi, guesses[nstr]
                                )
                            )
        elif is_guess:
            for try_item in ("총보수", "실부담비용"):
                attempt = _check_numbers(item, etfs, numbers, ITEM_COLUMN[try_item], try_item, True)
                if attempt and all(r.match for r in attempt):
                    results.extend(attempt)
                    break
            else:
                results.extend(
                    _check_numbers(item, etfs, numbers, "total_expense_ratio", "총보수", True)
                )

    # -- 글자 항목 --
    for si in src_items:
        if si in TEXT_ITEMS:
            col = ITEM_COLUMN[si]
            if not etfs:
                results.append(CheckResult(qid, split, si, answer, "", False, "대조 불가"))
            else:
                for etf in etfs:
                    db_val = getattr(etf, col, None) or ""
                    matched = _text_match(answer, db_val, keywords, si, etf_names)
                    results.append(CheckResult(qid, split, si, answer, db_val, matched))

    # -- 날짜 항목(상장일) --
    date_re = re.compile(r"\d{4}-\d{2}-\d{2}")
    for si in src_items:
        if si in DATE_ITEMS:
            col = ITEM_COLUMN[si]
            expected_date = ""
            m = date_re.search(answer)
            if m:
                expected_date = m.group()
            else:
                for kw in keywords:
                    if date_re.fullmatch(kw):
                        expected_date = kw
                        break
            if expected_date:
                if not etfs:
                    results.append(
                        CheckResult(qid, split, si, expected_date, "", False, "대조 불가")
                    )
                else:
                    for etf in etfs:
                        db_val = getattr(etf, col, None)
                        db_str = str(db_val) if db_val else ""
                        results.append(
                            CheckResult(
                                qid, split, si, expected_date, db_str, expected_date == db_str
                            )
                        )

    # -- 기준일(as_of) --
    for src in item.get("sources", []):
        as_of = src.get("as_of", "")
        si = src.get("item", "")
        if as_of and si in AS_OF_COLUMN:
            col = AS_OF_COLUMN[si]
            label = f"{si} 기준일"
            if not etfs:
                results.append(CheckResult(qid, split, label, as_of, "", False, "대조 불가"))
            else:
                for etf in etfs:
                    db_val = getattr(etf, col, None)
                    db_str = str(db_val) if db_val else ""
                    results.append(CheckResult(qid, split, label, as_of, db_str, as_of == db_str))

    return results


# ---- Output formatting ----


def format_results(results: list[CheckResult]) -> str:
    lines: list[str] = []
    for r in results:
        mark = "\u2713" if r.match else "\u2717"
        note = f" [{r.note}]" if r.note else ""
        if r.split == "dev":
            lines.append(
                f"  {r.question_id} | {r.item} | {r.expected} | {r.db_value} | {mark}{note}"
            )
        else:
            # 시험용: 질문·정답값·DB 값 출력 금지
            lines.append(f"  {r.question_id} | {r.item} | {mark}{note}")
    return "\n".join(lines)


def summarize(
    dev_results: list[CheckResult],
    test_results: list[CheckResult],
    dev_skipped: int,
    test_skipped: int,
) -> str:
    dev_fail = sum(1 for r in dev_results if not r.match)
    lines = [
        f"개발용: 대조 {len(dev_results)}건, 불일치 {dev_fail}건, 대조 대상 없음 {dev_skipped}건"
    ]
    if test_results or test_skipped:
        test_fail = sum(1 for r in test_results if not r.match)
        lines.append(
            f"시험용: 대조 {len(test_results)}건, 불일치 {test_fail}건, 대조 대상 없음 {test_skipped}건"
        )
    return "\n".join(lines)


# ---- DB ----


async def load_all_etfs(session: AsyncSession) -> list[EtfMaster]:
    result = await session.execute(select(EtfMaster))
    return list(result.scalars().all())


# ---- Main entry ----


async def run(maker: async_sessionmaker[AsyncSession], eval_dir: Path | None = None) -> int:
    """대조 실행. 불일치·대조 불가가 있으면 1, 없으면 0."""
    dev_items, test_items, warns = load_items(eval_dir)
    for w in warns:
        logger.warning(w)
        print(w)

    async with maker() as session:
        all_etfs = await load_all_etfs(session)

    dev_results: list[CheckResult] = []
    test_results: list[CheckResult] = []
    dev_skipped = 0
    test_skipped = 0

    for it in dev_items:
        checks = build_checks(it, all_etfs)
        if checks is None:
            dev_skipped += 1
        else:
            dev_results.extend(checks)

    for it in test_items:
        checks = build_checks(it, all_etfs)
        if checks is None:
            test_skipped += 1
        else:
            test_results.extend(checks)

    if dev_results:
        print("\n[개발용]")
        print(format_results(dev_results))

    if test_results:
        print("\n[시험용]")
        print(format_results(test_results))

    print()
    print(summarize(dev_results, test_results, dev_skipped, test_skipped))

    has_fail = any(not r.match for r in [*dev_results, *test_results])
    return 1 if has_fail else 0

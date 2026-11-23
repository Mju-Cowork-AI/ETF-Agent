"""jobs.check_answers 단위 테스트.

실제 DB·private 폴더를 쓰지 않고, 가짜 문항과 SimpleNamespace ETF로 검증한다.
"""

import json
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from jobs.check_answers import (
    CheckResult,
    build_checks,
    find_etfs,
    format_results,
    load_items,
)


def _etf(**kw: object) -> SimpleNamespace:
    """EtfMaster 대용 객체."""
    defaults = {
        "ticker": "000000",
        "name": "테스트ETF",
        "aliases": [],
        "alias_text": "",
        "issuer": None,
        "underlying_index": None,
        "total_expense_ratio": None,
        "actual_expense_ratio": None,
        "actual_expense_as_of": None,
        "distribution_cycle": None,
        "listed_date": None,
        "net_assets_as_of": None,
    }
    defaults.update(kw)
    return SimpleNamespace(**defaults)


def _item(
    *,
    qid: str = "t01",
    split: str = "dev",
    question: str = "",
    keywords: list[str] | None = None,
    numbers: list[str] | None = None,
    answer: str = "",
    sources: list[dict[str, str]] | None = None,
) -> dict:
    return {
        "id": qid,
        "_split": split,
        "question": question,
        "expected_keywords": keywords or [],
        "expected_numbers": numbers or [],
        "expected_answer": answer,
        "sources": sources or [],
    }


# ---- 일치 ----


def test_single_number_match():
    etf = _etf(name="TIGER 미국나스닥100", total_expense_ratio=Decimal("0.0068"))
    item = _item(
        question="TIGER 미국나스닥100 총보수 얼마야?",
        keywords=["TIGER 미국나스닥100", "총보수"],
        numbers=["0.0068%"],
        answer="연 0.0068%",
        sources=[{"item": "총보수"}],
    )
    results = build_checks(item, [etf])
    assert results is not None
    assert len(results) == 1
    assert results[0].match is True


def test_text_issuer_match():
    etf = _etf(name="KODEX 200", issuer="삼성자산운용")
    item = _item(
        question="KODEX 200 운용사가 어디야?",
        keywords=["삼성자산운용"],
        answer="삼성자산운용",
        sources=[{"item": "운용사"}],
    )
    results = build_checks(item, [etf])
    assert results is not None
    assert all(r.match for r in results)


# ---- 불일치 ----


def test_number_mismatch():
    etf = _etf(name="TIGER 미국나스닥100", total_expense_ratio=Decimal("0.0099"))
    item = _item(
        question="TIGER 미국나스닥100 총보수 얼마야?",
        keywords=["총보수"],
        numbers=["0.0068%"],
        answer="연 0.0068%",
        sources=[{"item": "총보수"}],
    )
    results = build_checks(item, [etf])
    assert results is not None
    assert any(not r.match for r in results)


# ---- 시험용 출력에 정답값 미포함 ----


def test_test_split_hides_values():
    r = CheckResult(
        question_id="sec01",
        split="test",
        item="총보수",
        expected="0.0068%",
        db_value="0.0068%",
        match=True,
    )
    output = format_results([r])
    assert "sec01" in output
    assert "총보수" in output
    # 정답값·DB 값이 출력에 없어야 한다
    assert "0.0068%" not in output


def test_test_split_hides_values_on_mismatch():
    r = CheckResult(
        question_id="sec02",
        split="test",
        item="실부담비용",
        expected="0.1308%",
        db_value="0.1400%",
        match=False,
    )
    output = format_results([r])
    assert "0.1308%" not in output
    assert "0.1400%" not in output
    assert "\u2717" in output


# ---- _test 파일 읽기 ----


def test_reads_private_test_file(tmp_path: Path):
    # 개발용
    dev = [{"id": "g01", "split": "dev", "question": "q"}]
    (tmp_path / "general.jsonl").write_text(
        json.dumps(dev[0], ensure_ascii=False) + "\n", encoding="utf-8"
    )
    # 시험용 private/
    priv = tmp_path / "private"
    priv.mkdir()
    t1 = {"id": "p01", "split": "test", "question": "q1"}
    t2 = {"id": "p02", "split": "test", "question": "q2"}
    (priv / "general.jsonl").write_text(json.dumps(t1, ensure_ascii=False) + "\n", encoding="utf-8")
    (priv / "general_test.jsonl").write_text(
        json.dumps(t2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    dev_items, test_items, warns = load_items(tmp_path)
    assert len(dev_items) == 1
    assert {it["id"] for it in test_items} == {"p01", "p02"}
    assert not warns


def test_missing_private_warns(tmp_path: Path):
    (tmp_path / "general.jsonl").write_text("{}\n", encoding="utf-8")
    _, _, warns = load_items(tmp_path)
    assert any("시험용 파일 없음" in w for w in warns)


# ---- ETF 이름이 question에만 있는 문항 ----


def test_etf_found_only_in_question():
    """gen03처럼 ETF 이름이 question에만 있을 때도 찾아야 한다."""
    etf = _etf(name="ACE 미국나스닥100", listed_date="2020-10-29")
    item = _item(
        question="ACE 미국나스닥100 상장일이 언제야?",
        keywords=["상장일", "2020-10-29"],
        answer="2020-10-29",
        sources=[{"item": "상장일"}],
    )
    results = build_checks(item, [etf])
    assert results is not None
    assert results[0].match is True


# ---- 숫자 여러 개 (any-match 경로) ----


def test_multi_number_any_match():
    """gen11처럼 짝짓기 불가 시 아무 ETF 값과 맞으면 일치."""
    etf_a = _etf(name="TIGER 미국나스닥100", total_expense_ratio=Decimal("0.0068"))
    etf_b = _etf(name="KODEX 미국나스닥100", total_expense_ratio=Decimal("0.0062"))
    item = _item(
        question="TIGER 미국나스닥100이랑 KODEX 미국나스닥100 총보수 비교해줘",
        keywords=["TIGER 미국나스닥100", "KODEX 미국나스닥100", "총보수"],
        numbers=["0.0068%", "0.0062%"],
        answer="TIGER 0.0068% vs KODEX 0.0062%",  # 전체 이름 없음 → 짝짓기 실패
        sources=[{"item": "총보수"}],
    )
    results = build_checks(item, [etf_a, etf_b])
    assert results is not None
    num_results = [r for r in results if "총보수" in r.item]
    assert all(r.match for r in num_results)


def test_multi_number_paired():
    """gen16처럼 expected_answer에 전체 ETF 이름이 있으면 짝짓기."""
    etfs = [
        _etf(name="TIGER 미국배당다우존스", actual_expense_ratio=Decimal("0.1092")),
        _etf(name="ACE 미국나스닥100", actual_expense_ratio=Decimal("0.1308")),
        _etf(name="TIGER 미국나스닥100", actual_expense_ratio=Decimal("0.1430")),
        _etf(name="KODEX 미국나스닥100", actual_expense_ratio=Decimal("0.1571")),
    ]
    item = _item(
        keywords=["실부담비용", "2026-10-30"],
        numbers=["0.1092%", "0.1308%", "0.1430%", "0.1571%"],
        answer=(
            "낮은 순: TIGER 미국배당다우존스 0.1092% < ACE 미국나스닥100 0.1308%"
            " < TIGER 미국나스닥100 0.1430% < KODEX 미국나스닥100 0.1571%"
            " (기준일 2026-10-30)"
        ),
        sources=[{"item": "실부담비용", "as_of": "2026-10-30"}],
    )
    results = build_checks(item, etfs)
    assert results is not None
    num_results = [r for r in results if r.item == "실부담비용"]
    assert len(num_results) == 4
    assert all(r.match for r in num_results)


# ---- 분배주기 표기 차이 ----


def test_distribution_cycle_flexible_match():
    """gen04: 정답 '월배당(매월)', DB '매월' → DB값이 정답에 포함 → 일치."""
    etf = _etf(name="TIGER 미국배당다우존스", distribution_cycle="매월")
    item = _item(
        question="TIGER 미국배당다우존스 분배주기가 어떻게 돼?",
        keywords=["분배", "매월"],
        answer="월배당(매월)",
        sources=[{"item": "분배주기"}],
    )
    results = build_checks(item, [etf])
    assert results is not None
    text_results = [r for r in results if r.item == "분배주기"]
    assert text_results[0].match is True


def test_distribution_cycle_keyword_match():
    """DB '월(매월)'일 때 키워드 '매월'이 DB에 포함 → 일치."""
    etf = _etf(name="TIGER 미국배당다우존스", distribution_cycle="월(매월)")
    item = _item(
        question="TIGER 미국배당다우존스 분배주기가 어떻게 돼?",
        keywords=["분배", "매월"],
        answer="월배당(매월)",
        sources=[{"item": "분배주기"}],
    )
    results = build_checks(item, [etf])
    assert results is not None
    text_results = [r for r in results if r.item == "분배주기"]
    assert text_results[0].match is True


# ---- 대조 대상 없음 (개념·추천·범위 밖) ----


def test_no_checkable_items_returns_none():
    item = _item(
        question="총보수랑 실부담비용 차이가 뭐야?",
        keywords=["총보수", "실부담비용"],
        answer="총보수는 운용·판매 보수. 실부담비용은 ...",
        sources=[],
    )
    assert build_checks(item, []) is None


# ---- ETF 못 찾으면 대조 불가 ----


def test_etf_not_found_is_unverifiable():
    item = _item(
        question="없는ETF 총보수 얼마야?",
        keywords=["총보수"],
        numbers=["0.0100%"],
        answer="연 0.01%",
        sources=[{"item": "총보수"}],
    )
    results = build_checks(item, [])
    assert results is not None
    assert all(r.note == "대조 불가" for r in results)
    assert all(not r.match for r in results)


# ---- as_of 기준일 ----


def test_as_of_date_check():
    etf = _etf(name="ACE 미국나스닥100", actual_expense_as_of="2026-10-30")
    item = _item(
        question="ACE 미국나스닥100 실부담비용 얼마야?",
        keywords=["실부담비용", "2026-10-30"],
        numbers=["0.1308%"],
        answer="0.1308% (기준일 2026-10-30)",
        sources=[{"item": "실부담비용", "as_of": "2026-10-30"}],
    )
    # actual_expense_ratio 없으면 숫자 불일치지만, 기준일은 별도로 체크
    results = build_checks(item, [etf])
    assert results is not None
    as_of_results = [r for r in results if "기준일" in r.item]
    assert len(as_of_results) == 1
    assert as_of_results[0].match is True


# ---- find_etfs: 별칭 ----


def test_find_etfs_by_alias():
    etf = _etf(name="공식이름ETF", aliases=["별칭A"])
    assert find_etfs("별칭A 총보수", [etf]) == [etf]
    assert find_etfs("다른텍스트", [etf]) == []


# ---- 추정 경로 ----


def test_guess_fee_column():
    """sources·keywords에 항목이 없으면 두 컬럼을 시도해서 맞는 쪽을 고른다."""
    etf = _etf(name="TEST ETF", total_expense_ratio=Decimal("0.0050"))
    item = _item(
        question="TEST ETF 보수 얼마야?",
        keywords=["TEST ETF"],
        numbers=["0.0050%"],
        answer="0.005%",
        sources=[],
    )
    # sources 비었지만 numbers가 있으므로 대조 대상 있음
    results = build_checks(item, [etf])
    assert results is not None
    assert results[0].match is True
    assert "추정" in results[0].item

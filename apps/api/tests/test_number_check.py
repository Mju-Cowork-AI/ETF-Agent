"""숫자 대조(가드 ①): 단위 환산·반올림·날짜 대조·질문 수치 (Streamlit 기반 core/guardrail.py에서 옮김)."""

import pytest

from app.agents.guard.rules import check_rules, ungrounded_numbers

TABLE = (
    "| 항목 | 샘플 코스피200 |\n| --- | --- |\n"
    "| 총보수 | 연 0.0450% |\n| NAV | 36,095.44원 |\n| 괴리율 | -0.17% |\n"
    "| 순자산 | 178,500,000,000원 |\n| 실부담비용 | 0.0099% |\n"
    "기준일: 2026-11-11 (일별 데이터)"
)


# --- 단위 환산 ---
@pytest.mark.parametrize(
    "answer",
    [
        "순자산은 1,785억 원입니다.",
        "순자산은 1785억원입니다.",
        "순자산은 약 1,785억 원 규모입니다.",
    ],
)
def test_korean_units_are_converted(answer: str) -> None:
    assert ungrounded_numbers(answer, [TABLE]) == []


def test_compound_korean_units() -> None:
    evidence = ["| 순자산 | 1,234,500,000,000원 |"]
    assert ungrounded_numbers("순자산은 1조 2,345억 원입니다.", evidence) == []
    assert ungrounded_numbers("순자산은 1조 3,245억 원입니다.", evidence) == ["1조3245억"]


def test_wrong_converted_value_is_caught() -> None:
    assert ungrounded_numbers("순자산은 1,875억 원입니다.", [TABLE]) == ["1875억"]


# --- 반올림·버림 (상대 오차 5% 이하) ---
@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("총보수는 연 0.0450%입니다.", []),  # 그대로
        ("총보수는 연 0.045%입니다.", []),  # 끝자리 0 생략
        ("실부담비용은 0.01%입니다.", []),  # 0.0099% 반올림(오차 1%)
        ("NAV는 36,095원입니다.", []),  # 36,095.44 버림
        ("NAV는 36,095.4원입니다.", []),  # 반올림
        ("NAV는 36,100원입니다.", ["36100원"]),  # 마지막 자릿수(1원)에서 맞지 않음
        ("총보수는 0.5%입니다.", ["0.5%"]),
    ],
)
def test_rounding_within_tolerance(answer: str, expected: list[str]) -> None:
    assert ungrounded_numbers(answer, [TABLE]) == expected


def test_rounding_beyond_tolerance_is_caught() -> None:
    # 반올림이어도 상대 오차가 5%를 넘으면 불통과(0.0062% → 0.01%는 61%, 0.0450% → 0.05%는 11%)
    assert ungrounded_numbers("총보수는 0.01%입니다.", ["총보수 0.0062%"]) == ["0.01%"]
    assert ungrounded_numbers("총보수는 0.05%입니다.", [TABLE]) == ["0.05%"]


def test_boundary_is_not_truncation() -> None:
    # 근거 10을 9.99로 쓰는 것은 버림이 아니다(원 코드의 경계값 처리 수정)
    assert ungrounded_numbers("괴리율은 9.99%입니다.", ["| 순위 | 10 |"]) == ["9.99%"]


def test_date_digits_are_not_numeric_evidence() -> None:
    # 근거의 기준일 2026-11-11 속 숫자(2026, 11)로 답변 수치가 통과하면 안 된다
    assert ungrounded_numbers("괴리율은 11%입니다.", [TABLE]) == ["11%"]
    assert ungrounded_numbers("2,026원입니다.", [TABLE]) == ["2026원"]


def test_negative_values() -> None:
    assert ungrounded_numbers("괴리율은 -0.17%입니다.", [TABLE]) == []


# --- 날짜 대조 ---
@pytest.mark.parametrize(
    "answer",
    [
        "2026-11-11 기준입니다.",
        "2026.11.11 기준입니다.",
        "2026년 11월 11일 기준입니다.",
        "2026년 11월 기준입니다.",
        "11월 11일 기준입니다.",
    ],
)
def test_dates_matching_evidence_pass(answer: str) -> None:
    assert ungrounded_numbers(answer, [TABLE]) == []


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("2026-11-15 기준입니다.", ["2026-11-15"]),
        ("2026년 10월 31일 기준입니다.", ["2026년10월31일"]),
        ("2025년 실적입니다.", ["2025년"]),
    ],
)
def test_dates_not_in_evidence_are_caught(answer: str, expected: list[str]) -> None:
    assert ungrounded_numbers(answer, [TABLE]) == expected


def test_unicode_hyphen_and_space_are_normalized() -> None:
    assert ungrounded_numbers("2026\u201111\u201111 기준 0.0450\u202f%", [TABLE]) == []


# --- 질문 속 수치·날짜 ---
def test_numbers_from_question_are_allowed() -> None:
    answer = "총보수 0.1% 이하인 상품은 아래와 같습니다."
    assert ungrounded_numbers(answer, [TABLE]) == ["0.1%"]
    assert ungrounded_numbers(answer, [TABLE], "총보수 0.1% 이하 해외 ETF 찾아줘") == []


def test_dates_from_question_are_allowed() -> None:
    answer = "2024년 분배금 자료는 아직 없습니다."
    assert ungrounded_numbers(answer, [TABLE]) == ["2024년"]
    assert ungrounded_numbers(answer, [TABLE], "069500 2024년 분배금 알려줘") == []


def test_check_rules_passes_question() -> None:
    body = "총보수 0.1% 이하인 상품은 아래와 같습니다."
    kwargs = {"included_disclaimers": [], "required_disclaimers": [], "evidence": [TABLE]}
    assert "ungrounded_number:0.1%" in check_rules(body, **kwargs)
    assert "ungrounded_number:0.1%" not in check_rules(body, question="0.1% 이하 ETF", **kwargs)


# --- 검사하지 않는 숫자 ---
@pytest.mark.parametrize(
    "answer",
    [
        "KODEX 200과 TIGER 미국나스닥100을 비교했습니다.",
        "상위 10개 종목과 3종목을 봤습니다.",
        "종목코드 133690 [1]",
        "S&P500 지수를 추종합니다.",
    ],
)
def test_names_ranks_codes_are_not_checked(answer: str) -> None:
    assert ungrounded_numbers(answer, [TABLE]) == []

"""개인정보 마스킹. 로그·트레이스·DB 저장 전에 반드시 mask_pii()를 거친다(공통 규칙 4). # P1-AG-06"""

import hashlib
import re

# 순서가 중요하다: 긴 패턴(주민번호·카드) → 짧은 패턴(전화·계좌)
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("EMAIL", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("RRN", re.compile(r"(?<!\d)\d{6}\s?-\s?[1-8]\d{6}(?!\d)")),  # 주민·외국인등록번호
    ("CARD", re.compile(r"(?<!\d)\d{4}[- ]\d{4}[- ]\d{4}[- ]\d{4}(?!\d)")),
    # 전화번호. 지역번호·통신사 번호 뒤가 붙어 있는데 끝 4자리만 공백으로 떨어진 꼴은 받지 않는다:
    # '069500 2024년'(종목코드 + 연도)이 전화번호로 가려진다. 휴대전화만 그 꼴을 허용한다.
    (
        "PHONE",
        re.compile(
            r"(?<!\d)(?:"
            r"(?:01[016789]|0[2-6]\d?)[- .]\d{3,4}[- .]\d{4}"  # 02-123-4567, 010 1234 5678
            r"|(?:01[016789]|0[2-6]\d?)\d{3,4}[-.]?\d{4}"  # 01012345678, 0212345678, 021234-5678
            r"|01[016789]\d{3,4} \d{4}"  # 0101234 5678
            r")(?!\d)"
        ),
    ),
    # 계좌번호(날짜 YYYY-MM-DD는 제외)
    (
        "ACCOUNT",
        re.compile(
            r"(?<!\d)(?!(?:19|20)\d{2}-[01]\d-[0-3]\d(?!\d))\d{3,6}-\d{2,6}-\d{2,8}(?:-\d{1,3})?(?!\d)"
        ),
    ),
    ("RRN", re.compile(r"(?<!\d)\d{2}[01]\d[0-3]\d[1-8]\d{6}(?!\d)")),  # 하이픈 없는 13자리
]


def find_pii(text: str) -> list[str]:
    """발견된 개인정보 종류 목록(중복 제거, 값은 반환하지 않는다)."""
    kinds: list[str] = []
    for kind, pat in _PATTERNS:
        if pat.search(text) and kind not in kinds:
            kinds.append(kind)
    return kinds


# ---------- 외부 호출 전 차단(입력 검사) ----------
# mask_pii(저장·트레이스용)와 따로 둔다. 차단은 구분자 없는 카드번호·하이픈 없는 계좌번호까지 본다.
# 오탐을 줄이려고 카드는 Luhn 검사 통과나 가까운 '카드' 단어를, 계좌는 가까운 '계좌' 단어를 요구한다.
# 숫자 뒤에 단위(원·주·%·년 등)나 소수점이 붙으면 금액·수량·비율로 보고, 앞에 영문자가 붙으면
# ISIN(KR7069500007) 일부로 보아 제외한다. 종목코드(6자리)·날짜(8자리)는 자릿수가 달라 걸리지 않는다.
_NOT_UNIT = r"(?!\d|[.,]\d|\s*(?:원|주|만|억|조|%|개|년|월|일))"
_BARE_CARD = re.compile(r"(?<![A-Za-z0-9])\d{16}" + _NOT_UNIT)
_NEAR = 15  # '카드'·'계좌' 단어와 숫자 사이 최대 글자 수
_BARE_ACCOUNT = re.compile(
    rf"계좌[^\d\n]{{0,{_NEAR}}}(?<![A-Za-z0-9])\d{{10,14}}{_NOT_UNIT}"
    rf"|(?<![A-Za-z0-9])\d{{10,14}}{_NOT_UNIT}[^\d\n]{{0,{_NEAR}}}계좌"
)


def _luhn_ok(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return total % 10 == 0


def _has_bare_card(text: str) -> bool:
    for m in _BARE_CARD.finditer(text):
        near = text[max(0, m.start() - _NEAR) : m.end() + _NEAR]
        if _luhn_ok(m.group()) or "카드" in near:
            return True
    return False


def find_pii_to_block(text: str) -> list[str]:
    """외부 호출(LLM·임베딩) 전에 막을 개인정보 종류. 값은 돌려주지 않는다.

    반드시 원문(정규화 전)에 쓴다. 정규화는 '@'·'_'를 지워 이메일을 놓친다.
    """
    kinds = find_pii(text)
    if "CARD" not in kinds and _has_bare_card(text):
        kinds.append("CARD")
    if "ACCOUNT" not in kinds and _BARE_ACCOUNT.search(text):
        kinds.append("ACCOUNT")
    return kinds


def mask_pii(text: str) -> str:
    """이메일·주민번호·카드·전화·계좌번호를 [EMAIL] 같은 자리표시로 바꾼다."""
    if not text:
        return text
    for kind, pat in _PATTERNS:
        text = pat.sub(f"[{kind}]", text)
    return text


def stable_hash(value: str) -> str:
    """캐시 키 등에 쓰는 SHA-256 앞 16자리(원문을 키에 남기지 않는다)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]

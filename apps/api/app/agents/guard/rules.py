"""가드 ① 룰: 금칙 표현·순위 표현, 필수 고지 누락, 개인정보 노출, 근거 없는 수치. # P1-AG-06

금칙 표현 5범주와 순위 규칙 R1~R3의 기준은 docs/guard_rules.md, 패턴은 prompts/guard/rules.yaml에 있다.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from app.agents.prompts import load_yaml
from app.privacy import find_pii

_CITATION = re.compile(r"\[\d{1,2}\]")
_TICKER = re.compile(r"(?<!\d)\d{6}(?!\d)")

# 0장: 유니코드 하이픈·빼기 기호와 특수 공백을 ASCII로 바꾼다(금칙·순위 검사에만 쓴다)
_HYPHENS = re.compile(r"[\u2010-\u2015\u2212\uFE58\uFE63\uFF0D]")
_SPACES = re.compile(r"[\u00A0\u2000-\u200B\u202F\u205F\u3000\uFEFF]")


@dataclass(frozen=True, slots=True)
class BannedRule:
    id: str
    reason: str
    patterns: tuple[re.Pattern[str], ...]

    def search(self, text: str) -> bool:
        return any(p.search(text) for p in self.patterns)


@dataclass(frozen=True, slots=True)
class RankingRule:
    sentence_split: re.Pattern[str]
    skip_line: re.Pattern[str]
    target: re.Pattern[str]
    basis: re.Pattern[str]
    date: re.Pattern[str]
    cheapest: re.Pattern[str]
    real_cost: re.Pattern[str]
    rank_marker: re.Pattern[str]
    recommend: re.Pattern[str]


@lru_cache(maxsize=1)
def _config() -> dict:
    return load_yaml("guard/rules.yaml")


def _expand(pattern: str) -> str:
    neg = _config().get("negation", {})
    for name, value in neg.items():
        pattern = pattern.replace("{" + name + "}", value)
    return pattern


@lru_cache(maxsize=1)
def _banned() -> tuple[BannedRule, ...]:
    return tuple(
        BannedRule(r["id"], r["reason"], tuple(re.compile(_expand(p)) for p in r["patterns"]))
        for r in _config()["banned"]
    )


def banned_rules() -> list[BannedRule]:
    return list(_banned())


@lru_cache(maxsize=1)
def _ranking() -> RankingRule | None:
    cfg = _config().get("ranking")
    if not cfg:
        return None
    flags = {"skip_line": re.MULTILINE, "target": re.IGNORECASE, "rank_marker": re.IGNORECASE}
    return RankingRule(**{k: re.compile(cfg[k], flags.get(k, 0)) for k in RankingRule.__slots__})


@lru_cache(maxsize=1)
def _quoted_mention() -> re.Pattern[str] | None:
    p = _config().get("preprocess", {}).get("quoted_mention")
    return re.compile(p) if p else None


def normalize(text: str) -> str:
    """검사 전 공통 처리: 하이픈·공백 정규화, '…'는 표현 같은 인용 문구 지우기(0장)."""
    text = _SPACES.sub(" ", _HYPHENS.sub("-", text))
    quoted = _quoted_mention()
    return quoted.sub(" ", text) if quoted else text


def find_banned(text: str) -> list[str]:
    """금칙 표현 5범주. 범주마다 한 번만 보고한다(banned:{범주 id})."""
    text = normalize(text)
    return [f"banned:{r.id}" for r in _banned() if r.search(text)]


def sentences(text: str) -> list[str]:
    rule = _ranking()
    if rule is None:
        return []
    text = rule.skip_line.sub("", normalize(text))
    return [s.strip() for s in rule.sentence_split.split(text) if s.strip()]


def find_ranking(text: str) -> list[str]:
    """순위 표현 R1~R3(6장). 문장마다 검사하고 사유는 규칙별로 한 번만 보고한다.

    R1 순서·순위 문장에는 정렬 기준과 기준일을 같은 문장에 쓴다.
    R2 '가장 저렴'은 같은 문장에 실부담비용이 있어야 한다(기준일이 ETF마다 다른지는 데이터로만 알 수 있어
       여기서는 보지 않는다, D8).
    R3 순위를 좋은 상품·정답·추천으로 잇지 않는다(바꿔 말한 표현은 검증 모델이 판정).
    """
    rule = _ranking()
    if rule is None:
        return []
    found: list[str] = []
    for s in sentences(text):
        if rule.target.search(s):
            if not rule.basis.search(s):
                found.append("banned:ranking_no_basis")
            if not rule.date.search(s):
                found.append("banned:ranking_no_date")
        if rule.cheapest.search(s) and not rule.real_cost.search(s):
            found.append("banned:ranking_cheapest_without_real_cost")
        if rule.rank_marker.search(s) and rule.recommend.search(s):
            found.append("banned:ranking_as_recommendation")
    return list(dict.fromkeys(found))


# --- 숫자 대조(가드 ①) ---
# Streamlit 기반 core/guardrail.py의 unsupported_numbers 규칙을 옮겨 왔다(원 코드: 조은서).
# 1. 단위(%·원·배·bp·주·좌·조·억·만)가 붙거나 소수점이 있는 수치만 검사한다. 이름 속 숫자(KODEX 200,
#    나스닥100), 순위·개수(상위 10개), 인용 번호([1]), 종목코드(6자리)는 검사하지 않는다.
# 2. 한글 단위(조·억·만)는 값으로 환산해 비교한다(1,785억 원 = 178,500,000,000원).
# 3. 답변 값이 근거 값을 마지막 표시 자릿수에서 반올림·버림한 값이고, 상대 오차가 rel_tolerance(5%) 이하면
#    통과한다(근거 0.0099% → 답변 0.01% 통과, 근거 0.0062% → 답변 0.01% 불통과).
# 4. 날짜(2026-11-11, 2026년 11월 11일, 2026년 11월, 11월 11일, 2026년)는 근거·질문의 날짜와 맞아야 통과한다.
# 5. 질문에 나온 날짜와, 질문에서 조건 표현(이하·이상·미만·초과·까지·부터·보다 낮은 …)이 붙은 수치만 근거로 본다
#    ("총보수 0.1% 이하" 질문에 "0.1% 이하"로 답하는 경우). "0.5%라던데 맞아?"처럼 사용자가 주장한 수치는
#    근거가 아니다. 가드는 결과가 매번 같아야 해서 계획 JSON(LLM) 값은 근거로 쓰지 않는다(11-21 결정).
#    알려진 남은 경우(11-24 개발용 평가에서 확인): "0.5% 이하라던데 맞아?"처럼 조건 표현과 주장이 섞이면 통과,
#    질문 속 날짜는 주장이어도 근거로 인정.

_UNIT_MULT = {"조": 1e12, "억": 1e8, "만": 1e4}
_NUM = r"\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
_LEAD = r"(?<![\d.,A-Za-z])"  # 앞이 숫자·영문이면 수치 시작으로 보지 않는다(ISIN 등)
_COMPOUND = re.compile(
    rf"{_LEAD}(?P<sign>-)?(?P<n1>{_NUM})\s*(?P<u1>조|억|만)"
    rf"(?:\s*(?P<n2>{_NUM})\s*(?P<u2>억|만))?"
    rf"(?:\s*(?P<n3>{_NUM})\s*(?P<u3>만))?"
    r"(?:\s*(?:원|주|좌))?"
)
_PLAIN = re.compile(rf"{_LEAD}(?P<sign>-)?(?P<n>{_NUM})(?!\d)\s*(?P<unit>%p|%|원|배|bp|주|좌)?")
_ANY_NUM = re.compile(rf"(?P<sign>-)?(?P<n>{_NUM})")

# 날짜(긴 형식부터 찾고 찾은 자리는 지운다)
_DATE_FULL = re.compile(r"(?<!\d)(\d{4})\s*[-./]\s*(\d{1,2})\s*[-./]\s*(\d{1,2})(?!\d)")
_DATE_KO_FULL = re.compile(r"(?<!\d)(\d{4})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_DATE_KO_YM = re.compile(r"(?<!\d)(\d{4})\s*년\s*(\d{1,2})\s*월")
_DATE_KO_MD = re.compile(r"(?<!\d)(\d{1,2})\s*월\s*(\d{1,2})\s*일")
_DATE_KO_Y = re.compile(r"(?<!\d)(\d{4})\s*년")


@dataclass(frozen=True, slots=True)
class _Num:
    raw: str  # 사유에 쓰는 표기(쉼표·공백 없음, 예: 0.5%, 1785억)
    value: float
    unit: float  # 마지막 표시 자릿수의 크기(예: 0.01, 1억)


@dataclass(slots=True)
class _Dates:
    full: set[tuple[int, int, int]]
    ym: set[tuple[int, int]]
    md: set[tuple[int, int]]
    years: set[int]

    def add(self, y: int, m: int, d: int) -> None:
        self.full.add((y, m, d))
        self.ym.add((y, m))
        self.md.add((m, d))
        self.years.add(y)


def _chars(text: str) -> str:
    """유니코드 하이픈·특수 공백을 ASCII로(글자 수 유지)."""
    return _SPACES.sub(" ", _HYPHENS.sub("-", text))


def _blank(text: str, span: tuple[int, int]) -> str:
    s, e = span
    return text[:s] + " " * (e - s) + text[e:]


def _decimals(s: str) -> int:
    return len(s.split(".")[1]) if "." in s else 0


def _to_float(s: str) -> float:
    return float(s.replace(",", ""))


def _collect_dates(text: str) -> _Dates:
    """근거·질문 속 날짜. 연·월만 있는 표현(2026년 11월)도 그 범위로 인정한다."""
    out = _Dates(set(), set(), set(), set())
    for pattern in (_DATE_FULL, _DATE_KO_FULL):
        for y, m, d in pattern.findall(text):
            out.add(int(y), int(m), int(d))
    for y, m in _DATE_KO_YM.findall(text):
        out.ym.add((int(y), int(m)))
        out.years.add(int(y))
    for y in _DATE_KO_Y.findall(text):
        out.years.add(int(y))
    return out


def _check_dates(text: str, allowed: _Dates) -> tuple[str, list[str]]:
    """답변 속 날짜를 근거·질문 날짜와 대조하고 본문에서 지운다. 맞지 않는 날짜 표기를 돌려준다."""
    rules = (
        (_DATE_FULL, lambda g: (int(g[0]), int(g[1]), int(g[2])) in allowed.full),
        (_DATE_KO_FULL, lambda g: (int(g[0]), int(g[1]), int(g[2])) in allowed.full),
        (_DATE_KO_YM, lambda g: (int(g[0]), int(g[1])) in allowed.ym),
        (_DATE_KO_MD, lambda g: (int(g[0]), int(g[1])) in allowed.md),
        (_DATE_KO_Y, lambda g: int(g[0]) in allowed.years),
    )
    bad: list[str] = []
    for pattern, ok in rules:
        for m in list(pattern.finditer(text)):
            if not ok(m.groups()):
                bad.append(re.sub(r"\s+", "", m.group()))
            text = _blank(text, m.span())
    return text, bad


def _extract(text: str, *, require_unit_or_decimal: bool) -> list[_Num]:
    nums: list[_Num] = []
    for m in list(_COMPOUND.finditer(text)):
        value, unit = 0.0, 1.0
        for n_key, u_key in (("n1", "u1"), ("n2", "u2"), ("n3", "u3")):
            if m.group(n_key):
                mult = _UNIT_MULT[m.group(u_key)]
                value += _to_float(m.group(n_key)) * mult
                unit = 10 ** -_decimals(m.group(n_key)) * mult
        if m.group("sign"):
            value = -value
        raw = re.sub(r"[\s,]|원$|주$|좌$", "", m.group())
        nums.append(_Num(raw=raw, value=value, unit=unit))
        text = _blank(text, m.span())
    for m in _PLAIN.finditer(text):
        n, unit_s = m.group("n"), m.group("unit")
        if require_unit_or_decimal and not unit_s and "." not in n:
            continue
        sign = "-" if m.group("sign") else ""
        value = _to_float(n) * (-1 if sign else 1)
        raw = f"{sign}{n.replace(',', '')}{unit_s or ''}"
        nums.append(_Num(raw=raw, value=value, unit=10 ** -_decimals(n)))
    return nums


def _evidence_values(text: str) -> list[float]:
    """근거·질문 속 모든 수치를 값으로(한글 단위 환산 포함, 단위 없는 수도 포함)."""
    values: list[float] = []
    for m in list(_COMPOUND.finditer(text)):
        v = sum(
            _to_float(m.group(n)) * _UNIT_MULT[m.group(u)]
            for n, u in (("n1", "u1"), ("n2", "u2"), ("n3", "u3"))
            if m.group(n)
        )
        values.append(-v if m.group("sign") else v)
        text = _blank(text, m.span())
    for m in _ANY_NUM.finditer(text):
        v = _to_float(m.group("n"))
        values.append(-v if m.group("sign") else v)
    return values


# 질문 속 수치 바로 뒤에 오는 조건 표현(검색 조건으로 쓴 수치만 근거로 인정)
_CONDITION_AFTER = re.compile(
    r"^\s*(?:이하|이상|미만|초과|까지|부터|이내|넘는|넘게|넘지|안\s*넘|아래|밑|보다\s*(?:낮|높|작|크|적|많|싼|비싼))"
)


def _condition_values(question: str) -> list[float]:
    """질문에서 조건 표현이 붙은 수치만 값으로("0.1% 이하"의 0.1). 주장·확인 요청 속 수치는 뺀다."""
    text = _check_dates(_chars(question), _Dates(set(), set(), set(), set()))[0]
    values: list[float] = []
    for x, end in _extract_with_end(text):
        if _CONDITION_AFTER.match(text[end:]):
            values.append(x.value)
    return values


def _extract_with_end(text: str) -> list[tuple[_Num, int]]:
    """_extract와 같되 각 수치가 끝나는 위치를 함께 돌려준다(단위가 없어도 포함)."""
    out: list[tuple[_Num, int]] = []
    for m in list(_COMPOUND.finditer(text)):
        value = sum(
            _to_float(m.group(n)) * _UNIT_MULT[m.group(u)]
            for n, u in (("n1", "u1"), ("n2", "u2"), ("n3", "u3"))
            if m.group(n)
        )
        out.append(
            (_Num(raw=m.group(), value=-value if m.group("sign") else value, unit=1.0), m.end())
        )
        text = _blank(text, m.span())
    for m in _PLAIN.finditer(text):
        v = _to_float(m.group("n"))
        out.append((_Num(raw=m.group(), value=-v if m.group("sign") else v, unit=1.0), m.end()))
    return out


def _same_value(x: _Num, f: float, rel_tolerance: float) -> bool:
    """답변 값 x가 근거 값 f를 반올림·버림한 표기이고 상대 오차가 rel_tolerance 이하인지."""
    for target in (f, -f):
        if x.value == 0:
            if target == 0:
                return True
            continue
        eps = 1e-9 * max(1.0, abs(target))
        diff = abs(x.value - target)
        rounded = diff <= x.unit / 2 + eps
        # 버림: 근거가 답변보다 크고 차이가 마지막 자릿수 1칸 미만(경계값은 버림이 아니다: 10 → 9.99 불통과)
        truncated = 0 <= abs(target) - abs(x.value) < x.unit - eps and (x.value >= 0) == (
            target >= 0
        )
        if (rounded or truncated) and diff <= rel_tolerance * abs(target) + eps:
            return True
    return False


def _prepare(text: str) -> str:
    text = _chars(text)
    text = _CITATION.sub(" ", text)
    return _TICKER.sub(" ", text)


def extract_numbers(text: str) -> list[str]:
    """답변에서 검사 대상 수치의 표기(날짜·인용 번호·종목코드 제외)."""
    cfg = _config()["numbers"]
    text, _ = _check_dates(_prepare(text), _Dates(set(), set(), set(), set()))
    nums = _extract(text, require_unit_or_decimal=cfg.get("require_unit_or_decimal", True))
    return [n.raw for n in nums]


def ungrounded_numbers(answer: str, evidence: list[str], question: str = "") -> list[str]:
    """답변 수치·날짜 중 근거(evidence)·질문 날짜·질문의 조건 수치에 없는 것. 비어 있으면 통과.

    값으로 비교한다: 근거가 '0.0500%'·'36,180.00원'·'178,500,000,000원'이면 답변의 '0.05%'·'36,180원'·
    '1,785억 원'도 근거가 있다. 반올림·버림은 상대 오차 rel_tolerance(기본 5%) 안에서만 인정한다.
    """
    cfg = _config()["numbers"]
    if not cfg.get("enabled", True):
        return []
    allow = {a.replace(" ", "") for a in cfg.get("allow", [])}
    tol = float(cfg.get("rel_tolerance", 0.05))
    ev_text = _chars(" ".join(evidence))
    # 날짜는 근거와 질문 모두에서 인정한다
    allowed_dates = _collect_dates(_chars(f"{ev_text} {question}"))
    # 날짜 속 숫자(2026-11-11의 2026·11)가 수치 근거로 섞이지 않게 날짜를 지운 뒤 수치를 모은다
    allowed_values = _evidence_values(_check_dates(ev_text, allowed_dates)[0])
    # 질문 수치는 조건 표현이 붙은 것만("0.1% 이하"). "0.5%라던데 맞아?"의 0.5%는 근거가 아니다
    allowed_values += _condition_values(question)

    text, missing = _check_dates(_prepare(answer), allowed_dates)
    for x in _extract(text, require_unit_or_decimal=cfg.get("require_unit_or_decimal", True)):
        if x.raw in allow or any(_same_value(x, f, tol) for f in allowed_values):
            continue
        missing.append(x.raw)
    return list(dict.fromkeys(missing))


def missing_numbers(answer: str, expected: list[str]) -> list[str]:
    """평가용: 정답 수치·날짜(expected) 중 답변에 없는 것. 비어 있으면 모두 있음.

    ungrounded_numbers와 방향만 반대이고 같은 규칙을 쓴다(채점 기준 2장, 8장 3번). 정답 값을 근거로 보고,
    답변 수치가 그 값을 반올림·버림한 표기이며 상대 오차 rel_tolerance 이하면 있다고 본다.
    '0.0100%' = '0.01%', '1,785억 원' = '178,500,000,000원'. 날짜는 같은 날이어야 한다.
    """
    cfg = _config()["numbers"]
    tol = float(cfg.get("rel_tolerance", 0.05))
    answer_dates = _collect_dates(_chars(answer))
    text, _ = _check_dates(_prepare(answer), answer_dates)
    found = _extract(text, require_unit_or_decimal=cfg.get("require_unit_or_decimal", True))
    out: list[str] = []
    for e in expected:
        e_dates = _collect_dates(_chars(e))
        if e_dates.full:
            ok = e_dates.full <= answer_dates.full
        else:
            values = _evidence_values(_chars(e))
            ok = bool(values) and all(any(_same_value(x, v, tol) for x in found) for v in values)
        if not ok and e not in answer:
            out.append(e)
    return out


def check_rules(
    body: str,
    *,
    included_disclaimers: list[str],
    required_disclaimers: list[str],
    evidence: list[str],
    question: str = "",
    check_numbers: bool = True,
) -> list[str]:
    reasons = find_banned(body) + find_ranking(body)
    reasons += [
        f"missing_disclaimer:{d}" for d in required_disclaimers if d not in included_disclaimers
    ]
    if _config().get("pii", {}).get("enabled", True):
        reasons += [f"pii:{k}" for k in find_pii(body)]
    if check_numbers:
        reasons += [f"ungrounded_number:{n}" for n in ungrounded_numbers(body, evidence, question)]
    return reasons


def clear_cache() -> None:
    _config.cache_clear()
    _banned.cache_clear()
    _ranking.cache_clear()
    _quoted_mention.cache_clear()

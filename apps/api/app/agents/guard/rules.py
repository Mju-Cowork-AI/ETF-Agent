"""가드 ① 룰: 금칙 표현·순위 표현, 필수 고지 누락, 개인정보 노출, 근거 없는 수치. # P1-AG-06

금칙 표현 5범주와 순위 규칙 R1~R3의 기준은 docs/guard_rules.md, 패턴은 prompts/guard/rules.yaml에 있다.
"""

import re
from dataclasses import dataclass
from functools import lru_cache

from app.agents.prompts import load_yaml
from app.privacy import find_pii

_CITATION = re.compile(r"\[\d{1,2}\]")
_DATE = re.compile(r"\d{4}[-./]\d{1,2}[-./]\d{1,2}")
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


def _norm_num(int_part: str, frac: str | None, unit: str | None) -> str:
    n = int_part.replace(",", "")
    if frac:
        n = f"{n}.{frac}"
    return f"{n}{unit or ''}"


def _canon(int_part: str, frac: str | None) -> str:
    """표기만 다른 같은 값을 하나로: 쉼표·앞자리 0·소수 끝자리 0을 뗀다(0.0500 → 0.05, 36,180.00 → 36180)."""
    n = int_part.replace(",", "").lstrip("0") or "0"
    f = (frac or "").rstrip("0")
    return f"{n}.{f}" if f else n


def extract_numbers(text: str) -> list[str]:
    cfg = _config()["numbers"]
    pat = re.compile(cfg["pattern"])
    text = _CITATION.sub(" ", text)
    text = _DATE.sub(" ", text)
    text = _TICKER.sub(" ", text)
    out = []
    for m in pat.finditer(text):
        int_part, frac, unit = m.group(1), m.group(2), m.group(3)
        if cfg.get("require_unit_or_decimal", True) and not (unit or frac):
            continue
        out.append(_norm_num(int_part, frac, unit))
    return out


def ungrounded_numbers(answer: str, evidence: list[str]) -> list[str]:
    """답변 수치 중 근거 텍스트에 없는 것. 단위 없이 숫자만 일치해도 근거로 인정한다.

    값으로 비교한다: 근거가 '0.0500%'·'36,180.00원'이면 답변의 '0.05%'·'36,180원'도 근거가 있다.
    """
    cfg = _config()["numbers"]
    if not cfg.get("enabled", True):
        return []
    allow = {a.replace(" ", "") for a in cfg.get("allow", [])}
    ev_text = " ".join(evidence)
    ev_nums = set()
    for m in re.finditer(r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?", ev_text):
        ev_nums.add(_canon(m.group(1), m.group(2)))
    missing = []
    for n in extract_numbers(answer):
        int_part, _, frac = re.sub(r"[^\d.]", "", n).partition(".")
        if n in allow or _canon(int_part, frac) in ev_nums:
            continue
        missing.append(n)
    return list(dict.fromkeys(missing))


def check_rules(
    body: str,
    *,
    included_disclaimers: list[str],
    required_disclaimers: list[str],
    evidence: list[str],
    check_numbers: bool = True,
) -> list[str]:
    reasons = find_banned(body) + find_ranking(body)
    reasons += [
        f"missing_disclaimer:{d}" for d in required_disclaimers if d not in included_disclaimers
    ]
    if _config().get("pii", {}).get("enabled", True):
        reasons += [f"pii:{k}" for k in find_pii(body)]
    if check_numbers:
        reasons += [f"ungrounded_number:{n}" for n in ungrounded_numbers(body, evidence)]
    return reasons


def clear_cache() -> None:
    _config.cache_clear()
    _banned.cache_clear()
    _ranking.cache_clear()
    _quoted_mention.cache_clear()

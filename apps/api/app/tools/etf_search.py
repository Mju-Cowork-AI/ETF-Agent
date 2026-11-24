"""ETF 검색·필터 도구(분류, 기초지수, 보수 범위). # P1-AG-03"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import etf as etf_repo
from app.repositories.models import EtfMaster

# ---------- 보수 조건 ----------
# '보수|수수료|비용' 뒤에 이어지는 수치를 읽는다. 비교어는 수치 바로 뒤에 붙지 않아도 된다
# ('0.3%를 초과하는', '0.3%가 넘는', '0.5%보다 더 낮은'): 수치 뒤의 짧은 구간에서 찾는다.
_FEE_KEY = re.compile(r"보수|수수료|비용")
_PCT = r"(?:%|퍼센트|프로)"
_NUM = r"\d+(?:\.\d+)?"
_FEE_NUM = re.compile(rf"({_NUM})\s*({_PCT})?")
# 범위 표기: 0.1~0.3%, 0.1%-0.3%, 0.1%에서 0.3% 사이, 0.1%부터 0.3%까지
_FEE_RANGE = re.compile(rf"({_NUM})\s*{_PCT}?\s*(?:~|-|에서|부터)\s*({_NUM})\s*{_PCT}")
# 비교어 → (max|min, 경계 제외 여부)
_FEE_OPS: list[tuple[re.Pattern[str], tuple[str, bool]]] = [
    (re.compile(r"이하|이내"), ("max", False)),
    (re.compile(r"이상"), ("min", False)),
    (re.compile(r"미만|밑|아래|낮|작[은게아]|적[은게]|싼|저렴"), ("max", True)),
    (re.compile(r"초과|넘|높|큰|많[은이]|비싼"), ("min", True)),
]
# 수치와 보수 표현 사이에 이 말이 끼면 그 수치는 보수가 아니다('수수료 싼 배당률 4% 이상')
_OTHER_METRIC = re.compile(
    r"배당|분배|수익|괴리|금리|순자산|거래량|가격|시세|종가|nav", re.IGNORECASE
)
# 비교어를 찾는 구간은 다음 수치나 대상 명사 앞에서 끊는다('0.3% ETF 중 순자산 많은')
_OP_STOP = re.compile(r"\d|etf|이티에프|상품|펀드|,|이고|면서", re.IGNORECASE)
_FEE_FIRST_GAP = 12  # 보수 표현과 첫 수치 사이
_FEE_NEXT_GAP = 8  # 두 번째 조건('0.1% 이상 0.3% 이하')까지
_OP_WINDOW = 10  # 수치 뒤에서 비교어를 찾는 길이


def _fee_op(tail: str) -> tuple[str, bool] | None:
    """수치 뒤 구간에서 가장 먼저 나오는 비교어."""
    if stop := _OP_STOP.search(tail):
        tail = tail[: stop.start()]
    found = [(m.start(), op) for pat, op in _FEE_OPS if (m := pat.search(tail))]
    return min(found)[1] if found else None


def _parse_fee(text: str, f: EtfFilters) -> None:
    key = _FEE_KEY.search(text)
    if key is None:
        return
    pos, gap = key.end(), _FEE_FIRST_GAP
    while (m := _FEE_NUM.search(text, pos)) is not None:
        between = text[pos : m.start()]
        if len(between) > gap or _OTHER_METRIC.search(between):
            return
        if r := _FEE_RANGE.match(text, m.start()):
            low, high = sorted((Decimal(r.group(1)), Decimal(r.group(2))))
            f.min_fee, f.min_exclusive = low, False
            f.max_fee, f.max_exclusive = high, False
            return
        op = _fee_op(text[m.end() : m.end() + _OP_WINDOW])
        if op is None:
            if not m.group(2):
                return  # 단위도 비교어도 없다: '보수 낮은 순으로 3개'의 3
            op = ("max", False)  # '보수 0.3% ETF'는 0.3% 이하로 본다
        side, exclusive = op
        if side == "max":
            f.max_fee, f.max_exclusive = Decimal(m.group(1)), exclusive
        else:
            f.min_fee, f.min_exclusive = Decimal(m.group(1)), exclusive
        pos, gap = m.end(), _FEE_NEXT_GAP


# 질문 표현 → etf_master.category 부분 문자열
_CATEGORY = [
    ("레버리지", "레버리지"),
    ("인버스", "레버리지·인버스"),
    ("채권", "채권"),
    ("배당", "배당"),
    ("원자재", "원자재"),
    ("금리", "단기금리"),
    ("파킹", "단기금리"),
    ("리츠", "부동산"),
    ("부동산", "부동산"),
    ("테마", "테마"),
    ("업종", "업종"),
    ("자산배분", "자산배분"),
    ("tdf", "자산배분"),
    ("주식", "주식"),
]


REGIONS = etf_repo.REGION_PREFIXES


@dataclass(slots=True)
class EtfFilters:
    category: str | None = None
    region: str | None = None  # 국내 | 해외
    underlying_index: str | None = None
    max_fee: Decimal | None = None
    min_fee: Decimal | None = None
    max_exclusive: bool = False  # 미만(경계값 제외)
    min_exclusive: bool = False  # 초과(경계값 제외)
    sort: str | None = None  # 정렬 기준(SORT_LABELS의 키). 없으면 총보수 낮은 순
    sort_desc: bool = False

    def has_fee(self) -> bool:
        return self.max_fee is not None or self.min_fee is not None

    def is_empty(self) -> bool:
        # 보수 0도 조건이다(Decimal(0)은 거짓이라 값의 참거짓으로 보면 안 된다).
        # 정렬만 있어도('실부담비용 순서대로') 전체 상품을 그 기준으로 보여 주는 조건 검색이다.
        return (
            not any((self.category, self.region, self.underlying_index, self.sort))
            and self.max_fee is None
            and self.min_fee is None
        )

    def sort_key(self) -> str:
        return self.sort or "total_expense_ratio"

    def sort_label(self) -> str:
        """'실부담비용 낮은 순'처럼 정렬 기준과 방향."""
        name, low, high = SORT_LABELS[self.sort_key()]
        return f"{name} {high if self.sort_desc else low} 순"

    def describe(self) -> str:
        parts = []
        if self.region:
            parts.append(self.region)
        if self.category:
            parts.append(f"분류 '{self.category}'")
        if self.underlying_index:
            parts.append(f"기초지수 '{self.underlying_index}'")
        if self.max_fee is not None:
            parts.append(f"총보수 {self.max_fee}% {'미만' if self.max_exclusive else '이하'}")
        if self.min_fee is not None:
            parts.append(f"총보수 {self.min_fee}% {'초과' if self.min_exclusive else '이상'}")
        if self.sort:
            parts.append(self.sort_label())
        return ", ".join(parts) or "조건 없음"


# ---------- 정렬 ----------
# 이름 → (표시 이름, 오름차순 표현, 내림차순 표현)
SORT_LABELS = {
    "total_expense_ratio": ("총보수", "낮은", "높은"),
    "actual_expense_ratio": ("실부담비용", "낮은", "높은"),
    "net_assets": ("순자산", "작은", "큰"),
}
# '실부담비용 순서대로', '순자산 큰 순', '총보수가 가장 낮은'
_SORT_METRIC = r"(?P<metric>실부담\s*비용|총\s*보수|보수|순자산|규모)"
_SORT_WORD = re.compile(
    _SORT_METRIC + r"\s*(?:이|가|을|를|의)?\s*(?:(?:가장|제일)\s*)?"
    r"(?P<dir>낮|높|싼|비싼|저렴|크|큰|작|적|많)?[은는게]?\s*"
    r"(?P<order>순서|순위|순으로|순|정렬|차례|것|상품|etf|ETF)?"
)
_DESC_WORDS = ("높", "비싼", "크", "큰", "많")


def _parse_sort(text: str, f: EtfFilters) -> None:
    """정렬 표현이 있으면 기준과 방향을 채운다. 기준 단어만 있고 순서·최상급 표현이 없으면 무시한다."""
    for m in _SORT_WORD.finditer(text):
        direction, order = m.group("dir"), m.group("order")
        superlative = re.search(r"가장|제일", m.group(0))
        if not (
            order in ("순서", "순위", "순으로", "순", "정렬", "차례") or (superlative and direction)
        ):
            continue
        metric = re.sub(r"\s", "", m.group("metric"))
        if metric == "실부담비용":
            f.sort = "actual_expense_ratio"
        elif metric in ("순자산", "규모"):
            f.sort = "net_assets"
        else:
            f.sort = "total_expense_ratio"
        if f.sort == "net_assets":
            # 순자산은 '큰 순'이 기본이다('순자산 순으로' → 큰 순)
            f.sort_desc = not (direction and direction.startswith(("작", "적")))
        else:
            f.sort_desc = bool(direction and direction.startswith(_DESC_WORDS))
        return


def parse_filters(text: str, known_indexes: list[str]) -> EtfFilters:
    f = EtfFilters()
    low = text.lower()
    _parse_fee(text, f)
    _parse_sort(text, f)
    for word, cat in _CATEGORY:
        if word in low:
            f.category = cat
            break
    if "해외" in text or "미국" in text:
        f.region = "해외"
    elif "국내" in text:
        f.region = "국내"
    squashed = re.sub(r"[^0-9a-z가-힣]", "", low)
    for idx in sorted(known_indexes, key=len, reverse=True):
        key = re.sub(r"[^0-9a-z가-힣]", "", idx.lower())
        if len(key) >= 4 and key in squashed:
            f.underlying_index = idx
            break
    return f


def _fee(value: object) -> Decimal | None:
    try:
        d = Decimal(str(value).strip().rstrip("%"))
    except InvalidOperation, ValueError:
        return None
    return d if d.is_finite() and 0 <= d <= 10 else None


def merge_plan_conditions(
    f: EtfFilters, cond: dict[str, object], known_indexes: list[str]
) -> EtfFilters:
    """질문 문장 규칙으로 못 채운 조건만 계획 JSON(etf_search.conditions)으로 채운다.

    규칙이 찾은 값이 우선이다. 계획 값은 DB가 쓰는 값(지역·분류·기초지수 이름·정렬 키)일 때만 받는다.
    모델이 지어낸 분류명으로 검색하면 0건이 나오기 때문이다.
    """
    if not cond:
        return f
    categories = {cat for _, cat in _CATEGORY}
    if f.region is None and cond.get("region") in REGIONS:
        f.region = str(cond["region"])
    if f.category is None and cond.get("category") in categories:
        f.category = str(cond["category"])
    if f.underlying_index is None and cond.get("underlying_index") in known_indexes:
        f.underlying_index = str(cond["underlying_index"])
    if not f.has_fee():
        f.max_fee = _fee(cond["max_fee"]) if cond.get("max_fee") is not None else None
        f.min_fee = _fee(cond["min_fee"]) if cond.get("min_fee") is not None else None
    if f.sort is None and cond.get("sort") in SORT_LABELS:
        f.sort = str(cond["sort"])
        f.sort_desc = cond.get("sort_desc") is True
    return f


def _repo_filters(f: EtfFilters) -> dict[str, object]:
    # 지역은 분류 앞머리('국내 주식 …')로만 알 수 있다. '부동산'·'원자재'처럼 지역 표기가 없는
    # 분류를 함께 물으면('국내 리츠') 지역을 확인할 수 없으므로 그 분류의 상품은 빼지 않는다.
    return {
        "category": f.category,
        "category_prefix": f.region,
        "unprefixed_ok": REGIONS if f.region and f.category else (),
        "underlying_index": f.underlying_index,
        "max_fee": f.max_fee,
        "min_fee": f.min_fee,
        "max_fee_exclusive": f.max_exclusive,
        "min_fee_exclusive": f.min_exclusive,
        "sort": f.sort_key(),
        "descending": f.sort_desc,
    }


async def search(session: AsyncSession, f: EtfFilters, limit: int = 10) -> list[EtfMaster]:
    # 지역도 DB에서 거른다(LIMIT 뒤에 거르면 앞쪽 N건 밖의 일치 상품이 빠진다).
    return await etf_repo.search_etfs(session, **_repo_filters(f), limit=limit)


async def unverifiable_note(session: AsyncSession, f: EtfFilters) -> str:
    """값이 없어 조건을 판단하지 못하고 뺀 상품이 있으면 그 사실을 알리는 문장.

    외부 수집으로 들어온 상품은 분류·총보수가 없고, '부동산'·'원자재' 같은 분류는 지역을 알 수 없다.
    말없이 빼면 '조건에 맞는 상품은 이것뿐'으로 읽힌다. 확인된 값으로 탈락한 상품은 세지 않는다.
    """
    args = {k: v for k, v in _repo_filters(f).items() if k not in ("sort", "descending")}
    n = await etf_repo.count_unverifiable(session, **args)
    if not n:
        return ""
    used = (
        ("지역", f.region),
        ("분류", f.category),
        ("기초지수", f.underlying_index),
        ("총보수", f.has_fee()),
    )
    names = "·".join(name for name, on in used if on)
    return f"조건({names}) 가운데 정보가 없어 확인할 수 없는 항목이 있는 상품 {n}개는 결과에서 뺐습니다."


def region_unverified(f: EtfFilters, etfs: list[EtfMaster]) -> list[EtfMaster]:
    """지역 조건을 걸었지만 분류에 지역 표기가 없어 지역을 확인하지 못한 채 결과에 넣은 상품.

    search()는 '국내 리츠'처럼 지역과 분류를 함께 물으면 '부동산'·'원자재' 같은 분류를 빼지 않는다.
    """
    if not (f.region and f.category):
        return []
    return [e for e in etfs if not (e.category or "").startswith(REGIONS)]

from __future__ import annotations

import re

from dart_app.utils.text import clean_text

PUBLIC_OFFER_MARKERS = (
    "공모", "사모", "공 사모", "공/사모", "청약", "모집", "원금지급형", "원금보장형",
    "원금비보장형", "고위험", "저위험", "온라인전용", "디지털전용",
)


def normalize_stock_name_text(stock_name):
    text = _normalize_round_text(stock_name)
    text = re.sub(r"^[A-Z]{2}[A-Z0-9]{10}\s+", "", text.strip(), flags=re.I)
    text = re.sub(r"[\[\]{}]", " ", text)
    return clean_text(text)

def _strip_stock_noise(text):
    out = normalize_stock_name_text(text)
    for word in PUBLIC_OFFER_MARKERS:
        out = re.sub(rf"(?<![가-힣A-Za-z]){re.escape(word)}(?![가-힣A-Za-z])", " ", out, flags=re.I)
    return clean_text(out.strip(" -_/·,"))

def _normalize_round_value(value):
    value = _normalize_round_text(value)
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"-+", "-", value)
    value = value.strip("-")
    if not value:
        return ""
    parts = value.split("-")
    if parts and parts[0].isdigit():
        parts[0] = parts[0].lstrip("0") or "0"
    if len(parts) > 1 and parts[1].isdigit():
        parts[1] = parts[1].lstrip("0") or "0"
    return "-".join(parts)

def extract_round(stock_name):
    """종목명 안의 회차. '134-1', '제339호', 'DLB 339 공모'를 모두 처리."""
    s = normalize_stock_name_text(stock_name)
    token = r"(\d{1,5}(?:\s*-\s*\d{1,3})?)"
    product = r"(?:\((?:DLB|DLS|ELB|ELS)\)|(?<![A-Za-z])(?:DLB|DLS|ELB|ELS)(?![A-Za-z]))"
    patterns = [
        rf"{product}[^\d]{{0,30}}(?:제\s*)?{token}\s*(?:회|호)?",
        rf"(?:제\s*){token}\s*(?:회|호)",
        rf"{token}\s*(?:회|호)",
        rf"{token}\s*(?:(?:{ '|'.join(re.escape(w) for w in PUBLIC_OFFER_MARKERS) })\s*)*$",
    ]
    matches = []
    for pattern in patterns:
        for m in re.finditer(pattern, s, flags=re.I):
            value = _normalize_round_value(m.group(1))
            if value:
                matches.append((m.start(), value))
        if matches:
            break
    if not matches:
        return (None, None)
    full = matches[-1][1]
    if extract_product_type(stock_name) in ("DLB", "DLS", "ELB", "ELS") and re.fullmatch(r"20\d{2}-\d{1,4}", full):
        return (None, None)
    base = full.split("-")[0]
    return (full, base)

def find_issuer(stock_name, issuers):
    """
    긴 prefix 우선 매핑. 매핑 없으면 종목명에서 회사명 자동 추출.
    예: '아이비케이증권(DLB)450' → '아이비케이증권'
        '메리츠캐피탈 제10회' → '메리츠캐피탈'
    반환: (회사명, 매핑여부)
    """
    items = [(k, v) for k, v in issuers.items()
             if not k.startswith("_") and isinstance(v, str)]
    items.sort(key=lambda x: len(x[0]), reverse=True)
    for prefix, company in items:
        if stock_name.startswith(prefix):
            return (company, True)
        if normalize_stock_name_text(stock_name).replace(" ", "").startswith(prefix.replace(" ", "")):
            return (company, True)

    # fallback: 괄호/숫자 이전까지를 회사명으로 추정
    normalized = _strip_stock_noise(stock_name)
    head = re.split(
        r"\((?:DLB|DLS|ELB|ELS|신종|후[^\)]*)\)|(?<![A-Za-z])(?:DLB|DLS|ELB|ELS)(?![A-Za-z])|(?:제\s*)?\d{1,5}(?:\s*-\s*\d{1,3})?\s*(?:회|호)?",
        normalized,
        maxsplit=1,
        flags=re.I,
    )[0]
    head = _strip_stock_noise(head)
    if head:
        return (head, False)

    m = re.match(r"\s*([A-Za-z가-힣][A-Za-z가-힣\s·&.-]*)", normalized)
    if m:
        return (clean_text(m.group(1)).strip(" -_/·,."), False)
    return (None, False)

def is_subordinated(stock_name):
    """(신종) 또는 (후) 포함 → 신종자본증권."""
    return bool(re.search(r"\((신종|후[^\)]*)\)", stock_name))

def extract_product_type(stock_name):
    """종목명 괄호에서 상품유형 추출. DLB/ELB/DLS/ELS/SUB(신종·후)/None."""
    if is_subordinated(stock_name):
        return "SUB"
    m = re.search(r"\((DLB|DLS|ELB|ELS)\)", stock_name, re.I)
    if not m:
        m = re.search(r"(?<![A-Za-z])(DLB|DLS|ELB|ELS)(?![A-Za-z])", stock_name, re.I)
    return m.group(1).upper() if m else None

def round_in(text, full, base):
    """
    타이틀 매칭. '제2,681회' 쉼표는 무시.
    full 우선, 없으면 base로 fallback. base는 세부회차(-1,-2) 타이틀도 허용.
    """
    if not full:
        return False
    t = re.sub(r"(?<=\d),(?=\d)", "", text)  # 매칭용으로만 쉼표 제거
    if re.search(rf"(?<![\d\-]){re.escape(full)}(?!\d)", t):
        return True
    if base and base != full:
        # 앞: 숫자/하이픈 아닌 것,  뒤: 숫자 아닌 것 (하이픈 허용 → '280-1'도 OK)
        if re.search(rf"(?<![\d\-]){re.escape(base)}(?!\d)", t):
            return True
    return False

def _normalize_round_text(text):
    return re.sub(r"(?<=\d),(?=\d)", "", str(text or "")).replace("－", "-").replace("–", "-").replace("—", "-")

def round_in_exact(text, full, base=None):
    """
    텀싯 매칭용 엄격 회차 판정.
    280-1 입력에서 280회 단독 표기는 오매칭 방지를 위해 제외한다.
    """
    if not full:
        return False
    t = _normalize_round_text(text)
    full = str(full).strip()
    if "-" not in full:
        return bool(re.search(rf"(?<![\d\-]){re.escape(full)}(?!\d)", t))

    parts = full.split("-", 1)
    if not parts[0] or not parts[1]:
        return bool(re.search(rf"(?<![\d\-]){re.escape(full)}(?!\d)", t))
    base_part, sub_part = map(re.escape, parts)
    patterns = [
        rf"(?<![\d\-]){base_part}\s*-\s*{sub_part}(?!\d)",
        rf"(?<![\d]){base_part}\s*의\s*{sub_part}(?!\d)",
        rf"제?\s*{base_part}\s*회\s*(?:제\s*)?{sub_part}\s*(?:차|호|종|회차)?",
    ]
    return any(re.search(pattern, t) for pattern in patterns)

def expected_product_label(product):
    if product in ("DLB", "ELB"):
        return "기타파생결합사채"
    if product in ("DLS", "ELS"):
        return "기타파생결합증권"
    if product == "SUB":
        return "신종자본증권"
    return ""

def has_wrong_product_label(text, product):
    if product in ("DLB", "ELB"):
        return "기타파생결합증권" in text and "기타파생결합사채" not in text
    if product in ("DLS", "ELS"):
        return "기타파생결합사채" in text and "기타파생결합증권" not in text
    if product == "SUB":
        return "기타파생결합" in text and "신종자본증권" not in text
    return False

def identifier_in_text(text, identifier):
    if not identifier:
        return False
    target = re.sub(r"[^A-Za-z0-9]", "", str(identifier or "")).upper()
    if not target:
        return False
    haystack = re.sub(r"[^A-Za-z0-9]", "", str(text or "")).upper()
    return target in haystack

def product_round_in_text(text, round_full, product=None, stock_name=""):
    """본문용 회차 매칭. 단순 숫자 표 대신 상품명/상품유형 주변의 회차만 인정한다."""
    if not round_full:
        return False
    t = _normalize_round_text(clean_text(text))
    if not t:
        return False
    round_value = _normalize_round_value(round_full)
    if not round_value:
        return False

    product = product or extract_product_type(stock_name)
    expected = expected_product_label(product)
    product_terms = [term for term in [product, expected] if term]
    if product in ("DLB", "ELB"):
        product_terms.extend(["파생결합사채", "기타파생결합사채"])
    elif product in ("DLS", "ELS"):
        product_terms.extend(["파생결합증권", "기타파생결합증권"])
    elif product == "SUB":
        product_terms.extend(["신종자본증권", "후순위", "조건부자본증권"])
    product_terms = sorted(set(product_terms), key=len, reverse=True)

    if "-" in round_value:
        round_patterns = [
            rf"(?:제\s*)?{re.escape(round_value).replace(r'\-', r'\s*-\s*')}\s*(?:호|회)?",
        ]
    else:
        round_patterns = [
            rf"(?:제\s*)?{re.escape(round_value)}\s*(?:호|회)",
            rf"(?:제\s*)?{re.escape(round_value)}(?!\d)",
        ]

    if stock_name:
        normalized_name = normalize_stock_name_text(stock_name)
        name_without_code = re.sub(r"^[A-Z]{2}[A-Z0-9]{10}\s+", "", normalized_name, flags=re.I)
        compact_name = re.sub(r"[\s()]+", "", name_without_code).upper()
        compact_text = re.sub(r"[\s()]+", "", t).upper()
        if compact_name and compact_name in compact_text:
            return True

    for round_pattern in round_patterns:
        for term in product_terms:
            term_pattern = re.escape(term)
            patterns = [
                rf"{term_pattern}[^\n\r]{{0,80}}{round_pattern}",
                rf"{round_pattern}[^\n\r]{{0,80}}{term_pattern}",
            ]
            if any(re.search(pattern, t, flags=re.I) for pattern in patterns):
                return True
    return False

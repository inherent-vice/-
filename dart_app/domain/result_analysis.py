from __future__ import annotations

import re

from dart_app.models import ResultAmount, ResultAnalysis
from dart_app.utils.text import clean_text

def _flex_label(label):
    return r"\s*".join(re.escape(ch) for ch in label.replace(" ", ""))

def _parse_amount_value(raw):
    raw = clean_text(raw)
    if not raw:
        return None
    if raw in ("-", "－", "없음") or "해당사항" in raw or "없습니다" in raw:
        return 0
    m = re.search(r"[0-9][0-9,]*", raw)
    if not m:
        return None
    return int(m.group(0).replace(",", ""))

def extract_allocation_table_amounts(text):
    normalized = clean_text(text)
    start = normalized.find("청약 및 배정현황")
    if start < 0:
        return []
    section = normalized[start:start + 2500]
    row_pattern = re.compile(
        r"(?<!\d)(\d{1,5})\s+"
        r"([0-9][0-9,]*(?:\s*원)?)\s+"
        r"(\d+)\s+"
        r"([0-9][0-9,]*(?:\s*원)?)\s+"
        r"([0-9]+(?:\.\d+)?)\s+"
        r"(\d+)\s+"
        r"([0-9][0-9,]*(?:\s*원)?)\s+"
        r"([0-9]+(?:\.\d+)?)"
    )
    amounts = []
    for m in row_pattern.finditer(section):
        round_no, offer_amount, _sub_count, sub_amount, _sub_rate, _alloc_count, alloc_amount, _alloc_rate = m.groups()
        amounts.extend([
            ResultAmount("회차", _parse_amount_value(round_no), round_no),
            ResultAmount("모집총액", _parse_amount_value(offer_amount), offer_amount),
            ResultAmount("청약금액", _parse_amount_value(sub_amount), sub_amount),
            ResultAmount("배정금액", _parse_amount_value(alloc_amount), alloc_amount),
        ])
    return amounts

def extract_result_amounts(text):
    normalized = clean_text(text)
    labels = [
        "실제 발행액",
        "실제발행액",
        "납입금액",
        "배정금액",
        "총배정금액",
        "청약금액",
        "발행금액",
        "모집 또는 매출총액",
        "모집또는매출총액",
        "모집총액",
        "매출총액",
        "발행총액",
    ]
    amounts = extract_allocation_table_amounts(normalized)
    seen = {(a.name, a.raw, idx) for idx, a in enumerate(amounts)}
    for label in labels:
        pattern = re.compile(_flex_label(label))
        for m in pattern.finditer(normalized):
            window = normalized[m.end():m.end() + 100]
            token = re.search(r"(해당사항\s*없(?:음|습니다)|없(?:음|습니다)|[-－]|[0-9][0-9,]*(?:\s*원)?)", window)
            if not token:
                continue
            raw = clean_text(token.group(1))
            value = _parse_amount_value(raw)
            key = (label.replace(" ", ""), raw, m.start())
            if key in seen:
                continue
            seen.add(key)
            amounts.append(ResultAmount(label.replace(" ", ""), value, raw))
    return amounts

def _find_phrases(text, phrases):
    return [phrase for phrase in phrases if phrase in text]

def analyze_result_text(text):
    """
    Return structured issuance-result analysis.
    status ∈ {'cancelled','issued','partial','unknown'}
    """
    normalized = clean_text(text)
    if not normalized:
        return ResultAnalysis(
            "unknown",
            "알 수 없음",
            "낮음",
            "분석할 본문 텍스트가 없습니다",
            ["본문 텍스트 없음"],
            [],
        )

    issued_phrases = _find_phrases(normalized, [
        "전량 배정",
        "전량배정",
        "배정되었습니다",
        "납입이 완료",
        "발행이 완료",
        "발행 완료",
    ])
    partial_phrases = _find_phrases(normalized, [
        "일부 배정",
        "일부배정",
        "부분 배정",
        "부분발행",
        "일부만 발행",
        "청약 미달",
        "모집한도금액에 미달",
        "모집금액의 100%에 미달",
        "모집금액 미달",
        "모집금액에 미달",
        "초과하지 아니하여 전액 배정",
    ])

    amounts = extract_result_amounts(normalized)
    primary_names = {"실제발행액", "납입금액", "배정금액", "총배정금액", "발행금액"}
    primary = [a for a in amounts if a.name in primary_names and a.value is not None]
    positive = [a for a in primary if a.value and a.value > 0]
    zero = [a for a in primary if a.value == 0]
    strong_cancel_phrases = _find_phrases(normalized, [
        "발행이 취소되었습니다",
        "발행이 취소되었",
        "발행을 취소하였습니다",
        "발행을 취소합니다",
        "발행하지 않기로",
        "모집 또는 매출실적이 없습니다",
        "모집ㆍ매출실적이 없습니다",
        "모집매출실적이 없습니다",
        "청약 미달로 인하여 발행하지",
    ])
    generic_cancel_phrases = _find_phrases(normalized, [
        "발행이 취소",
        "발행취소",
        "발행을 취소",
    ])
    cancel_phrases = strong_cancel_phrases or ([] if positive else generic_cancel_phrases)

    evidence = []
    evidence.extend(f"취소 문구: {p}" for p in cancel_phrases[:3])
    evidence.extend(f"발행 문구: {p}" for p in issued_phrases[:3])
    evidence.extend(f"부분발행 문구: {p}" for p in partial_phrases[:3])
    evidence.extend(f"{a.name}={a.raw}" for a in primary[:5])

    if cancel_phrases and positive:
        return ResultAnalysis(
            "unknown",
            "알 수 없음",
            "낮음",
            "취소 문구와 양수 발행금액이 함께 확인되어 수동 확인이 필요합니다",
            evidence,
            amounts,
        )
    if cancel_phrases:
        return ResultAnalysis(
            "cancelled",
            "발행취소",
            "높음",
            f"취소 문구 확인: {cancel_phrases[0]}",
            evidence,
            amounts,
        )
    if zero and not positive:
        return ResultAnalysis(
            "cancelled",
            "발행취소",
            "높음",
            f"{zero[0].name}=0 확인",
            evidence,
            amounts,
        )
    if positive and partial_phrases:
        return ResultAnalysis(
            "partial",
            "부분발행",
            "중간",
            f"양수 금액과 부분발행 문구 확인: {partial_phrases[0]}",
            evidence,
            amounts,
        )
    if positive:
        return ResultAnalysis(
            "issued",
            "발행됨",
            "높음",
            f"{positive[0].name}={positive[0].raw} 확인",
            evidence,
            amounts,
        )
    if issued_phrases:
        return ResultAnalysis(
            "issued",
            "발행됨",
            "중간",
            f"발행/배정 문구 확인: {issued_phrases[0]}",
            evidence,
            amounts,
        )
    return ResultAnalysis(
        "unknown",
        "알 수 없음",
        "낮음",
        "취소 문구나 발행금액을 안정적으로 확인하지 못했습니다",
        evidence or ["판정 근거 부족"],
        amounts,
    )

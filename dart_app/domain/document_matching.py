from __future__ import annotations

import re
from collections.abc import Callable, Iterable

from dart_app.domain.security_name import (
    has_wrong_product_label,
    identifier_in_text,
    product_round_in_text,
    round_in,
    round_in_exact,
)
from dart_app.models import DocumentCandidateScore, ResultReportMatch, TermsheetMatchResult
from dart_app.utils.pdf import text_to_pdf_bytes
from dart_app.utils.text import clean_text

INDEX_SCAN_LIMIT = 80
PDF_SCAN_LIMIT = 80
RESULT_SCAN_LIMIT = 50


def termsheet_keywords(product):
    common = ["일괄신고추가서류", "투자설명서"]
    if product in ("DLB", "ELB"):
        return common + [product, "기타파생결합사채", "파생결합사채"]
    if product in ("DLS", "ELS"):
        return common + [product, "기타파생결합증권", "파생결합증권"]
    if product == "SUB":
        return common + ["신종자본증권", "조건부자본증권", "후순위"]
    return common + ["파생결합", "증권신고서"]


def _contains_any(text: str, words: Iterable[str]) -> bool:
    normalized = clean_text(text).lower()
    return any(str(word).lower() in normalized for word in words if word)


def _product_score(title: str, product: str | None) -> int:
    if not product:
        return 0
    text = clean_text(title)
    if has_wrong_product_label(text, product):
        return -100
    if _contains_any(text, termsheet_keywords(product)):
        return 30
    return 0


def termsheet_candidates(pairs, product):
    candidates = []
    for order, (rcp, title) in enumerate(pairs):
        score = 100 - order
        title_text = clean_text(title)
        if _contains_any(title_text, ["일괄신고추가서류", "투자설명서", "증권신고서"]):
            score += 20
        score += _product_score(title_text, product)
        candidates.append((rcp, title, score))
    candidates.sort(key=lambda item: item[2], reverse=True)
    return candidates


def _round_matches(text: str, round_full: str | None, round_base: str | None, *, exact: bool) -> bool:
    if not round_full:
        return False
    if exact:
        return round_in_exact(text, round_full, round_base)
    return round_in(text, round_full, round_base)


def _reject(rcp, title, priority, source, reason, dcm_no=None, evidence=None):
    return DocumentCandidateScore(
        rcp_no=rcp,
        title=title,
        score=max(0, int(priority or 0)),
        grade="제외",
        source=source,
        evidence=list(evidence or []),
        reject_reason=reason,
        dcm_no=dcm_no,
    )


def _confirmed(rcp, title, score, source, dcm_no=None, evidence=None, grade="확정"):
    return DocumentCandidateScore(
        rcp_no=rcp,
        title=title,
        score=int(score),
        grade=grade,
        source=source,
        evidence=list(evidence or []),
        reject_reason="",
        dcm_no=dcm_no,
    )


def classify_termsheet_candidate(
    rcp,
    title,
    priority,
    product,
    round_full,
    round_base,
    dcm_no=None,
    titles=None,
    body="",
    stock_code="",
    stock_name="",
):
    title = clean_text(title)
    titles = [clean_text(item) for item in (titles or []) if clean_text(item)]
    body = clean_text(body)
    combined = " ".join([title, *titles, body])

    if product and has_wrong_product_label(combined, product):
        return _reject(
            rcp,
            title,
            priority,
            "title",
            "상품유형 불일치",
            dcm_no=dcm_no,
            evidence=[f"expected={product}"],
        )

    if stock_code and identifier_in_text(body, stock_code):
        return _confirmed(
            rcp,
            title,
            170 + int(priority or 0),
            "identifier",
            dcm_no=dcm_no,
            evidence=[f"종목코드 {stock_code} 본문 일치"],
        )

    if round_full:
        if _round_matches(title, round_full, round_base, exact=True):
            return _confirmed(
                rcp,
                title,
                140 + int(priority or 0),
                "title",
                dcm_no=dcm_no,
                evidence=[f"제{round_full}회 제목 일치"],
            )

        for doc_title in titles:
            if _round_matches(doc_title, round_full, round_base, exact=True):
                return _confirmed(
                    rcp,
                    title,
                    130 + int(priority or 0),
                    "index",
                    dcm_no=dcm_no,
                    evidence=[f"제{round_full}회 문서목차 일치: {doc_title}"],
                )

        if body and (
            product_round_in_text(body, round_full, product, stock_name)
            or _round_matches(body, round_full, round_base, exact=True)
        ):
            return _confirmed(
                rcp,
                title,
                120 + int(priority or 0),
                "body",
                dcm_no=dcm_no,
                evidence=[f"제{round_full}회 본문 일치"],
            )

        return _reject(
            rcp,
            title,
            priority,
            "title",
            f"회차 {round_full} 불일치",
            dcm_no=dcm_no,
            evidence=[f"target_round={round_full}"],
        )

    if product and (_contains_any(combined, termsheet_keywords(product)) or _contains_any(body, [product])):
        return _confirmed(
            rcp,
            title,
            90 + int(priority or 0),
            "title",
            dcm_no=dcm_no,
            evidence=["상품유형 문구 일치"],
            grade="검토필요",
        )

    return _reject(rcp, title, priority, "title", "회차/종목코드 근거 없음", dcm_no=dcm_no)


def match_termsheet(pairs, round_full, round_base, product):
    for rcp, title, priority in termsheet_candidates(pairs, product):
        candidate = classify_termsheet_candidate(rcp, title, priority, product, round_full, round_base)
        if candidate.grade == "확정" and candidate.source == "title":
            return rcp, title, False
    return None, None, False


def _candidate_dicts(candidates):
    return [candidate.to_dict() for candidate in candidates]


def _download_pdf(download_pdf: Callable, rcp_no, dcm_no):
    if not rcp_no or not dcm_no:
        return None
    try:
        return download_pdf(rcp_no, dcm_no)
    except Exception:
        return None


def _pdf_or_text_fallback(download_pdf: Callable, rcp_no, dcm_no, title, body):
    pdf = _download_pdf(download_pdf, rcp_no, dcm_no)
    fallback = False
    if not pdf and clean_text(body):
        pdf = _text_fallback_pdf(rcp_no, dcm_no, title, body)
        fallback = bool(pdf)
    return pdf, fallback


def _text_fallback_pdf(rcp_no, dcm_no, title, body):
    if not clean_text(body):
        return None
    note = f"DART 원본 PDF 다운로드 실패. 공식 공시 본문 기반 대체 PDF입니다. rcpNo={rcp_no} dcmNo={dcm_no or ''}"
    return text_to_pdf_bytes(title or rcp_no, body, note=note)


def _add_pdf_fallback_evidence(candidate, fallback):
    if fallback:
        candidate.evidence.append("DART 원본 PDF 차단: 공식 본문 기반 대체 PDF 생성")


def _safe_doc_info(get_doc_info, rcp_no):
    try:
        dcm_no, titles = get_doc_info(rcp_no)
        return dcm_no, titles or [], None
    except Exception as exc:
        return None, [], f"{type(exc).__name__}: {exc}"


def _safe_text(get_text, *args):
    if not get_text:
        return ""
    try:
        return get_text(*args) or ""
    except Exception:
        return ""


def _result_body_text(get_document_text, get_front_text, rcp_no, dcm_no):
    body = _safe_text(get_document_text, rcp_no) if get_document_text else ""
    if not body and dcm_no:
        body = _safe_text(get_front_text, rcp_no, dcm_no)
    return body


def find_termsheet_document(
    pairs,
    round_full,
    round_base,
    product,
    get_doc_info,
    download_pdf,
    get_front_text,
    get_document_text=None,
    stock_code="",
    stock_name="",
    log=None,
):
    candidates = termsheet_candidates(pairs, product)
    scored: list[DocumentCandidateScore] = []

    if get_document_text and stock_code:
        for rcp, title, priority in candidates[:PDF_SCAN_LIMIT]:
            body = _safe_text(get_document_text, rcp)
            candidate = classify_termsheet_candidate(
                rcp,
                title,
                priority,
                product,
                round_full,
                round_base,
                body=body,
                stock_code=stock_code,
                stock_name=stock_name,
            )
            if candidate.grade == "확정" and candidate.source == "identifier":
                dcm_no, titles, doc_error = _safe_doc_info(get_doc_info, rcp)
                if doc_error:
                    scored.append(_reject(rcp, title, priority, "index", f"목차 조회 실패: {doc_error}"))
                    continue
                pdf, fallback = _pdf_or_text_fallback(download_pdf, rcp, dcm_no, title, body)
                _add_pdf_fallback_evidence(candidate, fallback)
                candidate.dcm_no = dcm_no
                return TermsheetMatchResult(
                    rcp,
                    title,
                    dcm_no,
                    pdf,
                    candidate.source,
                    None if pdf else "PDF 응답 비정상",
                    candidate.score,
                    candidate.grade,
                    candidate.evidence,
                    _candidate_dicts([candidate, *scored]),
                )
            scored.append(candidate)

    title_scored = []
    for rcp, title, priority in candidates:
        candidate = classify_termsheet_candidate(rcp, title, priority, product, round_full, round_base)
        title_scored.append(candidate)
        if candidate.grade == "확정" and candidate.source == "title":
            dcm_no, titles, doc_error = _safe_doc_info(get_doc_info, rcp)
            if doc_error:
                title_scored.append(_reject(rcp, title, priority, "index", f"목차 조회 실패: {doc_error}"))
                continue
            pdf = _download_pdf(download_pdf, rcp, dcm_no)
            fallback = False
            if not pdf:
                body = _safe_text(get_front_text, rcp, dcm_no)
                pdf = _text_fallback_pdf(rcp, dcm_no, title, body)
                fallback = bool(pdf)
                _add_pdf_fallback_evidence(candidate, fallback)
            candidate.dcm_no = dcm_no
            return TermsheetMatchResult(
                rcp,
                title,
                dcm_no,
                pdf,
                "title",
                None if pdf else "PDF 응답 비정상",
                candidate.score,
                candidate.grade,
                candidate.evidence,
                _candidate_dicts([candidate, *title_scored]),
            )

    index_scored = []
    for rcp, title, priority in candidates[:INDEX_SCAN_LIMIT]:
        dcm_no, titles, doc_error = _safe_doc_info(get_doc_info, rcp)
        if doc_error:
            index_scored.append(_reject(rcp, title, priority, "index", f"목차 조회 실패: {doc_error}"))
            continue
        candidate = classify_termsheet_candidate(
            rcp,
            title,
            priority,
            product,
            round_full,
            round_base,
            dcm_no=dcm_no,
            titles=titles,
        )
        index_scored.append(candidate)
        if candidate.grade == "확정" and candidate.source == "index":
            pdf = _download_pdf(download_pdf, rcp, dcm_no)
            fallback = False
            if not pdf:
                body = _safe_text(get_front_text, rcp, dcm_no)
                pdf = _text_fallback_pdf(rcp, dcm_no, title, body)
                fallback = bool(pdf)
                _add_pdf_fallback_evidence(candidate, fallback)
            return TermsheetMatchResult(
                rcp,
                title,
                dcm_no,
                pdf,
                "index",
                None if pdf else "PDF 응답 비정상",
                candidate.score,
                candidate.grade,
                candidate.evidence,
                _candidate_dicts([candidate, *title_scored, *index_scored]),
            )

    body_scored = []
    for rcp, title, priority in candidates[:PDF_SCAN_LIMIT]:
        dcm_no, titles, doc_error = _safe_doc_info(get_doc_info, rcp)
        if doc_error:
            body_scored.append(_reject(rcp, title, priority, "body", f"목차 조회 실패: {doc_error}"))
            continue
        if not dcm_no:
            continue
        body = _safe_text(get_front_text, rcp, dcm_no)
        candidate = classify_termsheet_candidate(
            rcp,
            title,
            priority,
            product,
            round_full,
            round_base,
            dcm_no=dcm_no,
            titles=titles,
            body=body,
            stock_code=stock_code,
            stock_name=stock_name,
        )
        body_scored.append(candidate)
        if candidate.grade == "확정" and candidate.source in ("body", "identifier"):
            pdf, fallback = _pdf_or_text_fallback(download_pdf, rcp, dcm_no, title, body)
            _add_pdf_fallback_evidence(candidate, fallback)
            return TermsheetMatchResult(
                rcp,
                title,
                dcm_no,
                pdf,
                candidate.source,
                None if pdf else "PDF 응답 비정상",
                candidate.score,
                candidate.grade,
                candidate.evidence,
                _candidate_dicts([candidate, *title_scored, *index_scored, *body_scored]),
            )

    target = round_full or stock_code or "대상"
    all_scores = title_scored or index_scored or body_scored or scored
    return TermsheetMatchResult(
        None,
        None,
        None,
        None,
        "not_found",
        f"회차 {target} 일치 문서를 찾지 못했습니다",
        0,
        "제외",
        [f"target={target}"],
        _candidate_dicts(all_scores),
    )


def _is_result_report_title(title):
    compact = re.sub(r"\s+", "", clean_text(title))
    return "발행실적보고서" in compact


def match_result(pairs, round_full, round_base):
    for rcp, title in pairs:
        if not _is_result_report_title(title):
            continue
        if not round_full or round_in(title, round_full, round_base):
            return rcp, title
    return None, None


def _classify_result_candidate(rcp, title, priority, round_full, round_base, dcm_no=None, titles=None, body="", product=None, stock_code="", stock_name=""):
    title = clean_text(title)
    titles = [clean_text(item) for item in (titles or []) if clean_text(item)]
    body = clean_text(body)
    combined = " ".join([title, *titles, body])

    if not _is_result_report_title(combined):
        return _reject(rcp, title, priority, "title", "발행실적보고서 아님", dcm_no=dcm_no)

    if stock_code and identifier_in_text(body, stock_code):
        return _confirmed(rcp, title, 160 + int(priority or 0), "identifier", dcm_no=dcm_no, evidence=[f"종목코드 {stock_code} 본문 일치"], grade="검토필요")

    if round_full:
        if round_in(title, round_full, round_base):
            return _confirmed(rcp, title, 130 + int(priority or 0), "title", dcm_no=dcm_no, evidence=[f"회차 {round_full} 제목 일치"], grade="검토필요")
        for doc_title in titles:
            if round_in(doc_title, round_full, round_base):
                return _confirmed(rcp, title, 120 + int(priority or 0), "index", dcm_no=dcm_no, evidence=[f"회차 {round_full} 문서목차 일치"], grade="검토필요")
        if body and (
            product_round_in_text(body, round_full, product, stock_name)
            or round_in(body, round_full, round_base)
        ):
            return _confirmed(rcp, title, 115 + int(priority or 0), "body", dcm_no=dcm_no, evidence=[f"회차 {round_full} 본문 일치"], grade="검토필요")
        return _reject(rcp, title, priority, "title", f"회차 {round_full} 불일치", dcm_no=dcm_no)

    return _confirmed(rcp, title, 80 + int(priority or 0), "title", dcm_no=dcm_no, evidence=["발행실적보고서 제목 일치"], grade="검토필요")


def find_result_report_document(
    pairs,
    round_full,
    round_base,
    get_doc_info,
    download_pdf,
    get_front_text,
    get_document_text=None,
    stock_code="",
    stock_name="",
    product=None,
    need_pdf=False,
    log=None,
):
    candidates = [(rcp, title, 100 - order) for order, (rcp, title) in enumerate(pairs)]
    scored: list[DocumentCandidateScore] = []

    for rcp, title, priority in candidates:
        candidate = _classify_result_candidate(rcp, title, priority, round_full, round_base, product=product)
        scored.append(candidate)
        if candidate.grade != "제외" and candidate.source == "title":
            dcm_no, titles, doc_error = _safe_doc_info(get_doc_info, rcp)
            if doc_error:
                scored.append(_reject(rcp, title, priority, "index", f"목차 조회 실패: {doc_error}"))
                continue
            body = _result_body_text(get_document_text, get_front_text, rcp, dcm_no)
            pdf = _download_pdf(download_pdf, rcp, dcm_no) if need_pdf else None
            fallback = False
            if need_pdf and not pdf:
                pdf = _text_fallback_pdf(rcp, dcm_no, title, body)
                fallback = bool(pdf)
                _add_pdf_fallback_evidence(candidate, fallback)
            return ResultReportMatch(rcp, title, dcm_no, pdf, body, "title", None, candidate.score, candidate.grade, candidate.evidence, _candidate_dicts([candidate, *scored]))

    for rcp, title, priority in candidates[:INDEX_SCAN_LIMIT]:
        dcm_no, titles, doc_error = _safe_doc_info(get_doc_info, rcp)
        if doc_error:
            scored.append(_reject(rcp, title, priority, "index", f"목차 조회 실패: {doc_error}"))
            continue
        candidate = _classify_result_candidate(
            rcp,
            title,
            priority,
            round_full,
            round_base,
            dcm_no=dcm_no,
            titles=titles,
            product=product,
        )
        scored.append(candidate)
        if candidate.grade != "제외" and candidate.source == "index":
            body = _result_body_text(get_document_text, get_front_text, rcp, dcm_no)
            pdf = _download_pdf(download_pdf, rcp, dcm_no) if need_pdf else None
            fallback = False
            if need_pdf and not pdf:
                pdf = _text_fallback_pdf(rcp, dcm_no, title, body)
                fallback = bool(pdf)
                _add_pdf_fallback_evidence(candidate, fallback)
            return ResultReportMatch(rcp, title, dcm_no, pdf, body, "index", None, candidate.score, candidate.grade, candidate.evidence, _candidate_dicts([candidate, *scored]))

    if get_document_text:
        for rcp, title, priority in candidates[:RESULT_SCAN_LIMIT]:
            body = _safe_text(get_document_text, rcp)
            candidate = _classify_result_candidate(
                rcp,
                title,
                priority,
                round_full,
                round_base,
                body=body,
                product=product,
                stock_code=stock_code,
                stock_name=stock_name,
            )
            scored.append(candidate)
            if candidate.grade != "제외" and candidate.source in ("body", "identifier"):
                dcm_no, titles, doc_error = _safe_doc_info(get_doc_info, rcp)
                if doc_error:
                    scored.append(_reject(rcp, title, priority, "index", f"목차 조회 실패: {doc_error}"))
                    continue
                pdf = None
                if need_pdf:
                    pdf, fallback = _pdf_or_text_fallback(download_pdf, rcp, dcm_no, title, body)
                    _add_pdf_fallback_evidence(candidate, fallback)
                candidate.dcm_no = dcm_no
                return ResultReportMatch(rcp, title, dcm_no, pdf, body, candidate.source, None, candidate.score, candidate.grade, candidate.evidence, _candidate_dicts([candidate, *scored]))

    for rcp, title, priority in candidates[:RESULT_SCAN_LIMIT]:
        dcm_no, titles, doc_error = _safe_doc_info(get_doc_info, rcp)
        if doc_error:
            scored.append(_reject(rcp, title, priority, "body", f"목차 조회 실패: {doc_error}"))
            continue
        if not dcm_no:
            continue
        body = _safe_text(get_front_text, rcp, dcm_no)
        candidate = _classify_result_candidate(
            rcp,
            title,
            priority,
            round_full,
            round_base,
            dcm_no=dcm_no,
            titles=titles,
            body=body,
            product=product,
            stock_code=stock_code,
            stock_name=stock_name,
        )
        scored.append(candidate)
        if candidate.grade != "제외" and candidate.source in ("body", "identifier"):
            pdf = None
            if need_pdf:
                pdf, fallback = _pdf_or_text_fallback(download_pdf, rcp, dcm_no, title, body)
                _add_pdf_fallback_evidence(candidate, fallback)
            return ResultReportMatch(rcp, title, dcm_no, pdf, body, candidate.source, None, candidate.score, candidate.grade, candidate.evidence, _candidate_dicts([candidate, *scored]))

    target = round_full or stock_code or "대상"
    return ResultReportMatch(
        None,
        None,
        None,
        None,
        "",
        "not_found",
        f"회차 {target} 일치 발행실적보고서를 찾지 못했습니다",
        0,
        "제외",
        [f"target={target}"],
        _candidate_dicts(scored),
    )

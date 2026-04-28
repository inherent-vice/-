from __future__ import annotations

import datetime as dt
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dart_app.domain.document_matching import find_result_report_document, find_termsheet_document
from dart_app.domain.result_analysis import analyze_result_text
from dart_app.domain.security_name import extract_product_type, extract_round, find_issuer
from dart_app.models import ResultAnalysis
from dart_app.services.document_access import DartDocumentAccess
from dart_app.utils.files import output_pdf_path, stock_output_dir
from dart_app.utils.pdf import analyze_result_pdf


@dataclass(frozen=True)
class RecordWorkflowOptions:
    save_root: Path
    search_days: int
    result_search_days: int
    save_termsheet_pdf: bool = True
    save_result_pdf: bool = True
    auto_result: bool = False
    force_refresh: bool = False


@dataclass(frozen=True)
class RecordContext:
    stock_code: str
    stock_name: str
    issuer: str
    issuer_mapped: bool
    round_full: str | None
    round_base: str | None
    product: str | None


class RecordWorkflow:
    """Process one DART record behind a UI-neutral interface."""

    def __init__(
        self,
        issuers: Mapping[str, str],
        client_factory: Callable[[], Any],
        options: RecordWorkflowOptions,
        update_record: Callable[..., None],
        should_stop: Callable[[], bool] | None = None,
        access_factory: Callable[..., DartDocumentAccess] = DartDocumentAccess,
        today: dt.date | None = None,
    ):
        self.issuers = issuers
        self.client_factory = client_factory
        self.options = options
        self.update_record = update_record
        self.should_stop = should_stop or (lambda: False)
        self.access_factory = access_factory
        self.today = today or dt.date.today()

    def process_record(self, record):
        ctx = self._record_context(record, "검색 중")
        start, end = self._search_range(self.options.search_days)
        result_start, _result_end = self._search_range(self.options.result_search_days)

        client = self.client_factory()
        access = self.access_factory(client, force_refresh=self.options.force_refresh)
        pairs = client.search(ctx.issuer, start, end, force_refresh=self.options.force_refresh)
        self.update_record(ctx.stock_code, ctx.stock_name, status=f"검색 {len(pairs)}건")

        match = find_termsheet_document(
            pairs,
            ctx.round_full,
            ctx.round_base,
            ctx.product,
            access.doc_info,
            access.pdf_for,
            access.front_text,
            get_document_text=access.document_text_callback(),
            stock_code=ctx.stock_code,
            stock_name=ctx.stock_name,
        )
        updates = {
            "official_title": match.title or "",
            "termsheet_status": f"{match.confidence or match.source}: {match.title or match.error or ''}",
            "candidates": match.candidates,
            "status": "텀싯 확인",
        }
        if match.pdf and self.options.save_termsheet_pdf:
            out = output_pdf_path(self.options.save_root, ctx.stock_code, ctx.stock_name)
            out.write_bytes(match.pdf)
            updates["file"] = str(out)
            updates["folder"] = str(out.parent)
            saved_label = "대체 PDF 저장" if uses_pdf_fallback(match) else "저장 완료"
            updates["termsheet_status"] = f"{saved_label}: {match.title or match.rcp_no}"
        elif not match.pdf:
            updates["termsheet_status"] = match.error or "텀싯 미발견"
            updates["status"] = "미발견"
        self.update_record(ctx.stock_code, ctx.stock_name, **updates)

        if self.options.auto_result and not self.should_stop():
            result_pairs = client.search(
                ctx.issuer,
                result_start,
                end,
                report_name="증권발행실적보고서",
                force_refresh=self.options.force_refresh,
            )
            result_match = find_result_report_document(
                result_pairs or pairs,
                ctx.round_full,
                ctx.round_base,
                access.doc_info,
                access.pdf_for,
                access.front_text,
                get_document_text=access.document_text_callback(),
                stock_code=ctx.stock_code,
                stock_name=ctx.stock_name,
                product=ctx.product,
                need_pdf=self.options.save_result_pdf,
            )
            result_updates = result_updates_for_match(result_match)
            result_updates["status"] = "완료" if match.pdf else "검토필요"
            self._save_result_pdf(ctx, result_match, result_updates)
            self.update_record(ctx.stock_code, ctx.stock_name, **result_updates)
        elif match.pdf:
            self.update_record(ctx.stock_code, ctx.stock_name, status="완료")

        return ctx.stock_code, ctx.stock_name, bool(match.pdf)

    def process_result_record(self, record):
        ctx = self._record_context(record, "발행실적 검색 중")
        start, end = self._search_range(self.options.result_search_days)

        client = self.client_factory()
        access = self.access_factory(client, force_refresh=self.options.force_refresh)
        pairs = client.search(
            ctx.issuer,
            start,
            end,
            report_name="증권발행실적보고서",
            force_refresh=self.options.force_refresh,
        )

        result_match = find_result_report_document(
            pairs,
            ctx.round_full,
            ctx.round_base,
            access.doc_info,
            access.pdf_for,
            access.front_text,
            get_document_text=access.document_text_callback(),
            stock_code=ctx.stock_code,
            stock_name=ctx.stock_name,
            product=ctx.product,
            need_pdf=self.options.save_result_pdf,
        )
        updates = result_updates_for_match(result_match)
        updates["status"] = "완료" if result_match.rcp_no else "검토필요"
        self._save_result_pdf(ctx, result_match, updates)
        self.update_record(ctx.stock_code, ctx.stock_name, **updates)
        return ctx.stock_code, ctx.stock_name, bool(result_match.rcp_no)

    def _record_context(self, record, status):
        stock_code, stock_name = record
        issuer, mapped = find_issuer(stock_name, self.issuers)
        round_full, round_base = extract_round(stock_name)
        product = extract_product_type(stock_name)
        self.update_record(
            stock_code,
            stock_name,
            issuer=issuer or "",
            issuer_mapped=mapped,
            round_full=round_full or "",
            round_base=round_base or "",
            product=product or "",
            folder=str(stock_output_dir(self.options.save_root, stock_code)),
            status=status,
        )
        if not issuer:
            raise RuntimeError("발행사를 찾지 못했습니다")
        return RecordContext(
            stock_code=stock_code,
            stock_name=stock_name,
            issuer=issuer,
            issuer_mapped=mapped,
            round_full=round_full,
            round_base=round_base,
            product=product,
        )

    def _search_range(self, days):
        start = (self.today - dt.timedelta(days=days)).strftime("%Y%m%d")
        end = self.today.strftime("%Y%m%d")
        return start, end

    def _save_result_pdf(self, ctx: RecordContext, result_match, updates):
        if not (result_match.pdf and self.options.save_result_pdf):
            return
        out = output_pdf_path(
            self.options.save_root,
            ctx.stock_code,
            ctx.stock_name,
            suffix="_발행실적",
        )
        out.write_bytes(result_match.pdf)
        updates["result_file"] = str(out)
        updates["folder"] = str(out.parent)
        if uses_pdf_fallback(result_match):
            updates["result_status"] = f"{updates['result_status']} / 대체 PDF"


def result_analysis_for_match(result_match):
    if result_match.text:
        return analyze_result_text(result_match.text)
    if result_match.pdf:
        return analyze_result_pdf(result_match.pdf)
    return ResultAnalysis(
        "unknown",
        "알 수 없음",
        "낮음",
        result_match.error or "발행실적보고서 미발견",
        [result_match.error or "발행실적보고서 미발견"],
        [],
    )


def result_updates_for_match(result_match):
    analysis = result_analysis_for_match(result_match)
    return {
        "official_title": result_match.title or "",
        "result_status": f"{analysis.label}({analysis.confidence})",
        "result_label": analysis.label,
        "result_confidence": analysis.confidence,
        "result_reason": analysis.reason,
        "result_evidence": analysis.evidence,
        "result_candidates": result_match.candidates,
    }


def uses_pdf_fallback(match):
    evidence = getattr(match, "evidence", None) or []
    candidates = getattr(match, "candidates", None) or []
    candidate_evidence = []
    for candidate in candidates:
        candidate_evidence.extend(candidate.get("evidence") or [])
    return any("대체 PDF" in str(item) for item in [*evidence, *candidate_evidence])

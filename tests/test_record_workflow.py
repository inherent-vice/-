from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dart_app.models import ResultReportMatch
from dart_app.services.document_access import DartDocumentAccess, RunDocumentCache
from dart_app.services.record_workflow import (
    RecordWorkflow,
    RecordWorkflowOptions,
    RunSearchCache,
    result_analysis_for_match,
)


class FakeAccess:
    def __init__(self, client, force_refresh=False, **_kwargs):
        self.client = client
        self.force_refresh = force_refresh

    def doc_info(self, rcp_no):
        return "12345678", ["제280회 투자설명서"]

    def pdf_for(self, rcp_no, dcm_no):
        if rcp_no == "20260424000001":
            return b"%PDF-termsheet"
        if rcp_no == "20260425000001":
            return b"%PDF-result"
        return None

    def front_text(self, rcp_no, dcm_no):
        if rcp_no == "20260425000001":
            return "증권발행실적보고서 납입금액 : 10,000원"
        return ""

    def document_text_callback(self):
        return None


class FakeClient:
    def __init__(self):
        self.search_calls = []

    def search(self, company, start, end, report_name="", force_refresh=False):
        self.search_calls.append((company, start, end, report_name, force_refresh))
        if report_name == "증권발행실적보고서":
            return [("20260425000001", "증권발행실적보고서 제280회")]
        return [("20260424000001", "일괄신고추가서류(기타파생결합사채) 제280회")]


class RecordWorkflowTests(unittest.TestCase):
    def test_process_record_saves_termsheet_and_auto_result(self):
        client = FakeClient()
        updates = []

        with TemporaryDirectory() as tmp:
            workflow = RecordWorkflow(
                {"ABC": "ABC"},
                lambda: client,
                RecordWorkflowOptions(
                    save_root=Path(tmp),
                    search_days=30,
                    result_search_days=60,
                    save_termsheet_pdf=True,
                    save_result_pdf=True,
                    auto_result=True,
                    force_refresh=False,
                ),
                lambda code, name, **data: updates.append((code, name, data)),
                access_factory=FakeAccess,
                today=dt.date(2026, 4, 28),
            )

            result = workflow.process_record(("KR6ABC000001", "ABC(DLB)280"))
            pdfs = sorted(path.name for path in Path(tmp).rglob("*.pdf"))

        self.assertEqual(result, ("KR6ABC000001", "ABC(DLB)280", True))
        self.assertEqual(
            client.search_calls,
            [
                ("ABC", "20260329", "20260428", "", False),
                ("ABC", "20260227", "20260428", "증권발행실적보고서", False),
            ],
        )
        self.assertEqual(
            pdfs,
            [
                "KR6ABC000001_ABC(DLB)280.pdf",
                "KR6ABC000001_ABC(DLB)280_발행실적.pdf",
            ],
        )
        self.assertTrue(any(data.get("termsheet_status", "").startswith("저장 완료") for *_rest, data in updates))
        self.assertTrue(any("발행됨" in data.get("result_status", "") for *_rest, data in updates))

    def test_process_record_skips_auto_result_when_stop_requested(self):
        client = FakeClient()
        updates = []

        with TemporaryDirectory() as tmp:
            workflow = RecordWorkflow(
                {"ABC": "ABC"},
                lambda: client,
                RecordWorkflowOptions(
                    save_root=Path(tmp),
                    search_days=30,
                    result_search_days=60,
                    save_termsheet_pdf=False,
                    save_result_pdf=True,
                    auto_result=True,
                    force_refresh=True,
                ),
                lambda code, name, **data: updates.append((code, name, data)),
                should_stop=lambda: True,
                access_factory=FakeAccess,
                today=dt.date(2026, 4, 28),
            )

            result = workflow.process_record(("KR6ABC000001", "ABC(DLB)280"))

        self.assertEqual(result, ("KR6ABC000001", "ABC(DLB)280", True))
        self.assertEqual(client.search_calls, [("ABC", "20260329", "20260428", "", True)])
        self.assertFalse(any("result_status" in data for *_rest, data in updates))

    def test_search_cache_deduplicates_duplicate_record_searches(self):
        client = FakeClient()
        updates = []

        with TemporaryDirectory() as tmp:
            workflow = RecordWorkflow(
                {"ABC": "ABC"},
                lambda: client,
                RecordWorkflowOptions(
                    save_root=Path(tmp),
                    search_days=30,
                    result_search_days=60,
                    save_termsheet_pdf=False,
                    save_result_pdf=False,
                    auto_result=True,
                    force_refresh=True,
                ),
                lambda code, name, **data: updates.append((code, name, data)),
                access_factory=FakeAccess,
                search_cache=RunSearchCache(),
                today=dt.date(2026, 4, 28),
            )

            workflow.process_record(("KR6ABC000001", "ABC(DLB)280"))
            workflow.process_record(("KR6ABC000002", "ABC(DLB)280"))

        self.assertEqual(
            client.search_calls,
            [
                ("ABC", "20260329", "20260428", "", True),
                ("ABC", "20260227", "20260428", "증권발행실적보고서", True),
            ],
        )

    def test_search_cache_can_be_shared_across_workflows(self):
        client = FakeClient()
        search_cache = RunSearchCache()

        with TemporaryDirectory() as tmp:
            options = RecordWorkflowOptions(
                save_root=Path(tmp),
                search_days=30,
                result_search_days=60,
                save_termsheet_pdf=False,
                save_result_pdf=False,
                auto_result=False,
                force_refresh=False,
            )
            for code in ("KR6ABC000001", "KR6ABC000002"):
                workflow = RecordWorkflow(
                    {"ABC": "ABC"},
                    lambda: client,
                    options,
                    lambda *_args, **_kwargs: None,
                    access_factory=FakeAccess,
                    search_cache=search_cache,
                    today=dt.date(2026, 4, 28),
                )
                workflow.process_record((code, "ABC(DLB)280"))

        self.assertEqual(client.search_calls, [("ABC", "20260329", "20260428", "", False)])

    def test_search_cache_retries_after_failed_load(self):
        class FlakyClient:
            def __init__(self):
                self.calls = 0

            def search(self, *_args, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("temporary")
                return [("20260424000001", "투자설명서 제280회")]

        client = FlakyClient()
        cache = RunSearchCache()

        with self.assertRaises(RuntimeError):
            cache.search(client, "ABC", "20260329", "20260428")

        self.assertEqual(cache.search(client, "ABC", "20260329", "20260428"), [("20260424000001", "투자설명서 제280회")])
        self.assertEqual(client.calls, 2)

    def test_document_cache_can_be_shared_across_workflows(self):
        class FakeOpenDart:
            def enabled(self):
                return False

        class Client:
            def __init__(self):
                self.opendart = FakeOpenDart()
                self.search_calls = []
                self.index_calls = []
                self.pdf_calls = []

            def search(self, company, start, end, report_name="", force_refresh=False):
                self.search_calls.append((company, start, end, report_name, force_refresh))
                return [("20260424000001", "일괄신고추가서류(기타파생결합사채) 제280회")]

            def get_index_html(self, rcp_no):
                self.index_calls.append(rcp_no)
                return "index html"

            def parse_doc_info(self, html):
                return "12345678", ["제280회 투자설명서"]

            def download_pdf(self, rcp_no, dcm_no):
                self.pdf_calls.append((rcp_no, dcm_no))
                return b"%PDF-shared"

        client = Client()
        search_cache = RunSearchCache()
        document_cache = RunDocumentCache()

        with TemporaryDirectory() as tmp:
            options = RecordWorkflowOptions(
                save_root=Path(tmp),
                search_days=30,
                result_search_days=60,
                save_termsheet_pdf=False,
                save_result_pdf=False,
                auto_result=False,
                force_refresh=False,
            )
            for code in ("KR6ABC000001", "KR6ABC000002"):
                workflow = RecordWorkflow(
                    {"ABC": "ABC"},
                    lambda: client,
                    options,
                    lambda *_args, **_kwargs: None,
                    access_factory=DartDocumentAccess,
                    search_cache=search_cache,
                    document_cache=document_cache,
                    today=dt.date(2026, 4, 28),
                )
                workflow.process_record((code, "ABC(DLB)280"))

        self.assertEqual(client.index_calls, ["20260424000001"])
        self.assertEqual(client.pdf_calls, [("20260424000001", "12345678")])


class ResultAnalysisForMatchTests(unittest.TestCase):
    def _empty_match(self, error):
        return ResultReportMatch(
            rcp_no=None,
            title=None,
            dcm_no=None,
            pdf=None,
            text="",
            source="not_found",
            error=error,
        )

    def test_not_found_match_uses_미확인_label(self):
        analysis = result_analysis_for_match(
            self._empty_match("회차 528 일치 발행실적보고서를 찾지 못했습니다")
        )
        self.assertEqual(analysis.status, "unknown")
        self.assertEqual(analysis.label, "발행실적 미확인")
        self.assertEqual(analysis.confidence, "낮음")

    def test_unknown_error_keeps_알수없음_label(self):
        analysis = result_analysis_for_match(self._empty_match("PDF 파싱 오류"))
        self.assertEqual(analysis.status, "unknown")
        self.assertEqual(analysis.label, "알 수 없음")


if __name__ == "__main__":
    unittest.main()

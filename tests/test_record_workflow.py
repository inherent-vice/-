from __future__ import annotations

import datetime as dt
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dart_app.services.record_workflow import RecordWorkflow, RecordWorkflowOptions


class FakeAccess:
    def __init__(self, client, force_refresh=False):
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


if __name__ == "__main__":
    unittest.main()

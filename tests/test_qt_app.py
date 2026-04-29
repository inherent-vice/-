from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false")
if os.environ.get("QT_QPA_PLATFORM") == "offscreen" and not os.environ.get("QT_QPA_FONTDIR"):
    windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    if windows_fonts.exists():
        os.environ["QT_QPA_FONTDIR"] = str(windows_fonts)

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - only used when optional Qt dependency is absent
    QApplication = None

from dart_app.qt_app.theme import app_stylesheet
from dart_app.services.record_workflow import RecordWorkflowOptions


@unittest.skipIf(QApplication is None, "PySide6 is not installed")
class QtAppSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_preview_records_populates_model(self):
        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            window.input_text.setPlainText("KR6ABC000001  ABC(DLB)280")
            records = window.preview_records()

            self.assertEqual(records, [("KR6ABC000001", "ABC(DLB)280")])
            self.assertEqual(window.model.rowCount(), 1)
            record = window.model.record_at(0)
            self.assertEqual(record["stock_code"], "KR6ABC000001")
            self.assertEqual(record["round_full"], "280")
            self.assertEqual(record["product"], "DLB")
            self.assertIn("DLB 1", window.input_summary_label.text())
            self.assertTrue(window.table_hint_label.isHidden())
        finally:
            window.close()

    def test_load_input_file_previews_and_summarizes_records(self):
        from dart_app.qt_app.app import MainWindow

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.txt"
            path.write_text(
                "KR6ABC000001  ABC(DLB)280\nKR6ABC000002  ABC(DLS)281\n",
                encoding="utf-8",
            )
            window = MainWindow()
            try:
                records = window.load_input_file(path)

                self.assertEqual(records, [("KR6ABC000001", "ABC(DLB)280"), ("KR6ABC000002", "ABC(DLS)281")])
                self.assertEqual(window.model.rowCount(), 2)
                self.assertIn("sample.txt", window.input_summary_label.text())
                self.assertIn("DLB 1", window.input_summary_label.text())
                self.assertIn("DLS 1", window.input_summary_label.text())
            finally:
                window.close()

    def test_large_input_summary_includes_runtime_hint(self):
        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            rows = [{"product": "DLB", "issuer_mapped": True} for _ in range(300)]

            summary = window._records_summary(rows)

            self.assertIn("대상 300건", summary)
            self.assertIn("예상 최소", summary)
        finally:
            window.close()

    def test_termsheet_summary_marks_non_target_products(self):
        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            rows = [
                {"product": "DLB", "issuer_mapped": True},
                {"product": "DLS", "issuer_mapped": True},
                {"product": "", "issuer_mapped": True},
            ]

            summary = window._records_summary(rows)

            self.assertIn("텀싯 처리 2/3", summary)
            self.assertIn("기타 제외 1", summary)
        finally:
            window.close()

    def test_termsheet_run_filters_non_target_rows(self):
        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            window.model.set_records([
                {"stock_code": "KR6ABC000001", "stock_name": "ABC(DLB)280", "product": "DLB"},
                {"stock_code": "KR310515GG42", "stock_name": "기업은행(변)2604이275A-28", "product": ""},
            ])

            records = window._records_or_preview(mode="termsheet")

            self.assertEqual(records, [("KR6ABC000001", "ABC(DLB)280")])
            excluded = window.model.record_at(1)
            self.assertEqual(excluded["status"], "제외")
            self.assertEqual(excluded["termsheet_status"], "상품 유형 제외")
        finally:
            window.close()

    def test_run_uses_only_checked_target_rows(self):
        from PySide6.QtCore import Qt

        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            window.model.set_records([
                {"stock_code": "KR6ABC000001", "stock_name": "ABC(DLB)280", "product": "DLB"},
                {"stock_code": "KR6ABC000002", "stock_name": "ABC(DLB)281", "product": "DLB"},
            ])
            self.assertEqual(window.model.headerData(0, Qt.Horizontal), "대상")

            window.model.setData(window.model.index(1, 0), Qt.Unchecked, Qt.CheckStateRole)
            records = window._records_or_preview(mode="termsheet")

            self.assertEqual(records, [("KR6ABC000001", "ABC(DLB)280")])
            self.assertIn("대상 1/2건", window.input_summary_label.text())
        finally:
            window.close()

    def test_status_updates_do_not_recompute_input_summary(self):
        from PySide6.QtCore import Qt

        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            window.model.set_records([
                {"stock_code": "KR6ABC000001", "stock_name": "ABC(DLB)280", "product": "DLB", "target": True},
            ])
            calls = []
            window._set_input_summary = lambda rows: calls.append(list(rows))

            window.model.upsert("KR6ABC000001", "ABC(DLB)280", {"status": "검색 중"})
            self.assertEqual(calls, [])

            window.model.setData(window.model.index(0, 0), Qt.Unchecked, Qt.CheckStateRole)
            self.assertEqual(len(calls), 1)
        finally:
            window.close()

    def test_preview_marks_non_target_rows_as_pending_exclusion(self):
        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            window.input_text.setPlainText("KR310515GG42  기업은행(변)2604이275A-28")

            window.preview_records()

            row = window.model.record_at(0)
            self.assertEqual(row["status"], "제외 예정")
            self.assertEqual(row["termsheet_status"], "상품 유형 제외 예정")
        finally:
            window.close()

    def test_opendart_key_is_masked_by_default(self):
        from PySide6.QtWidgets import QLineEdit

        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            self.assertEqual(window.opendart_key_edit.echoMode(), QLineEdit.Password)
        finally:
            window.close()

    def test_advanced_controls_are_collapsible(self):
        from PySide6.QtWidgets import QScrollArea

        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            self.assertIsNotNone(window.findChild(QScrollArea, "LeftRailScroll"))
            self.assertIs(window.left_scroll, window.findChild(QScrollArea, "LeftRailScroll"))
            self.assertTrue(window.advanced_controls.isHidden())

            window.advanced_toggle_button.setChecked(True)
            self.assertFalse(window.advanced_controls.isHidden())

            window.advanced_toggle_button.setChecked(False)
            self.assertTrue(window.advanced_controls.isHidden())
        finally:
            window.close()

    def test_log_panel_is_collapsible(self):
        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            self.assertTrue(window.log_panel.isHidden())

            window.log("sample")
            self.assertIn("sample", window.log_text.toPlainText())

            window.log_toggle_button.setChecked(True)
            self.assertFalse(window.log_panel.isHidden())
        finally:
            window.close()

    def test_cache_policy_controls_are_saved(self):
        from unittest.mock import patch

        from dart_app import config, state
        from dart_app.qt_app.app import MainWindow

        with tempfile.TemporaryDirectory() as tmp, patch.object(config, "SETTINGS_PATH", Path(tmp) / "settings.json"):
            window = MainWindow()
            try:
                window.cache_auto_prune_check.setChecked(False)
                window.cache_search_days_spin.setValue(5)
                window.cache_document_days_spin.setValue(45)
                window.cache_pdf_days_spin.setValue(15)
                window.search_cache_hours_spin.setValue(3)
                window.result_scan_limit_spin.setValue(55)
                window.result_body_scan_limit_spin.setValue(33)
                window.result_front_text_scan_limit_spin.setValue(22)

                window.save_settings(show_message=False)
                settings = state.load_settings()

                self.assertFalse(settings["cache_auto_prune"])
                self.assertEqual(settings["cache_search_days"], 5)
                self.assertEqual(settings["cache_document_days"], 45)
                self.assertEqual(settings["cache_pdf_days"], 15)
                self.assertEqual(settings["search_cache_hours"], 3)
                self.assertEqual(settings["result_scan_limit"], 55)
                self.assertEqual(settings["result_body_scan_limit"], 33)
                self.assertEqual(settings["result_front_text_scan_limit"], 22)
            finally:
                window.close()

    def test_save_root_display_compacts_long_unc_path(self):
        from dart_app.qt_app.app import MainWindow

        path = r"\\10.10.10.11\파생상품평가본부\B.구조화평가팀\2_Term Sheet 모음\금리구조화채권"
        window = MainWindow()
        try:
            window._set_save_root(path)

            self.assertEqual(str(window.current_save_root()), path)
            self.assertTrue(window.save_root_edit.isHidden())
            self.assertIn("금리구조화채권", window.save_root_display.text())
            self.assertNotIn("10.10.10.11", window.save_root_display.text())
            self.assertEqual(window.save_root_display.toolTip(), path)
        finally:
            window.close()

    def test_candidate_detail_collapses_large_reject_list(self):
        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            candidates = [
                {
                    "rcp_no": "20260424000000",
                    "title": "투자설명서(일괄신고)",
                    "grade": "확정",
                    "source": "body",
                    "score": 260,
                    "evidence": ["제280회 본문 일치"],
                    "reject_reason": "",
                }
            ]
            candidates.extend(
                {
                    "rcp_no": f"2026042400{i:04d}",
                    "title": "투자설명서(일괄신고)",
                    "grade": "제외",
                    "source": "title",
                    "score": 100 - i,
                    "evidence": ["target_round=280"],
                    "reject_reason": "회차 280 불일치",
                }
                for i in range(100)
            )
            window.model.set_records([
                {
                    "stock_code": "KR6ABC000001",
                    "stock_name": "ABC(DLB)280",
                    "status": "완료",
                    "termsheet_status": "저장 완료",
                    "candidates": candidates,
                }
            ])
            window.table.selectRow(0)
            window._refresh_detail()

            self.assertEqual(window.candidate_table.rowCount(), 80)
            self.assertEqual(window.candidate_table.horizontalHeaderItem(0).text(), "판정")
            self.assertIn("전체 101", window.candidate_summary_label.text())
            self.assertIn("접힘", window.candidate_summary_label.text())
        finally:
            window.close()

    def test_candidate_detail_includes_result_candidates(self):
        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            window.model.set_records([
                {
                    "stock_code": "KR6ABC000001",
                    "stock_name": "ABC(DLB)280",
                    "status": "검토필요",
                    "result_status": "발행실적 미확인(낮음)",
                    "result_candidates": [
                        {
                            "rcp_no": "20260425000001",
                            "title": "증권발행실적보고서 제279회",
                            "grade": "제외",
                            "source": "title",
                            "score": 100,
                            "evidence": ["target_round=280"],
                            "reject_reason": "회차 280 불일치",
                        }
                    ],
                }
            ])
            window.table.selectRow(0)
            window._refresh_detail()

            self.assertEqual(window.candidate_table.rowCount(), 1)
            self.assertEqual(window.candidate_table.item(0, 3).text(), "증권발행실적보고서 제279회")
            self.assertIn("전체 1", window.candidate_summary_label.text())
        finally:
            window.close()

    def test_empty_detail_guides_next_action(self):
        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            window._refresh_detail()

            self.assertIn("입력 정리", window.result_detail.toPlainText())
            self.assertEqual(window.candidate_table.rowCount(), 1)
            self.assertIn("입력 정리", window.candidate_table.item(0, 0).text())
            self.assertFalse(window.table_hint_label.isHidden())
            self.assertFalse(window.open_file_button.isEnabled())
            self.assertFalse(window.open_folder_button.isEnabled())
            self.assertTrue(window.open_file_button.isHidden())
            self.assertTrue(window.open_folder_button.isHidden())
        finally:
            window.close()

    def test_cache_label_can_call_out_largest_group(self):
        from dart_app.qt_app.app import MainWindow

        window = MainWindow()
        try:
            label = window._dominant_cache_group_summary(
                {
                    "groups": {
                        "search": {"files": 3, "bytes": 128},
                        "pdf": {"files": 4, "bytes": 2 * 1024 * 1024},
                    }
                }
            )

            self.assertIn("PDF", label)
            self.assertIn("4", label)
            self.assertIn("2.0 MB", label)
        finally:
            window.close()

    def test_stylesheet_contains_warm_editorial_tokens(self):
        sheet = app_stylesheet()

        self.assertIn("#faf9f5", sheet)
        self.assertIn("#cc785c", sheet)
        self.assertIn("#181715", sheet)

    def test_stylesheet_marks_disabled_primary_and_danger_buttons(self):
        sheet = app_stylesheet()

        self.assertIn("QPushButton#PrimaryButton:disabled", sheet)
        self.assertIn("QPushButton#DangerButton:disabled", sheet)

    def test_workflow_runnable_finishes_after_bad_record(self):
        from dart_app.qt_app.app import WorkflowRunnable

        worker = WorkflowRunnable(
            records=[("KR6BADONLY",)],
            issuers={},
            options=RecordWorkflowOptions(
                save_root=Path("."),
                search_days=30,
                result_search_days=60,
                save_termsheet_pdf=False,
                save_result_pdf=False,
            ),
            use_opendart=False,
            opendart_api_key="",
            stop_event=type("Stop", (), {"is_set": lambda self: False})(),
        )
        logs = []
        progress = []
        finished = []
        worker.signals.log.connect(logs.append)
        worker.signals.progress.connect(progress.append)
        worker.signals.finished.connect(lambda completed, failed: finished.append((completed, failed)))

        worker.run()

        self.assertEqual(progress, [False])
        self.assertEqual(finished, [(0, 1)])
        self.assertIn("잘못된 입력 레코드", logs[0])


if __name__ == "__main__":
    unittest.main()

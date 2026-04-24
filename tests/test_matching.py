import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import requests

import dart_auto as d


class ParsingTests(unittest.TestCase):
    def test_parse_input_line_splits_code_and_name(self):
        self.assertEqual(
            d.parse_input_line("KR6HN0008746  하나증권(DLB)2681"),
            ("KR6HN0008746", "하나증권(DLB)2681"),
        )

    def test_parse_input_lines_pairs_code_name_lines(self):
        lines = [
            "KR6MZ0005MV0",
            "메리츠증권(DLB)3667",
            "KR6MZ0005MW8",
            "메리츠증권(DLB)3668",
            "KR6MZ0005MX6",
            "메리츠증권(DLB)3669",
            "KR6MZ0005MY4",
            "메리츠증권(DLB)3670",
        ]
        self.assertEqual(
            d.parse_input_lines(lines),
            [
                ("KR6MZ0005MV0", "메리츠증권(DLB)3667"),
                ("KR6MZ0005MW8", "메리츠증권(DLB)3668"),
                ("KR6MZ0005MX6", "메리츠증권(DLB)3669"),
                ("KR6MZ0005MY4", "메리츠증권(DLB)3670"),
            ],
        )

    def test_extract_round_keeps_sub_round(self):
        self.assertEqual(d.extract_round("미래에셋캐피탈134-1"), ("134-1", "134"))

    def test_product_type_detects_derivative_and_subordinated(self):
        self.assertEqual(d.extract_product_type("하나증권(DLB)2681"), "DLB")
        self.assertEqual(d.extract_product_type("교보증권(신종)12회"), "SUB")

    def test_find_issuer_prefers_longest_prefix(self):
        self.assertEqual(
            d.find_issuer("미래에셋캐피탈134-1", d.DEFAULT_ISSUERS),
            ("미래에셋캐피탈", True),
        )


class MatchingTests(unittest.TestCase):
    def test_round_in_rejects_embedded_numbers(self):
        self.assertFalse(d.round_in("제1280회", "280", "280"))
        self.assertFalse(d.round_in("제2800회", "280", "280"))
        self.assertTrue(d.round_in("제280회", "280", "280"))

    def test_round_in_handles_commas_and_sub_round_base(self):
        self.assertTrue(d.round_in("제2,681회 투자설명서", "2681", "2681"))
        self.assertTrue(d.round_in("제280-1회", "280-1", "280"))
        self.assertTrue(d.round_in("제280회", "280-1", "280"))

    def test_match_result_does_not_fallback_to_wrong_round(self):
        pairs = [
            ("20260424000001", "증권발행실적보고서 제281회"),
            ("20260423000001", "증권발행실적보고서 제279회"),
        ]
        self.assertEqual(d.match_result(pairs, "280", "280"), (None, None))

    def test_match_result_returns_matching_round(self):
        pairs = [
            ("20260424000001", "증권발행실적보고서 제281회"),
            ("20260423000001", "증권발행실적보고서 제280회"),
        ]
        self.assertEqual(
            d.match_result(pairs, "280", "280"),
            ("20260423000001", "증권발행실적보고서 제280회"),
        )

    def test_match_termsheet_respects_product_keyword(self):
        pairs = [
            ("20260424000001", "일괄신고추가서류(기타파생결합증권) 제280회"),
            ("20260423000001", "일괄신고추가서류(기타파생결합사채) 제280회"),
        ]
        self.assertEqual(
            d.match_termsheet(pairs, "280", "280", "DLB"),
            ("20260423000001", "일괄신고추가서류(기타파생결합사채) 제280회", False),
        )


class FilePathTests(unittest.TestCase):
    def test_unique_path_adds_suffix_when_file_exists(self):
        def fake_exists(path):
            return path.name == "sample.pdf"

        with patch.object(Path, "exists", fake_exists):
            self.assertEqual(d.unique_path(Path("sample.pdf")), Path("sample_1.pdf"))

    def test_output_pdf_path_uses_stock_code_directory(self):
        with TemporaryDirectory() as tmp:
            out = d.output_pdf_path(Path(tmp), "KR6MZ0005MV0", "메리츠증권(DLB)3667")

            self.assertEqual(out.parent, Path(tmp) / "KR6MZ0005MV0")
            self.assertTrue(out.parent.exists())
            self.assertEqual(out.name, "KR6MZ0005MV0_메리츠증권(DLB)3667.pdf")

    def test_settings_round_trip_save_root(self):
        with TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            save_root = Path(tmp) / "금리구조화채권"

            with patch.object(d, "SETTINGS_PATH", settings_path):
                d.save_settings({"save_root": str(save_root)})
                self.assertEqual(d.get_save_root(), save_root)


class DartParserTests(unittest.TestCase):
    def test_parse_search_results_extracts_rcp_and_title(self):
        html = """
        <a href="#" onclick="openReportViewer('20260424000001')">
          일괄신고추가서류(기타파생결합사채) 제280회
        </a>
        """
        self.assertEqual(
            d.Dart.parse_search_results(html),
            [("20260424000001", "일괄신고추가서류(기타파생결합사채) 제280회")],
        )

    def test_parse_search_results_falls_back_to_rcp_only(self):
        html = "<span>20260424000001</span><span>20260423000001</span>"
        self.assertEqual(
            d.Dart.parse_search_results(html),
            [("20260424000001", ""), ("20260423000001", "")],
        )

    def test_parse_doc_info_extracts_dcm_and_tree_titles(self):
        html = """
        <script>
        var dcmNo = '12345678';
        tree.add('1', '0', '제280회 투자설명서', 'url');
        </script>
        """
        self.assertEqual(
            d.Dart.parse_doc_info(html),
            ("12345678", ["제280회 투자설명서"]),
        )


class DartRequestTests(unittest.TestCase):
    def test_request_retries_after_connection_error(self):
        class Response:
            text = "ok"
            content = b"ok"

            def raise_for_status(self):
                return None

        class FlakySession:
            calls = 0

            def __init__(self):
                self.headers = {}
                self.closed = False

            def request(self, *_args, **_kwargs):
                FlakySession.calls += 1
                if FlakySession.calls == 1:
                    raise requests.ConnectionError("temporary disconnect")
                return Response()

            def close(self):
                self.closed = True

        made = []

        client = d.Dart()

        def make_session():
            session = FlakySession()
            made.append(session)
            return session

        with patch.object(d, "RETRY_BACKOFF", 0):
            client._make_session = make_session
            client.s = make_session()
            response = client._request("GET", "https://example.test")

        self.assertEqual(response.text, "ok")
        self.assertEqual(FlakySession.calls, 3)
        self.assertGreaterEqual(len(made), 2)

    def test_check_status_reports_failures_without_raising(self):
        client = d.Dart()

        def fail_request(*_args, **_kwargs):
            raise requests.ConnectionError("RemoteDisconnected")

        client._request = fail_request
        status = client.check_status()

        self.assertFalse(status["ok"])
        self.assertEqual(status["summary"], "장애 또는 접속 불가")
        self.assertEqual([c["name"] for c in status["checks"]], ["DART 메인", "DART 검색"])
        self.assertTrue(all(not c["ok"] for c in status["checks"]))


if __name__ == "__main__":
    unittest.main()

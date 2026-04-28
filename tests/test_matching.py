import io
import unittest
import zipfile
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

    def test_extract_round_ignores_kb_year_sequence_for_dlb(self):
        self.assertEqual(d.extract_round("KB증권(DLB)2026-852"), (None, None))

    def test_extract_round_handles_product_without_parentheses_and_public_marker(self):
        self.assertEqual(d.extract_product_type("KB able DLB 제339호 공모"), "DLB")
        self.assertEqual(d.extract_round("KB able DLB 제339호 공모"), ("339", "339"))
        self.assertEqual(d.extract_round("하나증권(DLB)0715"), ("715", "715"))

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

    def test_round_in_exact_requires_sub_round_for_termsheet(self):
        self.assertTrue(d.round_in_exact("제280-1회 투자설명서", "280-1", "280"))
        self.assertTrue(d.round_in_exact("제280회 제1차 투자설명서", "280-1", "280"))
        self.assertTrue(d.round_in_exact("제280의1회 투자설명서", "280-1", "280"))
        self.assertFalse(d.round_in_exact("제280회 투자설명서", "280-1", "280"))

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

    def test_classify_termsheet_candidate_scores_confirmed_match(self):
        candidate = d.classify_termsheet_candidate(
            "20260423000001",
            "일괄신고추가서류(기타파생결합사채) 제280회",
            0,
            "DLB",
            "280",
            "280",
            dcm_no="12345678",
            titles=["제280회 투자설명서"],
        )

        self.assertEqual(candidate.grade, "확정")
        self.assertGreaterEqual(candidate.score, 135)
        self.assertEqual(candidate.source, "title")

    def test_classify_termsheet_candidate_rejects_wrong_product(self):
        candidate = d.classify_termsheet_candidate(
            "20260423000001",
            "일괄신고추가서류(기타파생결합증권) 제280회",
            0,
            "DLB",
            "280",
            "280",
            dcm_no="12345678",
        )

        self.assertEqual(candidate.grade, "제외")
        self.assertIn("상품유형 불일치", candidate.reject_reason)

    def test_product_round_in_text_requires_product_context(self):
        self.assertTrue(
            d.product_round_in_text("KB able DLB 제339호 기타파생결합사채", "339", "DLB")
        )
        self.assertFalse(
            d.product_round_in_text("백테스트 표본 339개와 평균값입니다.", "339", "DLB")
        )

    def test_classify_termsheet_candidate_uses_isin_identifier(self):
        candidate = d.classify_termsheet_candidate(
            "20260423000001",
            "일괄신고추가서류(기타파생결합사채)",
            0,
            "DLB",
            None,
            None,
            body="종목코드 KR6KB00086G3 KB able DLB 제339호 기타파생결합사채",
            stock_code="KR6KB00086G3",
        )

        self.assertEqual(candidate.grade, "확정")
        self.assertEqual(candidate.source, "identifier")


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
                d.save_settings({
                    "save_root": str(save_root),
                    "opendart_api_key": " sample-key ",
                    "search_days": 120,
                    "result_search_days": 240,
                    "download_workers": 4,
                    "auto_result": False,
                    "force_refresh": True,
                    "save_termsheet_pdf": False,
                    "save_result_pdf": True,
                    "use_opendart": False,
                })
                self.assertEqual(d.get_save_root(), save_root)
                self.assertEqual(d.get_opendart_api_key(), "sample-key")
                settings = d.load_settings()
                self.assertEqual(settings["search_days"], 120)
                self.assertEqual(settings["result_search_days"], 240)
                self.assertEqual(settings["download_workers"], 4)
                self.assertFalse(settings["auto_result"])
                self.assertTrue(settings["force_refresh"])
                self.assertFalse(settings["save_termsheet_pdf"])
                self.assertTrue(settings["save_result_pdf"])
                self.assertFalse(settings["use_opendart"])

    def test_apply_runtime_settings_updates_globals(self):
        old = d.load_settings()
        try:
            runtime = d.apply_runtime_settings({
                "search_days": 31,
                "result_search_days": 62,
                "download_workers": 2,
                "search_cache_hours": 1,
            })
            self.assertEqual(runtime["search_days"], 31)
            self.assertEqual(d.SEARCH_DAYS, 31)
            self.assertEqual(d.RESULT_SEARCH_DAYS, 62)
            self.assertEqual(d.DOWNLOAD_WORKERS, 2)
            self.assertEqual(d.SEARCH_CACHE_SECONDS, 3600)
        finally:
            d.apply_runtime_settings(old)

    def test_runtime_presets_are_normalized(self):
        for preset in d.RUNTIME_PRESETS.values():
            normalized = d.normalize_runtime_settings(preset)
            self.assertGreaterEqual(normalized["download_workers"], 1)
            self.assertGreaterEqual(normalized["search_days"], 7)
            self.assertIn("auto_result", normalized)
            self.assertIn("save_termsheet_pdf", normalized)
            self.assertIn("save_result_pdf", normalized)
            self.assertIn("use_opendart", normalized)

    def test_clear_cache_removes_only_cache_children(self):
        with TemporaryDirectory() as tmp, patch.object(d, "CACHE_DIR", Path(tmp) / "cache"):
            search_dir = d.CACHE_DIR / "dart_search"
            search_dir.mkdir(parents=True)
            (search_dir / "sample.json").write_text("[]", encoding="utf-8")
            other_dir = d.CACHE_DIR / "dart_pdf"
            other_dir.mkdir(parents=True)
            (other_dir / "sample.pdf").write_bytes(b"%PDF")

            removed = d.clear_cache("search")

            self.assertEqual(removed, 1)
            self.assertFalse(search_dir.exists())
            self.assertTrue((other_dir / "sample.pdf").exists())

    def test_structured_bond_db_row_normalization_and_evidence(self):
        row = d.normalize_structured_bond_row({
            "bond_id": " KR6SH00091L9 ",
            "bond_name": " 신한투자증권(DLB)3883 ",
            "public_flag": "010",
            "bond_type": "21",
            "issue_date": "2026-04-24",
            "due_date": "2029-04-24",
            "underlying_memo": "",
        })

        self.assertEqual(row["bond_name"], "신한투자증권(DLB)3883")
        self.assertIn("PublicFlag=010", d.structured_bond_db_evidence(row))


class OpenDartTests(unittest.TestCase):
    def test_find_corp_code_loads_and_caches_zip_xml(self):
        xml = """
        <result>
          <list><corp_code>00126380</corp_code><corp_name>메리츠증권</corp_name><stock_code>008560</stock_code></list>
        </result>
        """.encode("utf-8")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("CORPCODE.xml", xml)

        class Response:
            content = buf.getvalue()

        with TemporaryDirectory() as tmp, patch.object(d, "CACHE_DIR", Path(tmp)):
            client = d.OpenDart("key")
            calls = []

            def fake_request(endpoint, **_kwargs):
                calls.append(endpoint)
                return Response()

            client._request = fake_request
            self.assertEqual(client.find_corp_code("메리츠증권"), "00126380")
            self.assertEqual(client.find_corp_code("메리츠증권"), "00126380")
            self.assertEqual(calls, ["corpCode.xml"])

    def test_find_corp_code_uses_aliases(self):
        rows = [
            {"corp_code": "00161639", "corp_name": "메리츠종합금융", "stock_code": "012420"},
        ]

        client = d.OpenDart("key")
        client._load_corp_codes = lambda: rows

        self.assertEqual(client.find_corp_code("메리츠증권"), "00161639")

    def test_opendart_search_returns_rcp_and_title_and_uses_cache(self):
        class Response:
            def json(self):
                return {
                    "status": "000",
                    "total_page": 1,
                    "list": [
                        {"rcept_no": "20260424000001", "report_nm": "증권발행실적보고서 제280회"},
                        {"rcept_no": "20260423000001", "report_nm": "타보고서"},
                    ],
                }

        with TemporaryDirectory() as tmp, patch.object(d, "CACHE_DIR", Path(tmp)):
            client = d.OpenDart("key")
            calls = []
            client.find_corp_code = lambda _company: "00126380"

            def fake_request(endpoint, **_kwargs):
                calls.append(endpoint)
                return Response()

            client._request = fake_request
            self.assertEqual(
                client.search("메리츠증권", "20260401", "20260430", report_name="증권발행실적보고서"),
                [("20260424000001", "증권발행실적보고서 제280회")],
            )
            self.assertEqual(
                client.search("메리츠증권", "20260401", "20260430", report_name="증권발행실적보고서"),
                [("20260424000001", "증권발행실적보고서 제280회")],
            )
            self.assertEqual(calls, ["list.json", "list.json"])
            self.assertEqual(
                client.search(
                    "메리츠증권",
                    "20260401",
                    "20260430",
                    report_name="증권발행실적보고서",
                    force_refresh=True,
                ),
                [("20260424000001", "증권발행실적보고서 제280회")],
            )
            self.assertEqual(calls, ["list.json", "list.json", "list.json"])

    def test_opendart_search_scans_market_filings_for_securities_issuer(self):
        class Response:
            def __init__(self, rows):
                self.rows = rows

            def json(self):
                return {
                    "status": "000",
                    "total_page": 1,
                    "list": self.rows,
                }

        rows = [
            {"corp_name": "KB금융", "rcept_no": "20260422000585", "report_nm": "일괄신고추가서류"},
            {"corp_name": "케이비증권", "rcept_no": "20260424000078", "report_nm": "일괄신고추가서류(기타파생결합사채)"},
            {"corp_name": "케이비증권", "rcept_no": "20260424000074", "report_nm": "증권발행실적보고서"},
        ]

        with TemporaryDirectory() as tmp, patch.object(d, "CACHE_DIR", Path(tmp)):
            client = d.OpenDart("key")
            client._request = lambda *_args, **_kwargs: Response(rows)

            self.assertEqual(
                client.search("KB증권", "20260401", "20260430"),
                [
                    ("20260424000078", "일괄신고추가서류(기타파생결합사채)"),
                    ("20260424000074", "증권발행실적보고서"),
                ],
            )
            self.assertEqual(
                client.search("KB증권", "20260401", "20260430", report_name="증권발행실적보고서"),
                [("20260424000074", "증권발행실적보고서")],
            )

    def test_opendart_document_text_extracts_and_caches_zip_xml(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr(
                "document.xml",
                "<html><body><p>KB able DLB 제339호 기타파생결합사채 KR6KB00086G3</p></body></html>",
            )

        class Response:
            content = buf.getvalue()

        with TemporaryDirectory() as tmp, patch.object(d, "CACHE_DIR", Path(tmp)):
            client = d.OpenDart("key")
            calls = []

            def fake_request(endpoint, **_kwargs):
                calls.append(endpoint)
                return Response()

            client._request = fake_request
            self.assertIn("제339호", client.get_document_text("20260417000267"))
            self.assertIn("KR6KB00086G3", client.get_document_text("20260417000267"))
            self.assertEqual(calls, ["document.xml"])


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

    def test_parse_search_results_normalizes_html_entities(self):
        html = """
        <a href="#" onclick="openReportViewer('20260424000001')">
          증권발행실적보고서&nbsp;제280회 &amp; 정정
        </a>
        """
        self.assertEqual(
            d.Dart.parse_search_results(html),
            [("20260424000001", "증권발행실적보고서 제280회 & 정정")],
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

    def test_parse_viewer_params_extracts_initial_view_doc(self):
        html = """
        <script>
        viewDoc("20260414001566", "11325425", "1", "779", "6502", "dart4.xsd", "");
        </script>
        """
        self.assertEqual(
            d.Dart.parse_viewer_params(html, rcp_no="20260414001566"),
            {
                "rcpNo": "20260414001566",
                "dcmNo": "11325425",
                "eleId": "1",
                "offset": "779",
                "length": "6502",
                "dtd": "dart4.xsd",
            },
        )
        self.assertIsNone(
            d.Dart.parse_viewer_params(html, rcp_no="20260414001566", dcm_no="11325426")
        )


class TermsheetDocumentTests(unittest.TestCase):
    def test_find_termsheet_document_uses_title_match(self):
        pairs = [
            ("20260424000001", "일괄신고추가서류(기타파생결합사채) 제280회"),
        ]

        result = d.find_termsheet_document(
            pairs,
            "280",
            "280",
            "DLB",
            lambda rcp: ("12345678", []),
            lambda rcp, dcm: b"%PDF-title",
            lambda rcp, dcm: "",
        )

        self.assertEqual(result.source, "title")
        self.assertEqual(result.rcp_no, "20260424000001")
        self.assertEqual(result.dcm_no, "12345678")
        self.assertEqual(result.pdf, b"%PDF-title")
        self.assertIsNone(result.error)
        self.assertEqual(result.confidence, "확정")
        self.assertGreaterEqual(result.score, 135)
        self.assertEqual(result.candidates[0]["grade"], "확정")

    def test_find_termsheet_document_falls_back_to_index_titles(self):
        pairs = [
            ("20260424000001", "일괄신고추가서류(기타파생결합사채)"),
            ("20260423000001", "일괄신고추가서류(기타파생결합사채)"),
        ]
        doc_calls = []
        pdf_calls = []

        def doc_info(rcp):
            doc_calls.append(rcp)
            if rcp == "20260423000001":
                return "22222222", ["제280회 투자설명서"]
            return "11111111", ["제279회 투자설명서"]

        def download_pdf(rcp, dcm):
            pdf_calls.append((rcp, dcm))
            return b"%PDF-index"

        result = d.find_termsheet_document(
            pairs,
            "280",
            "280",
            "DLB",
            doc_info,
            download_pdf,
            lambda rcp, dcm: "",
        )

        self.assertEqual(result.source, "index")
        self.assertEqual(result.rcp_no, "20260423000001")
        self.assertEqual(result.pdf, b"%PDF-index")
        self.assertEqual(doc_calls, ["20260424000001", "20260423000001"])
        self.assertEqual(pdf_calls, [("20260423000001", "22222222")])

    def test_find_termsheet_document_falls_back_to_pdf_text(self):
        pairs = [
            ("20260424000001", "일괄신고추가서류(기타파생결합사채)"),
        ]

        result = d.find_termsheet_document(
            pairs,
            "280",
            "280",
            "DLB",
            lambda rcp: ("12345678", ["제279회 투자설명서"]),
            lambda rcp, dcm: b"%PDF-body",
            lambda rcp, dcm: "본문에 DLB 제280회 조건이 있습니다.",
        )

        self.assertEqual(result.source, "body")
        self.assertEqual(result.rcp_no, "20260424000001")
        self.assertEqual(result.pdf, b"%PDF-body")

    def test_find_termsheet_document_uses_opendart_text_identifier_before_index_scan(self):
        pairs = [
            ("20260424000002", "일괄신고추가서류(기타파생결합사채)"),
            ("20260424000001", "일괄신고추가서류(기타파생결합사채)"),
        ]
        doc_calls = []

        def doc_info(rcp):
            doc_calls.append(rcp)
            return "12345678", []

        result = d.find_termsheet_document(
            pairs,
            None,
            None,
            "DLB",
            doc_info,
            lambda rcp, dcm: b"%PDF-identifier",
            lambda rcp, dcm: "",
            get_document_text=lambda rcp: "KR6KB00086G3 KB able DLB 제339호" if rcp == "20260424000001" else "",
            stock_code="KR6KB00086G3",
            stock_name="KB증권(DLB)2026-852",
        )

        self.assertEqual(result.source, "identifier")
        self.assertEqual(result.rcp_no, "20260424000001")
        self.assertEqual(doc_calls, ["20260424000001"])

    def test_find_termsheet_document_does_not_fallback_to_newest_without_round(self):
        pairs = [
            ("20260424000001", "일괄신고추가서류(기타파생결합사채)"),
        ]
        pdf_calls = []

        def download_pdf(rcp, dcm):
            pdf_calls.append((rcp, dcm))
            return b"%PDF-wrong"

        result = d.find_termsheet_document(
            pairs,
            "280",
            "280",
            "DLB",
            lambda rcp: ("12345678", ["제279회 투자설명서"]),
            download_pdf,
            lambda rcp, dcm: "본문에도 제279회만 있습니다.",
        )

        self.assertEqual(result.source, "not_found")
        self.assertIsNone(result.rcp_no)
        self.assertIsNone(result.pdf)
        self.assertEqual(pdf_calls, [])
        self.assertIn("회차 280", result.error)
        self.assertEqual(result.candidates[0]["grade"], "제외")

    def test_find_termsheet_document_rejects_base_round_for_sub_round(self):
        pairs = [
            ("20260424000001", "일괄신고추가서류(기타파생결합사채) 제280회"),
        ]

        result = d.find_termsheet_document(
            pairs,
            "280-1",
            "280",
            "DLB",
            lambda rcp: ("12345678", ["제280회 투자설명서"]),
            lambda rcp, dcm: b"%PDF-wrong",
            lambda rcp, dcm: "본문에도 제280회만 있습니다.",
        )

        self.assertEqual(result.source, "not_found")
        self.assertIsNone(result.rcp_no)
        self.assertIsNone(result.pdf)


class ResultAnalysisTests(unittest.TestCase):
    def test_analyze_result_text_detects_cancel_phrase(self):
        result = d.analyze_result_text("본 증권은 청약 미달로 발행이 취소되었습니다.")

        self.assertEqual(result.status, "cancelled")
        self.assertEqual(result.label, "발행취소")
        self.assertEqual(result.confidence, "높음")
        self.assertIn("취소 문구", result.evidence[0])

    def test_analyze_result_text_detects_zero_primary_amounts(self):
        result = d.analyze_result_text("청약금액 : 0원 배정금액 : 0원")

        self.assertEqual(result.status, "cancelled")
        self.assertIn("=0", result.reason)

    def test_analyze_result_text_detects_positive_issue_amount(self):
        result = d.analyze_result_text("납입금액 : 30,000,000,000원 배정되었습니다.")

        self.assertEqual(result.status, "issued")
        self.assertEqual(result.label, "발행됨")
        self.assertEqual(result.amounts[0].value, 30000000000)

    def test_analyze_result_text_detects_partial_issue(self):
        result = d.analyze_result_text("청약 미달로 일부 배정되었습니다. 납입금액 : 10,000원")

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.label, "부분발행")
        self.assertEqual(result.confidence, "중간")

    def test_analyze_result_text_ignores_generic_cancel_heading_when_table_has_positive_amount(self):
        text = (
            "발행취소 등에 관한 사항 "
            "3. 청약 및 배정현황 (단위 : 원, 주, %) "
            "회 차 모집 총액 청약현황 최종배정현황 건수 금액 비율 건수 금액 비율 "
            "530 20,000,000,000 1 4,452,000,000 22.26 1 4,452,000,000 22.26 "
            "공모결과 총 청약금액이 모집금액을 초과하지 아니하여 전액 배정되었습니다."
        )
        result = d.analyze_result_text(text)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.label, "부분발행")

    def test_analyze_result_text_reports_conflict_as_unknown(self):
        result = d.analyze_result_text("발행이 취소되었습니다. 납입금액 : 10,000원")

        self.assertEqual(result.status, "unknown")
        self.assertIn("수동 확인", result.reason)

    def test_find_result_report_document_matches_body_without_pdf_download(self):
        pairs = [("20260424000001", "증권발행실적보고서")]
        pdf_calls = []

        def download_pdf(rcp, dcm):
            pdf_calls.append((rcp, dcm))
            return b"%PDF-result"

        result = d.find_result_report_document(
            pairs,
            "280",
            "280",
            lambda rcp: ("12345678", ["증권발행실적보고서"]),
            download_pdf,
            lambda rcp, dcm: "DLB 제280회 증권발행실적보고서 납입금액 : 10,000원",
            product="DLB",
            need_pdf=False,
        )

        self.assertEqual(result.source, "body")
        self.assertEqual(result.rcp_no, "20260424000001")
        self.assertIsNone(result.pdf)
        self.assertEqual(pdf_calls, [])
        self.assertEqual(result.confidence, "검토필요")
        self.assertEqual(result.candidates[0]["grade"], "검토필요")

    def test_find_result_report_document_keeps_text_when_pdf_not_requested(self):
        pairs = [("20260424000001", "증권발행실적보고서 제280회")]
        pdf_calls = []

        result = d.find_result_report_document(
            pairs,
            "280",
            "280",
            lambda rcp: ("12345678", []),
            lambda rcp, dcm: pdf_calls.append((rcp, dcm)) or b"%PDF-result",
            lambda rcp, dcm: "DLB 제280회 증권발행실적보고서 납입금액 : 10,000원",
            product="DLB",
            need_pdf=False,
        )

        self.assertEqual(result.source, "title")
        self.assertIn("납입금액", result.text)
        self.assertIsNone(result.pdf)
        self.assertEqual(pdf_calls, [])

    def test_find_result_report_document_respects_result_scan_limit(self):
        old_limit = d.RESULT_SCAN_LIMIT
        d.RESULT_SCAN_LIMIT = 1
        document_text_calls = []

        def document_text(rcp):
            document_text_calls.append(rcp)
            if rcp == "20260424000002":
                return "DLB 제280회 증권발행실적보고서 납입금액 : 10,000원"
            return ""

        try:
            result = d.find_result_report_document(
                [
                    ("20260424000001", "기타 보고서"),
                    ("20260424000002", "기타 보고서"),
                ],
                "280",
                "280",
                lambda rcp: ("12345678", []),
                lambda rcp, dcm: b"%PDF-result",
                lambda rcp, dcm: "",
                get_document_text=document_text,
                product="DLB",
                need_pdf=False,
            )
        finally:
            d.RESULT_SCAN_LIMIT = old_limit

        self.assertEqual(result.source, "not_found")
        self.assertEqual(document_text_calls, ["20260424000001"])

    def test_find_result_report_document_returns_rejected_candidates(self):
        pairs = [("20260424000001", "증권발행실적보고서 제279회")]

        result = d.find_result_report_document(
            pairs,
            "280",
            "280",
            lambda rcp: ("12345678", ["증권발행실적보고서 제279회"]),
            lambda rcp, dcm: b"%PDF-result",
            lambda rcp, dcm: "제279회 증권발행실적보고서",
            need_pdf=False,
        )

        self.assertEqual(result.source, "not_found")
        self.assertEqual(result.candidates[0]["grade"], "제외")
        self.assertIn("회차 280", result.candidates[0]["reject_reason"])


class DartRequestTests(unittest.TestCase):
    def test_is_pdf_bytes_rejects_html_responses(self):
        self.assertTrue(d.is_pdf_bytes(b"%PDF-1.7\ncontent"))
        self.assertFalse(d.is_pdf_bytes(b"<html>blocked</html>"))

    def test_download_pdf_rejects_non_pdf_response(self):
        class Response:
            content = b"<html>blocked</html>"

            def raise_for_status(self):
                return None

        with TemporaryDirectory() as tmp, patch.object(d, "CACHE_DIR", Path(tmp)):
            client = d.Dart("")
            client._request = lambda *_args, **_kwargs: Response()

            self.assertIsNone(client.download_pdf("20260424000001", "12345678"))
            self.assertFalse(any(Path(tmp).rglob("*")))

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
        self.assertEqual(FlakySession.calls, 2)
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


class DocumentAccessTests(unittest.TestCase):
    def test_document_access_caches_index_viewer_and_opendart_text(self):
        class FakeOpenDart:
            def __init__(self):
                self.calls = []

            def enabled(self):
                return True

            def get_document_text(self, rcp_no, force_refresh=False):
                self.calls.append((rcp_no, force_refresh))
                return f"document text {rcp_no}"

        class FakeClient:
            def __init__(self):
                self.opendart = FakeOpenDart()
                self.index_calls = []
                self.viewer_calls = []
                self.pdf_calls = []

            def get_index_html(self, rcp_no):
                self.index_calls.append(rcp_no)
                return "index html"

            def parse_doc_info(self, html):
                return "12345678", ["제280회 투자설명서"]

            def get_viewer_text_from_index(self, html, rcp_no, dcm_no):
                self.viewer_calls.append((rcp_no, dcm_no))
                return "viewer text"

            def download_pdf(self, rcp_no, dcm_no):
                self.pdf_calls.append((rcp_no, dcm_no))
                return b"%PDF-1.7\ncontent"

        client = FakeClient()
        access = d.DartDocumentAccess(client, force_refresh=True)

        self.assertEqual(access.doc_info("20260424000001"), ("12345678", ["제280회 투자설명서"]))
        self.assertEqual(access.doc_info("20260424000001"), ("12345678", ["제280회 투자설명서"]))
        self.assertEqual(access.front_text("20260424000001", "12345678"), "viewer text")
        self.assertEqual(access.front_text("20260424000001", "12345678"), "viewer text")
        callback = access.document_text_callback()
        self.assertIsNotNone(callback)
        self.assertEqual(callback("20260424000001"), "document text 20260424000001")
        self.assertEqual(callback("20260424000001"), "document text 20260424000001")

        self.assertEqual(client.index_calls, ["20260424000001"])
        self.assertEqual(client.viewer_calls, [("20260424000001", "12345678")])
        self.assertEqual(client.pdf_calls, [])
        self.assertEqual(client.opendart.calls, [("20260424000001", True)])


if __name__ == "__main__":
    unittest.main()

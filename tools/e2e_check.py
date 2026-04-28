from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dart_auto as d
from dart_app.services.document_access import DartDocumentAccess


DEFAULT_INPUT = """\
KR6MZ0005MV0
메리츠증권(DLB)3667
KR6MZ0005MW8
메리츠증권(DLB)3668
KR6MZ0005MX6
메리츠증권(DLB)3669
KR6MZ0005MY4
메리츠증권(DLB)3670
"""


def find_termsheet(
    access,
    pairs,
    round_full,
    round_base,
    product,
    stock_code,
    stock_name,
):
    match = d.find_termsheet_document(
        pairs,
        round_full,
        round_base,
        product,
        access.doc_info,
        access.pdf_for,
        access.front_text,
        get_document_text=access.document_text_callback(),
        stock_code=stock_code,
        stock_name=stock_name,
    )
    return match.rcp_no, match.title, match.dcm_no, match.pdf, match.source


def find_result_report(
    access,
    pairs,
    stock_code,
    stock_name,
):
    round_full, round_base = d.extract_round(stock_name)
    product = d.extract_product_type(stock_name)

    match = d.find_result_report_document(
        pairs,
        round_full,
        round_base,
        access.doc_info,
        access.pdf_for,
        access.front_text,
        get_document_text=access.document_text_callback(),
        stock_code=stock_code,
        stock_name=stock_name,
        product=product,
        need_pdf=True,
    )
    if not match.rcp_no:
        analysis = d.ResultAnalysis(
            "unknown",
            "알 수 없음",
            "낮음",
            match.error or "발행실적보고서 미게재",
            [match.error or "발행실적보고서 미게재"],
            [],
        )
        return None, None, None, None, analysis
    if match.error:
        analysis = d.ResultAnalysis("unknown", "알 수 없음", "낮음", match.error, [match.error], [])
        return match.rcp_no, match.title, match.dcm_no, match.pdf, analysis
    return match.rcp_no, match.title, match.dcm_no, match.pdf, d.analyze_result_text(match.text)


def run_e2e(input_text, output_dir):
    records = d.parse_input_lines(input_text.splitlines())
    output_dir.mkdir(parents=True, exist_ok=True)
    client = d.Dart()
    access = DartDocumentAccess(client, delay_seconds=d.SLEEP)
    today = dt.date.today()
    start = (today - dt.timedelta(days=d.SEARCH_DAYS)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    search_cache = {}
    failures = 0

    print(f"records={len(records)} output={output_dir}")
    for stock_code, stock_name in records:
        issuer, mapped = d.find_issuer(stock_name, d.DEFAULT_ISSUERS)
        product = d.extract_product_type(stock_name)
        round_full, round_base = d.extract_round(stock_name)
        print(f"\n[{stock_code}] {stock_name}")
        print(f"issuer={issuer} mapped={mapped} product={product} round={round_full}")
        if not issuer or not round_full:
            print("FAIL parse")
            failures += 1
            continue

        try:
            if issuer not in search_cache:
                search_cache[issuer] = client.search(issuer, start, end)
            pairs = search_cache[issuer]
            print(f"search_results={len(pairs)}")

            rcp, title, dcm, pdf, source = find_termsheet(
                access,
                pairs,
                round_full,
                round_base,
                product,
                stock_code,
                stock_name,
            )
            if not pdf:
                print(f"FAIL termsheet source={source} rcp={rcp} title={title}")
                failures += 1
                continue
            out = d.output_pdf_path(output_dir, stock_code, stock_name)
            out.write_bytes(pdf)
            print(f"OK termsheet source={source} rcp={rcp} dcm={dcm} file={out}")

            rr_rcp, rr_title, rr_dcm, rr_pdf, status = find_result_report(
                access,
                pairs,
                stock_code,
                stock_name,
            )
            print(
                f"result_report status={status.label} confidence={status.confidence} "
                f"reason={status.reason} rcp={rr_rcp} dcm={rr_dcm}"
            )
            for evidence in status.evidence[:3]:
                print(f"result_evidence={evidence}")
            if rr_pdf:
                rr_out = d.output_pdf_path(output_dir, stock_code, stock_name, suffix="_발행실적")
                rr_out.write_bytes(rr_pdf)
                print(f"OK result_pdf file={rr_out}")
        except Exception as e:
            print(f"FAIL exception={e}")
            failures += 1

    return failures


def main():
    parser = argparse.ArgumentParser(description="Run real DART end-to-end checks.")
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "e2e_output")
    args = parser.parse_args()
    input_text = args.input_file.read_text(encoding="utf-8") if args.input_file else DEFAULT_INPUT
    failures = run_e2e(input_text, args.output_dir)
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()

from __future__ import annotations

import argparse
import datetime as dt
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import dart_auto as d


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


def find_termsheet(client, pairs, round_full, round_base, product, doc_cache, pdf_cache, text_cache):
    def doc_info(rcp_no):
        if rcp_no not in doc_cache:
            doc_cache[rcp_no] = client.get_doc_info(rcp_no)
            time.sleep(d.SLEEP)
        return doc_cache[rcp_no]

    def pdf_for(rcp_no, dcm_no):
        key = (rcp_no, dcm_no)
        if key not in pdf_cache:
            pdf_cache[key] = client.download_pdf(rcp_no, dcm_no)
            time.sleep(d.SLEEP)
        return pdf_cache[key]

    def front_text(rcp_no, dcm_no):
        key = (rcp_no, dcm_no)
        if key not in text_cache:
            pdf = pdf_for(rcp_no, dcm_no)
            text_cache[key] = d.pdf_front_text(pdf, max_pages=5) if pdf else ""
        return text_cache[key]

    rcp, title, _fb = d.match_termsheet(pairs, round_full, round_base, product)
    pdf = None
    dcm = None
    if rcp:
        dcm, _titles = doc_info(rcp)
        if dcm:
            pdf = pdf_for(rcp, dcm)
        return rcp, title, dcm, pdf, "title"

    cands = d.termsheet_candidates(pairs, product)

    for c_rcp, c_title, _pri in cands[:d.INDEX_SCAN_LIMIT]:
        c_dcm, titles = doc_info(c_rcp)
        if any(d.round_in(t, round_full, round_base) for t in titles):
            pdf = pdf_for(c_rcp, c_dcm) if c_dcm else None
            return c_rcp, c_title, c_dcm, pdf, "index"

    for c_rcp, c_title, _pri in cands[:d.PDF_SCAN_LIMIT]:
        c_dcm, _titles = doc_info(c_rcp)
        if not c_dcm:
            continue
        cand_pdf = pdf_for(c_rcp, c_dcm)
        if cand_pdf and d.round_in(front_text(c_rcp, c_dcm), round_full, round_base):
            return c_rcp, c_title, c_dcm, cand_pdf, "pdf"

    return None, None, None, None, "not_found"


def find_result_report(client, pairs, stock_name):
    round_full, round_base = d.extract_round(stock_name)
    rcp, title = d.match_result(pairs, round_full, round_base)
    if not rcp:
        return None, None, None, None, ("unknown", "알 수 없음", "발행실적보고서 미게재")
    dcm = client.get_dcm_no(rcp)
    if not dcm:
        return rcp, title, None, None, ("unknown", "알 수 없음", "dcm_no 없음")
    pdf = client.download_pdf(rcp, dcm)
    if not pdf:
        return rcp, title, dcm, None, ("unknown", "알 수 없음", "PDF 응답 비정상")
    return rcp, title, dcm, pdf, d.analyze_result_pdf(pdf)


def run_e2e(input_text, output_dir):
    records = d.parse_input_lines(input_text.splitlines())
    output_dir.mkdir(parents=True, exist_ok=True)
    client = d.Dart()
    today = dt.date.today()
    start = (today - dt.timedelta(days=d.SEARCH_DAYS)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")
    search_cache = {}
    doc_cache = {}
    pdf_cache = {}
    text_cache = {}
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
                client, pairs, round_full, round_base, product, doc_cache, pdf_cache, text_cache
            )
            if not pdf:
                print(f"FAIL termsheet source={source} rcp={rcp} title={title}")
                failures += 1
                continue
            out = d.output_pdf_path(output_dir, stock_code, stock_name)
            out.write_bytes(pdf)
            print(f"OK termsheet source={source} rcp={rcp} dcm={dcm} file={out}")

            rr_rcp, rr_title, rr_dcm, rr_pdf, status = find_result_report(client, pairs, stock_name)
            label = status[1]
            reason = status[2]
            print(f"result_report status={label} reason={reason} rcp={rr_rcp} dcm={rr_dcm}")
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

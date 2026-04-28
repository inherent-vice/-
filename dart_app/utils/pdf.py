from __future__ import annotations

import io
import textwrap

from dart_app.domain.result_analysis import analyze_result_text
from dart_app.utils.text import clean_text

try:
    import pdfplumber

    HAS_PDFPLUMBER = True
except ImportError:
    pdfplumber = None
    HAS_PDFPLUMBER = False

try:
    from pdfminer.high_level import extract_text as pdfminer_extract_text

    HAS_PDFMINER = True
except ImportError:
    pdfminer_extract_text = None
    HAS_PDFMINER = False

HAS_PDF_TEXT = HAS_PDFPLUMBER or HAS_PDFMINER

try:
    import fitz

    HAS_PYMUPDF = True
except ImportError:
    fitz = None
    HAS_PYMUPDF = False


def is_pdf_bytes(data):
    if not data:
        return False
    return bytes(data[:1024]).lstrip().startswith(b"%PDF-")


def pdf_front_text(pdf_bytes, max_pages=5):
    if not is_pdf_bytes(pdf_bytes):
        return ""

    if HAS_PDFPLUMBER:
        try:
            chunks = []
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                for page in pdf.pages[:max_pages]:
                    chunks.append(page.extract_text() or "")
            text = "\n".join(chunk for chunk in chunks if chunk)
            if text.strip():
                return text
        except Exception:
            pass

    if HAS_PDFMINER:
        try:
            return pdfminer_extract_text(io.BytesIO(pdf_bytes), maxpages=max_pages) or ""
        except Exception:
            return ""
    return ""


def analyze_result_pdf(pdf_bytes):
    return analyze_result_text(pdf_front_text(pdf_bytes, max_pages=8))


def text_to_pdf_bytes(title, text, note=""):
    if not HAS_PYMUPDF or not clean_text(text):
        return None

    doc = fitz.open()
    width, height = 595, 842
    margin = 42
    font_size = 9
    line_height = 13
    max_lines = int((height - margin * 2) / line_height)
    lines = []
    for value in (title, note, "", text):
        value = clean_text(value)
        if not value and value != "":
            continue
        if value == "":
            lines.append("")
            continue
        for raw_line in str(value).splitlines() or [str(value)]:
            wrapped = textwrap.wrap(raw_line, width=92, replace_whitespace=False, drop_whitespace=False)
            lines.extend(wrapped or [""])

    page = None
    y = margin
    line_no = 0
    for line in lines:
        if page is None or line_no >= max_lines:
            page = doc.new_page(width=width, height=height)
            y = margin
            line_no = 0
        page.insert_text((margin, y), line, fontsize=font_size, fontname="korea")
        y += line_height
        line_no += 1

    return doc.tobytes()

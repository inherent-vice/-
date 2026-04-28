from __future__ import annotations

import re
from html import unescape as html_unescape

def clean_text(s):
    return re.sub(r"\s+", " ", html_unescape(s or "")).strip()

def html_body_text(html):
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html or "")
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return clean_text(text)

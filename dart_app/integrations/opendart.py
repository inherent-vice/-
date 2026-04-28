from __future__ import annotations

import io
import json
import re
import threading
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import requests

from dart_app import config
from dart_app.utils.text import clean_text, html_body_text

OPENDART_BASE = "https://opendart.fss.or.kr/api"
DEFAULT_CACHE_DIR = config.CACHE_DIR
SECURITIES_ISSUER_ALIASES = {
    "BNK증권": ["BNK투자증권"],
    "BNK투자증권": ["BNK증권"],
    "DB증권": ["DB금융투자"],
    "DB금융투자": ["DB증권"],
    "KB증권": ["케이비증권"],
    "케이비증권": ["KB증권"],
    "메리츠증권": ["메리츠종합금융"],
    "메리츠종합금융": ["메리츠증권"],
    "신한투자증권": ["신한금융투자"],
    "신한금융투자": ["신한투자증권"],
    "하나증권": ["하나금융투자"],
    "하나금융투자": ["하나증권"],
}


def _read_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_cache_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9가-힣_.-]+", "_", str(value or "")).strip("_") or "empty"


def _normalize_company(value: str) -> str:
    text = re.sub(r"\s+", "", clean_text(value))
    for token in ("주식회사", "(주)", "증권", "투자", "금융", "종합", "투자증권", "종합금융증권"):
        text = text.replace(token, "")
    return text


def _strict_company_key(value: str) -> str:
    text = re.sub(r"\s+", "", clean_text(value))
    for token in ("주식회사", "(주)", "㈜"):
        text = text.replace(token, "")
    return text.upper()


def _company_aliases(company: str) -> list[str]:
    company = clean_text(company)
    aliases = [company, *SECURITIES_ISSUER_ALIASES.get(company, [])]
    if company.startswith("KB"):
        aliases.append(company.replace("KB", "케이비", 1))
    if company.startswith("케이비"):
        aliases.append(company.replace("케이비", "KB", 1))
    return list(dict.fromkeys(alias for alias in aliases if alias))


def _company_name_matches(corp_name: str, aliases: list[str]) -> bool:
    corp_key = _strict_company_key(corp_name)
    return bool(corp_key and any(corp_key == _strict_company_key(alias) for alias in aliases))


def _looks_like_securities_issuer(company: str) -> bool:
    text = clean_text(company)
    return "증권" in text or text in SECURITIES_ISSUER_ALIASES


class OpenDart:
    _request_lock = threading.Lock()
    _last_request_at = 0.0
    _market_lock = threading.Lock()
    _market_refreshed_keys: set[tuple[str, str, str]] = set()

    def __init__(self, api_key, cache_dir=None):
        self.api_key = str(api_key or "").strip()
        self._cache_dir_override = Path(cache_dir) if cache_dir else None
        self.s = requests.Session()
        self._corp_codes = None

    def enabled(self):
        return bool(self.api_key)

    def cache_dir(self):
        return self._cache_dir_override or DEFAULT_CACHE_DIR

    def _request(self, endpoint, params=None, timeout=30):
        if not self.enabled():
            raise RuntimeError("OpenDART API key is empty")
        payload = dict(params or {})
        payload["crtfc_key"] = self.api_key
        with self._request_lock:
            now = time.monotonic()
            delay = 0.12 - (now - self._last_request_at)
            if delay > 0:
                time.sleep(delay)
            type(self)._last_request_at = time.monotonic()
        response = self.s.get(f"{OPENDART_BASE}/{endpoint}", params=payload, timeout=timeout)
        response.raise_for_status()
        return response

    def _corp_cache_path(self):
        return self.cache_dir() / "opendart" / "corp_codes.json"

    def _search_cache_path(self, company, start, end, report_name):
        name = _safe_cache_name(f"v2_{company}_{start}_{end}_{report_name}")
        return self.cache_dir() / "opendart" / "search" / f"{name}.json"

    def _document_cache_path(self, rcp_no):
        return self.cache_dir() / "opendart" / "document" / f"{_safe_cache_name(rcp_no)}.txt"

    def _market_filings_cache_path(self, start, end, pblntf_ty):
        name = _safe_cache_name(f"v2_{start}_{end}_{pblntf_ty or 'all'}")
        return self.cache_dir() / "opendart" / "market_filings" / f"{name}.json"

    def _load_corp_codes(self):
        if self._corp_codes is not None:
            return self._corp_codes

        cache_path = self._corp_cache_path()
        cached = _read_json(cache_path, None)
        if cached is not None:
            self._corp_codes = cached
            return cached

        response = self._request("corpCode.xml")
        rows = []
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            names = zf.namelist()
            if not names:
                self._corp_codes = []
                return []
            xml_data = zf.read(names[0])
        root = ElementTree.fromstring(xml_data)
        for item in root.findall(".//list"):
            rows.append({
                "corp_code": clean_text(item.findtext("corp_code")),
                "corp_name": clean_text(item.findtext("corp_name")),
                "stock_code": clean_text(item.findtext("stock_code")),
            })
        _write_json(cache_path, rows)
        self._corp_codes = rows
        return rows

    def find_corp_code(self, company):
        target = clean_text(company)
        if not target:
            return None
        normalized_target = _normalize_company(target)
        fallback = None
        for row in self._load_corp_codes():
            name = clean_text(row.get("corp_name"))
            code = clean_text(row.get("corp_code"))
            if not name or not code:
                continue
            if name == target:
                return code
            normalized_name = _normalize_company(name)
            if normalized_name and normalized_name == normalized_target:
                return code
            if normalized_name and normalized_target and (
                normalized_name.startswith(normalized_target) or normalized_target.startswith(normalized_name)
            ):
                fallback = fallback or code
        return fallback

    def _load_market_filings(self, start, end, pblntf_ty="C", force_refresh=False):
        cache_path = self._market_filings_cache_path(start, end, pblntf_ty)
        cache_key = (str(start), str(end), str(pblntf_ty or ""))
        with self._market_lock:
            if not force_refresh or cache_key in self._market_refreshed_keys:
                cached = _read_json(cache_path, None)
                if cached is not None:
                    return cached

            rows = []
            page = 1
            while True:
                response = self._request(
                    "list.json",
                    params={
                        "bgn_de": start,
                        "end_de": end,
                        "page_no": page,
                        "page_count": 100,
                        "pblntf_ty": pblntf_ty,
                    },
                )
                data = response.json()
                if data.get("status") not in (None, "000", "013"):
                    break
                rows.extend(data.get("list") or [])
                total_page = int(data.get("total_page") or 1)
                if page >= total_page:
                    break
                page += 1

            _write_json(cache_path, rows)
            self._market_refreshed_keys.add(cache_key)
            return rows

    def _scan_market_filings_by_company(self, company, start, end, report_name="", force_refresh=False):
        aliases = _company_aliases(company)
        if not aliases:
            return []
        rows = self._load_market_filings(start, end, pblntf_ty="C", force_refresh=force_refresh)
        results = []
        seen = set()
        for row in rows:
            if not _company_name_matches(row.get("corp_name", ""), aliases):
                continue
            rcp_no = clean_text(row.get("rcept_no"))
            title = clean_text(row.get("report_nm"))
            if not rcp_no or rcp_no in seen:
                continue
            if report_name and report_name not in title:
                continue
            seen.add(rcp_no)
            results.append((rcp_no, title))
        return results

    def search(self, company, start, end, report_name="", page_size=100, force_refresh=False):
        cache_path = self._search_cache_path(company, start, end, report_name)
        if not force_refresh:
            cached = _read_json(cache_path, None)
            if cached is not None:
                return [tuple(item) for item in cached]

        if _looks_like_securities_issuer(company):
            scanned = self._scan_market_filings_by_company(company, start, end, report_name, force_refresh=force_refresh)
            if scanned:
                _write_json(cache_path, scanned)
                return scanned

        corp_code = self.find_corp_code(company)
        if not corp_code:
            scanned = self._scan_market_filings_by_company(company, start, end, report_name, force_refresh=force_refresh)
            _write_json(cache_path, scanned)
            return scanned

        aliases = _company_aliases(company)
        results = []
        page = 1
        while True:
            response = self._request(
                "list.json",
                params={
                    "corp_code": corp_code,
                    "bgn_de": start,
                    "end_de": end,
                    "page_no": page,
                    "page_count": page_size,
                },
            )
            data = response.json()
            if data.get("status") not in (None, "000", "013"):
                break
            for row in data.get("list") or []:
                rcp_no = clean_text(row.get("rcept_no"))
                title = clean_text(row.get("report_nm"))
                if not rcp_no:
                    continue
                corp_name = clean_text(row.get("corp_name"))
                if corp_name and not _company_name_matches(corp_name, aliases):
                    continue
                if report_name and report_name not in title:
                    continue
                results.append((rcp_no, title))
            total_page = int(data.get("total_page") or 1)
            if page >= total_page:
                break
            page += 1

        if not results:
            results = self._scan_market_filings_by_company(company, start, end, report_name, force_refresh=force_refresh)

        _write_json(cache_path, results)
        return results

    def get_document_text(self, rcp_no, force_refresh=False):
        cache_path = self._document_cache_path(rcp_no)
        if cache_path.exists() and not force_refresh:
            return cache_path.read_text(encoding="utf-8", errors="ignore")

        response = self._request("document.xml", params={"rcept_no": rcp_no})
        text = ""
        with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
            for name in zf.namelist():
                if not name.lower().endswith((".xml", ".html", ".htm")):
                    continue
                raw = zf.read(name)
                try:
                    body = raw.decode("utf-8")
                except UnicodeDecodeError:
                    body = raw.decode("cp949", errors="ignore")
                text = html_body_text(body)
                if text:
                    break
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(text, encoding="utf-8")
        return text

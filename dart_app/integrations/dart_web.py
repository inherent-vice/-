from __future__ import annotations

import datetime as dt
import re
import threading
import time
from html import unescape as html_unescape

import requests

from dart_app import config
from dart_app.integrations.opendart import OpenDart
from dart_app.runtime import (
    load_json,
    load_json_cache,
    read_cache_bytes,
    read_cache_text,
    safe_cache_name,
    save_json,
    write_cache_bytes,
    write_cache_text,
)
from dart_app.utils.pdf import is_pdf_bytes
from dart_app.utils.text import clean_text, html_body_text

DART_BASE = "https://dart.fss.or.kr"
SEARCH_URL = f"{DART_BASE}/dsab007/detailSearch.ax"
INDEX_URL = f"{DART_BASE}/dsaf001/main.do"
PDF_URL = f"{DART_BASE}/pdf/download/pdf.do"
VIEWER_URL = f"{DART_BASE}/report/viewer.do"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": DART_BASE,
    "Referer": f"{DART_BASE}/dsab007/main.do",
    "Cache-Control": "no-cache",
    "Connection": "close",
}
REQUEST_RETRIES = 3
RETRY_BACKOFF = 0.8


class Dart:
    _global_request_lock = threading.Lock()
    _global_last_request_at = 0.0
    _global_blocked_until = 0.0
    _global_consecutive_failures = 0

    def __init__(self, opendart_api_key=None):
        self._warmed = False
        self._blocked_until = 0.0
        self._last_request_error = None
        self._consecutive_failures = 0
        self.s = self._make_session()
        self.opendart = self.make_opendart(self.resolve_opendart_api_key(opendart_api_key))

    def resolve_opendart_api_key(self, value):
        return value or ""

    def make_opendart(self, api_key):
        return OpenDart(api_key)

    def cache_dir(self):
        return config.CACHE_DIR

    def search_cache_seconds(self):
        return config.SEARCH_CACHE_SECONDS

    def _search_cache_path(self, company, start, end, report_name):
        report_key = report_name or "all"
        name = safe_cache_name(f"v2_{company}_{start}_{end}_{report_key}")
        return self.cache_dir() / "dart_search" / f"{name}.json"

    def _index_cache_path(self, rcp_no):
        return self.cache_dir() / "dart_index" / f"{safe_cache_name(rcp_no)}.html"

    def _pdf_cache_path(self, rcp_no, dcm_no):
        return self.cache_dir() / "dart_pdf" / f"{safe_cache_name(rcp_no)}_{safe_cache_name(dcm_no)}.pdf"

    def _viewer_cache_path(self, rcp_no, dcm_no):
        return self.cache_dir() / "dart_viewer" / f"{safe_cache_name(rcp_no)}_{safe_cache_name(dcm_no or 'initial')}.txt"

    def request_retries(self):
        return config.REQUEST_RETRIES

    def retry_backoff(self):
        return config.RETRY_BACKOFF

    def _make_session(self):
        session = requests.Session()
        session.trust_env = False
        session.headers.update(HEADERS)
        return session

    def _reset_session(self):
        try:
            self.s.close()
        except Exception:
            pass
        self._warmed = False
        self.s = self._make_session()

    def _warmup(self):
        if self._warmed:
            return
        try:
            response = self._paced_session_request("GET", f"{DART_BASE}/dsab007/main.do", timeout=10)
            response.raise_for_status()
            self._warmed = True
        except requests.RequestException:
            self._reset_session()

    @classmethod
    def _is_dart_url(cls, url):
        return str(url or "").startswith(DART_BASE)

    @classmethod
    def _wait_for_global_slot(cls):
        with cls._global_request_lock:
            now = time.monotonic()
            blocked_for = cls._global_blocked_until - now
            if blocked_for > 0:
                time.sleep(blocked_for)
            now = time.monotonic()
            min_interval = max(0.0, float(config.HTTP_MIN_INTERVAL or 0))
            delay = min_interval - (now - cls._global_last_request_at)
            if delay > 0:
                time.sleep(delay)
            cls._global_last_request_at = time.monotonic()

    @classmethod
    def _record_global_success(cls):
        with cls._global_request_lock:
            cls._global_consecutive_failures = 0
            cls._global_blocked_until = 0.0

    @classmethod
    def _record_global_failure(cls, error, attempt=0):
        text = str(error)
        transient = (
            "RemoteDisconnected" in text
            or "empty response" in text.lower()
            or isinstance(error, (requests.ConnectionError, requests.Timeout))
        )
        if not transient:
            return
        with cls._global_request_lock:
            cls._global_consecutive_failures += 1
            short_cooldown = max(float(config.HTTP_MIN_INTERVAL or 0) * 4, float(config.RETRY_BACKOFF or 0.5) * (attempt + 1), 1.0)
            cooldown = min(short_cooldown, 10.0)
            if cls._global_consecutive_failures >= max(1, int(config.CIRCUIT_FAIL_LIMIT or 1)):
                cooldown = max(cooldown, min(float(config.CIRCUIT_COOLDOWN or 0), 8.0))
            cls._global_blocked_until = max(cls._global_blocked_until, time.monotonic() + cooldown)

    def _paced_session_request(self, method, url, **kwargs):
        if self._is_dart_url(url):
            self._wait_for_global_slot()
        return self.s.request(method, url, **kwargs)

    def _request(self, method, url, **kwargs):
        now = time.monotonic()
        if self._blocked_until > now:
            detail = f": {self._last_request_error}" if self._last_request_error else ""
            time.sleep(self._blocked_until - now)

        last_error = None
        retries = max(1, int(self.request_retries() or 1))
        for attempt in range(retries):
            try:
                response = self._paced_session_request(method, url, **kwargs)
                response.raise_for_status()
                self._blocked_until = 0.0
                self._last_request_error = None
                self._consecutive_failures = 0
                if self._is_dart_url(url):
                    self._record_global_success()
                return response
            except requests.RequestException as exc:
                last_error = exc
                if self._is_dart_url(url):
                    self._record_global_failure(exc, attempt)
                self._reset_session()
                if attempt < retries - 1:
                    time.sleep(float(self.retry_backoff() or 0) * (attempt + 1))
        self._last_request_error = last_error
        self._consecutive_failures += 1
        if self._consecutive_failures >= max(1, int(config.CIRCUIT_FAIL_LIMIT or 1)):
            self._blocked_until = time.monotonic() + min(float(config.CIRCUIT_COOLDOWN or 0), 8.0)
        raise last_error

    @staticmethod
    def _error_label(error):
        text = str(error)
        if "RemoteDisconnected" in text or "empty response" in text.lower():
            return "서버가 응답 없이 연결을 끊었습니다"
        if isinstance(error, requests.Timeout):
            return "요청 시간이 초과되었습니다"
        if isinstance(error, requests.SSLError):
            return "TLS/인증서 연결 오류"
        if isinstance(error, requests.ConnectionError):
            return "연결 오류"
        return f"{type(error).__name__}: {text}"

    def check_status(self):
        checks = []

        def add_check(name, method, url, **kwargs):
            started = time.time()
            try:
                response = self._request(method, url, **kwargs)
                elapsed = time.time() - started
                checks.append({
                    "name": name,
                    "ok": True,
                    "status": response.status_code,
                    "detail": f"HTTP {response.status_code}, {len(response.content)} bytes, {elapsed:.1f}s",
                })
            except Exception as exc:
                elapsed = time.time() - started
                checks.append({
                    "name": name,
                    "ok": False,
                    "status": None,
                    "detail": f"{self._error_label(exc)} ({elapsed:.1f}s)",
                })

        add_check("DART 메인", "GET", f"{DART_BASE}/dsab007/main.do", timeout=10)
        today = dt.date.today()
        add_check(
            "DART 검색",
            "POST",
            SEARCH_URL,
            data={
                "currentPage": 1,
                "maxResults": 10,
                "sort": "date",
                "series": "desc",
                "startDate": (today - dt.timedelta(days=7)).strftime("%Y%m%d"),
                "endDate": today.strftime("%Y%m%d"),
                "pubStatus": "Y",
                "textCrpNm": "메리츠증권",
                "reportName": "",
            },
            timeout=20,
        )
        ok = all(check["ok"] for check in checks)
        return {"ok": ok, "summary": "정상" if ok else "장애 또는 접속 불가", "checks": checks}

    @staticmethod
    def parse_search_results(html):
        pairs = re.findall(
            r"openReportViewer\(\s*['\"](\d{14})['\"][^>]*\)[^>]*>\s*([^<]+?)\s*<",
            html or "",
            flags=re.I | re.S,
        )
        if pairs:
            return [(rcp, clean_text(html_unescape(title).replace("\xa0", " "))) for rcp, title in pairs]
        rcps = []
        seen = set()
        for rcp in re.findall(r"\b(\d{14})\b", html or ""):
            if rcp in seen:
                continue
            seen.add(rcp)
            rcps.append((rcp, ""))
        return rcps

    @staticmethod
    def parse_doc_info(html):
        html = html or ""
        dcm_no = None
        for pattern in (
            r"\bdcmNo\s*[:=]\s*['\"]?(\d{8})",
            r"\bdcm_no\s*[:=]\s*['\"]?(\d{8})",
            r"openPdfDownload\(\s*['\"]\d{14}['\"]\s*,\s*['\"](\d{8})",
        ):
            match = re.search(pattern, html, flags=re.I)
            if match:
                dcm_no = match.group(1)
                break
        if not dcm_no:
            nums = re.findall(r"['\"](\d{8})['\"]", html)
            dcm_no = next((num for num in nums if not num.startswith("00")), None)

        titles = re.findall(
            r"\.add\(\s*['\"][^'\"]*['\"]\s*,\s*['\"][^'\"]*['\"]\s*,\s*['\"]([^'\"]+)['\"]",
            html,
            flags=re.S,
        )
        if not titles:
            titles = [
                item for item in re.findall(r"['\"]([^'\"]{8,})['\"]", html)
                if re.search(r"[가-힣]", item)
            ]
        return dcm_no, [clean_text(html_unescape(title)) for title in titles]

    @staticmethod
    def parse_viewer_params(html, rcp_no=None, dcm_no=None):
        html = html or ""
        pattern = re.compile(
            r"viewDoc\(\s*['\"](?P<rcpNo>\d{14})['\"]\s*,\s*"
            r"['\"](?P<dcmNo>\d{8})['\"]\s*,\s*"
            r"['\"](?P<eleId>[^'\"]+)['\"]\s*,\s*"
            r"['\"](?P<offset>\d+)['\"]\s*,\s*"
            r"['\"](?P<length>\d+)['\"]\s*,\s*"
            r"['\"](?P<dtd>[^'\"]+)['\"]",
            flags=re.I,
        )
        for match in pattern.finditer(html):
            data = match.groupdict()
            if rcp_no and data["rcpNo"] != str(rcp_no):
                continue
            if dcm_no and data["dcmNo"] != str(dcm_no):
                continue
            return data
        return None

    def search(self, company, start, end, report_name="", page_size=100, force_refresh=False):
        cache_path = self._search_cache_path(company, start, end, report_name)
        if not force_refresh:
            cached = load_json_cache(cache_path, self.search_cache_seconds())
            if cached is not None:
                return [tuple(item) for item in cached]

        if self.opendart.enabled():
            try:
                official = self.opendart.search(
                    company, start, end, report_name=report_name, page_size=page_size, force_refresh=force_refresh
                )
                if official:
                    save_json(cache_path, official)
                    return official
            except Exception:
                pass

        try:
            self._warmup()
            results = []
            seen = set()
            page = 1
            while True:
                data = {
                    "currentPage": page,
                    "maxResults": page_size,
                    "sort": "date",
                    "series": "desc",
                    "startDate": start,
                    "endDate": end,
                    "pubStatus": "Y",
                    "textCrpNm": company,
                    "reportName": report_name,
                }
                response = self._request("POST", SEARCH_URL, data=data, timeout=20)
                pairs = self.parse_search_results(response.text)
                new_count = 0
                for rcp, title in pairs:
                    if rcp in seen:
                        continue
                    seen.add(rcp)
                    new_count += 1
                    results.append((rcp, title))
                if new_count == 0 or len(pairs) < page_size:
                    break
                page += 1
            save_json(cache_path, results)
            return results
        except Exception:
            stale = load_json(cache_path, None)
            if stale is not None:
                return [tuple(item) for item in stale]
            raise

    def get_index_html(self, rcp_no):
        cache_path = self._index_cache_path(rcp_no)
        cached = read_cache_text(cache_path)
        if cached:
            return cached
        try:
            response = self._request("GET", INDEX_URL, params={"rcpNo": rcp_no}, timeout=20)
            write_cache_text(cache_path, response.text)
            return response.text
        except Exception:
            cached = read_cache_text(cache_path)
            if cached:
                return cached
            raise

    def get_doc_info(self, rcp_no):
        return self.parse_doc_info(self.get_index_html(rcp_no))

    def get_dcm_no(self, rcp_no):
        dcm_no, _titles = self.get_doc_info(rcp_no)
        return dcm_no

    def download_pdf(self, rcp_no, dcm_no):
        if not rcp_no or not dcm_no:
            return None
        cache_path = self._pdf_cache_path(rcp_no, dcm_no)
        cached = read_cache_bytes(cache_path)
        if is_pdf_bytes(cached):
            return cached
        try:
            response = self._request("GET", PDF_URL, params={"rcp_no": rcp_no, "dcm_no": dcm_no}, timeout=30)
            content = response.content
            if is_pdf_bytes(content):
                write_cache_bytes(cache_path, content)
                return content
            return None
        except Exception:
            cached = read_cache_bytes(cache_path)
            if is_pdf_bytes(cached):
                return cached
            raise

    def get_viewer_text_from_index(self, index_html, rcp_no, dcm_no=None):
        params = self.parse_viewer_params(index_html, rcp_no=rcp_no, dcm_no=dcm_no)
        if not params:
            return ""
        cache_path = self._viewer_cache_path(rcp_no, params.get("dcmNo") or dcm_no)
        cached = read_cache_text(cache_path)
        if cached:
            return cached
        try:
            response = self._request("GET", VIEWER_URL, params=params, timeout=20)
            text = html_body_text(response.text)
            write_cache_text(cache_path, text)
            return text
        except Exception:
            cached = read_cache_text(cache_path)
            if cached:
                return cached
            raise

    def get_viewer_text(self, rcp_no, dcm_no=None):
        return self.get_viewer_text_from_index(self.get_index_html(rcp_no), rcp_no, dcm_no=dcm_no)

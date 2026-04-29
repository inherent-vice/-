from __future__ import annotations

import os
from pathlib import Path

from dart_app import config
from dart_app.domain.document_matching import (
    classify_termsheet_candidate,
    find_result_report_document as _find_result_report_document,
    find_termsheet_document as _find_termsheet_document,
    match_result,
    match_termsheet,
    termsheet_candidates,
    termsheet_keywords,
)
from dart_app.domain.input_parser import is_security_code, parse_input_line, parse_input_lines
from dart_app.domain.result_analysis import analyze_result_text, extract_allocation_table_amounts, extract_result_amounts
from dart_app.domain.security_name import (
    PUBLIC_OFFER_MARKERS,
    expected_product_label,
    extract_product_type,
    extract_round,
    find_issuer,
    has_wrong_product_label,
    identifier_in_text,
    is_subordinated,
    normalize_stock_name_text,
    product_round_in_text,
    round_in,
    round_in_exact,
)
from dart_app.domain.structured_bond import normalize_structured_bond_row, structured_bond_db_evidence
from dart_app.integrations import opendart as _opendart
from dart_app.integrations.dart_web import DART_BASE, HEADERS, INDEX_URL, PDF_URL, SEARCH_URL, VIEWER_URL, Dart as _Dart
from dart_app.integrations.opendart import OPENDART_BASE
from dart_app.models import DocumentCandidateScore, ResultAnalysis, ResultAmount, ResultReportMatch, TermsheetMatchResult
from dart_app.runtime import (
    cache_stats as _cache_stats,
    clear_cache as _clear_cache,
    load_json_cache,
    prune_cache as _prune_cache,
    read_cache_bytes,
    read_cache_text,
    safe_cache_name,
    save_json as _save_json,
    today_str,
    write_cache_bytes,
    write_cache_text,
)
from dart_app.runtime import load_json as _load_json
from dart_app.runtime import normalize_runtime_settings as _normalize_runtime_settings
from dart_app.runtime import normalize_save_root as _normalize_save_root
from dart_app.services.document_access import DartDocumentAccess, RunDocumentCache
from dart_app.services.http_guard import HttpGuard
from dart_app.services.record_workflow import RecordWorkflow, RecordWorkflowOptions
from dart_app.services.structured_bond_db import (
    StructuredBondDbLookup,
    _default_sql_driver,
    couponcheck_root_candidates,
    find_couponcheck_root,
)
from dart_app.ui.app import App, main
from dart_app.ui.dialogs import IssuerEditor, SettingsDialog
from dart_app.utils.files import output_pdf_path, safe_filename, stock_output_dir, unique_path
from dart_app.utils.pdf import HAS_PDFMINER, HAS_PDFPLUMBER, HAS_PDF_TEXT, analyze_result_pdf, is_pdf_bytes, pdf_front_text
from dart_app.utils.text import clean_text, html_body_text

BUNDLE_DIR = config.BUNDLE_DIR
APP_DIR = config.APP_DIR
ISSUERS_PATH = config.ISSUERS_PATH
SETTINGS_PATH = config.SETTINGS_PATH
STATE_DIR = config.STATE_DIR
CACHE_DIR = config.CACHE_DIR
LOGO_PATH = config.LOGO_PATH
DEFAULT_SAVE_ROOT = config.DEFAULT_SAVE_ROOT
DOWNLOADS = config.DOWNLOADS
DEFAULT_ISSUERS = config.DEFAULT_ISSUERS
BG = config.BG
PANEL = config.PANEL
INPUT_BG = config.INPUT_BG
ACCENT = config.ACCENT
ACCENT_DK = config.ACCENT_DK
TEXT = config.TEXT
MUTED = config.MUTED
LOG_BG = config.LOG_BG
SLEEP = config.SLEEP
SEARCH_DAYS = config.SEARCH_DAYS
RESULT_SEARCH_DAYS = config.RESULT_SEARCH_DAYS
INDEX_SCAN_LIMIT = config.INDEX_SCAN_LIMIT
PDF_SCAN_LIMIT = config.PDF_SCAN_LIMIT
RESULT_SCAN_LIMIT = config.RESULT_SCAN_LIMIT
RESULT_BODY_SCAN_LIMIT = config.RESULT_BODY_SCAN_LIMIT
RESULT_FRONT_TEXT_SCAN_LIMIT = config.RESULT_FRONT_TEXT_SCAN_LIMIT
REQUEST_RETRIES = config.REQUEST_RETRIES
RETRY_BACKOFF = config.RETRY_BACKOFF
DOWNLOAD_WORKERS = config.DOWNLOAD_WORKERS
HTTP_MIN_INTERVAL = config.HTTP_MIN_INTERVAL
CIRCUIT_FAIL_LIMIT = config.CIRCUIT_FAIL_LIMIT
CIRCUIT_COOLDOWN = config.CIRCUIT_COOLDOWN
SEARCH_CACHE_SECONDS = config.SEARCH_CACHE_SECONDS
DEFAULT_RUNTIME_SETTINGS = config.DEFAULT_RUNTIME_SETTINGS
RUNTIME_PRESETS = config.RUNTIME_PRESETS
JSON_LOAD_ERRORS: list[str] = []


def _sync_config_from_globals():
    for name in (
        "SEARCH_DAYS",
        "RESULT_SEARCH_DAYS",
        "INDEX_SCAN_LIMIT",
        "PDF_SCAN_LIMIT",
        "RESULT_SCAN_LIMIT",
        "RESULT_BODY_SCAN_LIMIT",
        "RESULT_FRONT_TEXT_SCAN_LIMIT",
        "REQUEST_RETRIES",
        "RETRY_BACKOFF",
        "DOWNLOAD_WORKERS",
        "HTTP_MIN_INTERVAL",
        "CIRCUIT_FAIL_LIMIT",
        "CIRCUIT_COOLDOWN",
        "SEARCH_CACHE_SECONDS",
    ):
        setattr(config, name, globals()[name])


def load_json(path, default=None):
    try:
        return _load_json(path, default)
    except Exception as exc:
        JSON_LOAD_ERRORS.append(f"{path}: {exc}")
        return default


def save_json(path, data):
    return _save_json(path, data)


def load_issuers():
    merged = dict(DEFAULT_ISSUERS)
    user = load_json(ISSUERS_PATH, {}) or {}
    for key, value in user.items():
        if key.startswith("_") or not isinstance(value, str) or not value.strip():
            continue
        merged[key.strip()] = value.strip()
    return merged


def save_user_issuers(user_dict):
    cleaned = {"_comment": "사용자 추가 매핑. 기본값은 코드에 내장."}
    for key, value in (user_dict or {}).items():
        if key.startswith("_") or not value:
            continue
        key = str(key).strip()
        value = str(value).strip()
        if not key or not value:
            continue
        if DEFAULT_ISSUERS.get(key) == value:
            continue
        cleaned[key] = value
    save_json(ISSUERS_PATH, cleaned)


def normalize_save_root(value=None):
    return _normalize_save_root(value, DEFAULT_SAVE_ROOT)


def normalize_api_key(value=None):
    return str(value or "").strip()


def _read_env_api_key(path):
    path = Path(path)
    if not path.exists():
        return ""
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in ("OPENDART_API_KEY", "OPEN_DART_API_KEY", "DART_API_KEY"):
                return normalize_api_key(value.strip().strip('"').strip("'"))
    except OSError:
        return ""
    return ""


def discover_opendart_api_key():
    for key in ("OPENDART_API_KEY", "OPEN_DART_API_KEY", "DART_API_KEY"):
        value = normalize_api_key(os.environ.get(key))
        if value:
            return value
    candidates = [APP_DIR / ".env", APP_DIR.parent / ".env", Path.cwd() / ".env", Path(r"E:\Devs\Dart\.env")]
    seen = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        value = _read_env_api_key(path)
        if value:
            return value
    return ""


def normalize_runtime_settings(data=None):
    return _normalize_runtime_settings(data, DEFAULT_RUNTIME_SETTINGS)


def apply_runtime_settings(settings):
    runtime = normalize_runtime_settings(settings)
    globals()["SEARCH_DAYS"] = runtime["search_days"]
    globals()["RESULT_SEARCH_DAYS"] = runtime["result_search_days"]
    globals()["INDEX_SCAN_LIMIT"] = runtime["index_scan_limit"]
    globals()["PDF_SCAN_LIMIT"] = runtime["pdf_scan_limit"]
    globals()["RESULT_SCAN_LIMIT"] = runtime["result_scan_limit"]
    globals()["RESULT_BODY_SCAN_LIMIT"] = runtime["result_body_scan_limit"]
    globals()["RESULT_FRONT_TEXT_SCAN_LIMIT"] = runtime["result_front_text_scan_limit"]
    globals()["REQUEST_RETRIES"] = runtime["request_retries"]
    globals()["RETRY_BACKOFF"] = runtime["retry_backoff"]
    globals()["DOWNLOAD_WORKERS"] = runtime["download_workers"]
    globals()["HTTP_MIN_INTERVAL"] = runtime["http_min_interval"]
    globals()["CIRCUIT_FAIL_LIMIT"] = runtime["circuit_fail_limit"]
    globals()["CIRCUIT_COOLDOWN"] = runtime["circuit_cooldown"]
    globals()["SEARCH_CACHE_SECONDS"] = int(runtime["search_cache_hours"] * 3600)
    _sync_config_from_globals()
    _sync_document_matching_settings()
    return runtime


def load_settings():
    data = load_json(SETTINGS_PATH, {}) or {}
    settings = normalize_runtime_settings(data)
    if data.get("result_search_days") == 180:
        settings["result_search_days"] = RESULT_SEARCH_DAYS
    if data.get("result_scan_limit") == 50:
        settings["result_scan_limit"] = RESULT_SCAN_LIMIT
    settings["save_root"] = str(normalize_save_root(data.get("save_root")))
    if data.get("opendart_api_key"):
        settings["opendart_api_key"] = normalize_api_key(data.get("opendart_api_key"))
    return settings


def save_settings(settings):
    settings = dict(settings or {})
    root = normalize_save_root(settings.get("save_root"))
    normalized = normalize_runtime_settings(settings)
    normalized["save_root"] = str(root)
    if settings.get("opendart_api_key") is not None:
        normalized["opendart_api_key"] = normalize_api_key(settings.get("opendart_api_key"))
    save_json(SETTINGS_PATH, normalized)
    return root


def get_save_root():
    return normalize_save_root(load_settings().get("save_root"))


def get_opendart_api_key():
    settings_key = normalize_api_key(load_settings().get("opendart_api_key"))
    return settings_key or discover_opendart_api_key()


def get_state():
    STATE_DIR.mkdir(exist_ok=True)
    path = STATE_DIR / f"{today_str()}.json"
    return path, load_json(path, {"searched": []})


def cache_stats():
    return _cache_stats(CACHE_DIR)


def clear_cache(kind="all"):
    return _clear_cache(CACHE_DIR, kind)


def prune_cache(settings=None):
    return _prune_cache(CACHE_DIR, settings or load_settings())


class OpenDart(_opendart.OpenDart):
    def cache_dir(self):
        return CACHE_DIR


class Dart(_Dart):
    def cache_dir(self):
        return CACHE_DIR

    def search_cache_seconds(self):
        return SEARCH_CACHE_SECONDS

    def resolve_opendart_api_key(self, value):
        if value is not None:
            return value
        return get_opendart_api_key()

    def make_opendart(self, api_key):
        return OpenDart(api_key)

    def request_retries(self):
        return REQUEST_RETRIES

    def retry_backoff(self):
        return RETRY_BACKOFF


def _sync_document_matching_settings():
    import dart_app.domain.document_matching as document_matching

    document_matching.INDEX_SCAN_LIMIT = INDEX_SCAN_LIMIT
    document_matching.PDF_SCAN_LIMIT = PDF_SCAN_LIMIT
    document_matching.RESULT_SCAN_LIMIT = RESULT_SCAN_LIMIT
    document_matching.RESULT_BODY_SCAN_LIMIT = RESULT_BODY_SCAN_LIMIT
    document_matching.RESULT_FRONT_TEXT_SCAN_LIMIT = RESULT_FRONT_TEXT_SCAN_LIMIT


def find_termsheet_document(*args, **kwargs):
    _sync_document_matching_settings()
    return _find_termsheet_document(*args, **kwargs)


def find_result_report_document(*args, **kwargs):
    _sync_document_matching_settings()
    return _find_result_report_document(*args, **kwargs)

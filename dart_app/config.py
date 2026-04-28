from __future__ import annotations

import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    BUNDLE_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).resolve().parents[1]
    BUNDLE_DIR = APP_DIR

ISSUERS_PATH = APP_DIR / "issuers.json"
SETTINGS_PATH = APP_DIR / "settings.json"
STATE_DIR = APP_DIR / "state"
CACHE_DIR = APP_DIR / "cache"
LOGO_PATH = BUNDLE_DIR / "kap_logo.png"

DEFAULT_SAVE_ROOT = Path(
    r"\\10.10.10.11\파생상품평가본부\B.구조화평가팀\2_Term Sheet 모음\금리구조화채권"
)
DOWNLOADS = DEFAULT_SAVE_ROOT

DEFAULT_ISSUERS = {
    "트루": "한국투자증권",
    "한화스마트": "한화투자증권",
    "키움YOU": "키움증권",
    "미래에셋캐피탈": "미래에셋캐피탈",
    "미래에셋생명": "미래에셋생명보험",
    "미래에셋자산운용": "미래에셋자산운용",
    "미래에셋대우": "미래에셋증권",
    "대우증권": "미래에셋증권",
    "미래에셋": "미래에셋증권",
    "삼성생명": "삼성생명보험",
    "삼성화재": "삼성화재해상보험",
    "삼성카드": "삼성카드",
    "삼성자산운용": "삼성자산운용",
    "삼성": "삼성증권",
    "신한캐피탈": "신한캐피탈",
    "신한카드": "신한카드",
    "신한라이프": "신한라이프생명보험",
    "신한자산운용": "신한자산운용",
    "신한투자": "신한투자증권",
    "신한금융투자": "신한투자증권",
    "신한": "신한투자증권",
    "KB캐피탈": "케이비캐피탈",
    "KB카드": "케이비국민카드",
    "KB국민카드": "케이비국민카드",
    "KB라이프": "KB라이프생명보험",
    "KB손해보험": "KB손해보험",
    "KB자산운용": "케이비자산운용",
    "KB able": "KB증권",
    "KBable": "KB증권",
    "KB STAR": "KB증권",
    "KB": "KB증권",
    "NH투자": "NH투자증권",
    "NH농협캐피탈": "NH농협캐피탈",
    "NH농협카드": "NH농협카드",
    "NH농협생명": "NH농협생명보험",
    "NH농협손해보험": "NH농협손해보험",
    "NH아문디": "NH-Amundi자산운용",
    "NH": "NH투자증권",
    "하나캐피탈": "하나캐피탈",
    "하나카드": "하나카드",
    "하나자산운용": "하나자산운용",
    "하나생명": "하나생명보험",
    "하나금융투자": "하나증권",
    "하나": "하나증권",
    "메리츠캐피탈": "메리츠캐피탈",
    "메리츠화재": "메리츠화재해상보험",
    "메리츠자산운용": "메리츠자산운용",
    "메리츠": "메리츠증권",
    "한화생명": "한화생명보험",
    "한화손해보험": "한화손해보험",
    "한화자산운용": "한화자산운용",
    "한화": "한화투자증권",
    "현대차증권": "현대차증권",
    "현대캐피탈": "현대캐피탈",
    "현대카드": "현대카드",
    "현대커머셜": "현대커머셜",
    "현대해상": "현대해상화재보험",
    "현대차": "현대차증권",
    "교보생명": "교보생명보험",
    "교보자산운용": "교보악사자산운용",
    "교보": "교보증권",
    "한국투자캐피탈": "한국투자캐피탈",
    "한국투자저축": "한국투자저축은행",
    "한국투자KIS": "한국투자증권",
    "한국투자": "한국투자증권",
    "DB캐피탈": "DB캐피탈",
    "DB손해보험": "DB손해보험",
    "DB생명": "DB생명보험",
    "DB 드림빅": "DB증권",
    "DB드림빅": "DB증권",
    "DB세이프": "DB증권",
    "동부증권": "DB증권",
    "DB금융투자": "DB증권",
    "DB증권": "DB증권",
    "DB": "DB증권",
    "BNK캐피탈": "BNK캐피탈",
    "BNK증권": "BNK투자증권",
    "BNK": "BNK투자증권",
    "SK": "SK증권",
    "대신": "대신증권",
    "키움": "키움증권",
    "하이": "하이투자증권",
    "IBK": "아이비케이증권",
    "아이비케이": "아이비케이증권",
    "유안타W": "유안타증권",
    "유안타Y": "유안타증권",
    "유안타": "유안타증권",
    "유진": "유진투자증권",
    "부국": "부국증권",
    "한양": "한양증권",
    "케이프": "케이프투자증권",
    "이베스트": "이베스트투자증권",
    "LS": "LS증권",
    "신영": "신영증권",
    "DS": "DS투자증권",
    "다올": "다올투자증권",
    "우리카드": "우리카드",
}

BG = "#F5F0FA"
PANEL = "#FFFFFF"
INPUT_BG = "#FEFBF4"
ACCENT = "#B5A7E6"
ACCENT_DK = "#8573C9"
TEXT = "#3A3550"
MUTED = "#8A84A3"
LOG_BG = "#F9F6FE"

SLEEP = 0.3
SEARCH_DAYS = 90
RESULT_SEARCH_DAYS = 180
INDEX_SCAN_LIMIT = 80
PDF_SCAN_LIMIT = 80
RESULT_SCAN_LIMIT = 50
REQUEST_RETRIES = 3
RETRY_BACKOFF = 0.8
DOWNLOAD_WORKERS = 2
HTTP_MIN_INTERVAL = 0.8
CIRCUIT_FAIL_LIMIT = 3
CIRCUIT_COOLDOWN = 60
SEARCH_CACHE_SECONDS = 6 * 3600

DEFAULT_RUNTIME_SETTINGS = {
    "search_days": SEARCH_DAYS,
    "result_search_days": RESULT_SEARCH_DAYS,
    "index_scan_limit": INDEX_SCAN_LIMIT,
    "pdf_scan_limit": PDF_SCAN_LIMIT,
    "result_scan_limit": RESULT_SCAN_LIMIT,
    "request_retries": REQUEST_RETRIES,
    "retry_backoff": RETRY_BACKOFF,
    "download_workers": DOWNLOAD_WORKERS,
    "http_min_interval": HTTP_MIN_INTERVAL,
    "circuit_fail_limit": CIRCUIT_FAIL_LIMIT,
    "circuit_cooldown": CIRCUIT_COOLDOWN,
    "search_cache_hours": SEARCH_CACHE_SECONDS / 3600,
    "auto_result": True,
    "force_refresh": False,
    "save_termsheet_pdf": True,
    "save_result_pdf": True,
    "use_opendart": True,
}

RUNTIME_PRESETS = {
    "빠른 모드": {
        "search_days": 60,
        "result_search_days": 120,
        "index_scan_limit": 30,
        "pdf_scan_limit": 20,
        "result_scan_limit": 20,
        "download_workers": 3,
        "http_min_interval": 0.5,
        "search_cache_hours": 24,
        "auto_result": True,
        "force_refresh": False,
    },
    "균형 모드": DEFAULT_RUNTIME_SETTINGS,
    "정밀 모드": {
        "search_days": 180,
        "result_search_days": 365,
        "index_scan_limit": 120,
        "pdf_scan_limit": 120,
        "result_scan_limit": 100,
        "request_retries": 3,
        "retry_backoff": 0.8,
        "download_workers": 2,
        "http_min_interval": 0.8,
        "circuit_fail_limit": 3,
        "circuit_cooldown": 60,
        "search_cache_hours": 6,
        "auto_result": True,
        "force_refresh": False,
    },
    "안전 모드": {
        "search_days": 180,
        "result_search_days": 365,
        "index_scan_limit": 150,
        "pdf_scan_limit": 150,
        "result_scan_limit": 120,
        "request_retries": 4,
        "retry_backoff": 0.8,
        "download_workers": 1,
        "http_min_interval": 0.8,
        "circuit_fail_limit": 3,
        "circuit_cooldown": 60,
        "search_cache_hours": 6,
        "auto_result": True,
        "force_refresh": True,
    },
}

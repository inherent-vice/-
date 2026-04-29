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
    "미래에셋생명": "미래에셋생명",
    "미래에셋자산운용": "미래에셋자산운용",
    "미래에셋대우": "미래에셋증권",
    "대우증권": "미래에셋증권",
    "미래에셋": "미래에셋증권",
    "삼성생명": "삼성생명보험",
    "삼성화재": "삼성화재해상보험",
    "삼성카드": "삼성카드",
    "삼성자산운용": "삼성자산운용",
    "삼성": "삼성증권",
    "롯데카드": "롯데카드",
    "비씨카드": "비씨카드",
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
    "KB라이프": "케이비라이프생명보험",
    "KB손해보험": "KB손해보험",
    "KB자산운용": "케이비자산운용",
    "KB금융지주": "KB금융",
    "KB금융": "KB금융",
    "KB able": "케이비증권",
    "KBable": "케이비증권",
    "KB STAR": "케이비증권",
    "KB": "케이비증권",
    "NH투자": "NH투자증권",
    "NH농협캐피탈": "엔에이치농협캐피탈",
    "NH농협카드": "NH농협카드",
    "NH농협생명": "농협생명보험",
    "농협생명": "농협생명보험",
    "농협생명보험": "농협생명보험",
    "NH농협손해보험": "NH농협손해보험",
    "NH아문디": "NH-Amundi자산운용",
    "NH": "NH투자증권",
    "하나캐피탈": "하나캐피탈",
    "하나카드": "하나카드",
    "하나자산운용": "하나자산운용",
    "하나생명": "하나생명보험",
    "하나금융투자": "하나증권",
    "H&F투자": "하나증권",
    "하나": "하나증권",
    "메리츠캐피탈": "메리츠캐피탈",
    "메리츠화재": "메리츠화재해상보험",
    "메리츠자산운용": "메리츠자산운용",
    "메리츠": "메리츠증권",
    "동양생명": "동양생명",
    "에이비엘생명": "에이비엘생명보험",
    "ABL생명": "에이비엘생명보험",
    "푸본현대생명": "푸본현대생명보험",
    "KDB생명": "케이디비생명보험",
    "케이디비생명": "케이디비생명보험",
    "한화생명": "한화생명",
    "한화손해보험": "한화손해보험",
    "한화자산운용": "한화자산운용",
    "한화": "한화투자증권",
    "현대차증권": "현대차증권",
    "현대캐피탈": "현대캐피탈",
    "현대카드": "현대카드",
    "현대커머셜": "현대커머셜",
    "현대해상": "현대해상",
    "현대차": "현대차증권",
    "교보생명": "교보생명보험",
    "교보자산운용": "교보악사자산운용",
    "교보": "교보증권",
    "한국투자캐피탈": "한국투자캐피탈",
    "한국투자저축": "한국투자저축은행",
    "한국투자KIS": "한국투자증권",
    "한국투자금융지주": "한국투자금융지주",
    "한국투자": "한국투자증권",
    "DB캐피탈": "DB캐피탈",
    "DB손해보험": "DB손해보험",
    "DB손보": "DB손해보험",
    "DB생명": "DB생명보험",
    "DB 드림빅": "DB증권",
    "DB드림빅": "DB증권",
    "해피플러스": "DB증권",
    "DB세이프": "DB증권",
    "동부증권": "DB증권",
    "DB금융투자": "DB증권",
    "DB증권": "DB증권",
    "DB": "DB증권",
    "BNK캐피탈": "BNK캐피탈",
    "BNK금융지주": "BNK금융지주",
    "BNK금융": "BNK금융지주",
    "BNK증권": "BNK투자증권",
    "BNK": "BNK투자증권",
    "SKADVANCED": "SK어드밴스드",
    "SK어드밴스드": "SK어드밴스드",
    "SK": "SK증권",
    "산은캐피탈": "산은캐피탈",
    "아이엠캐피탈": "아이엠캐피탈",
    "롯데물산": "롯데물산",
    "대신": "대신증권",
    "키움": "키움증권",
    "하이": "아이엠증권",
    "IBK": "아이비케이투자증권",
    "아이비케이": "아이비케이투자증권",
    "유안타W": "유안타증권",
    "유안타Y": "유안타증권",
    "유안타": "유안타증권",
    "유진": "유진증권",
    "부국": "부국증권",
    "한양": "한양증권",
    "케이프": "케이프투자증권",
    "이베스트": "이베스트투자증권",
    "LS": "LS증권",
    "신영": "신영증권",
    "DS": "DS투자증권",
    "다올": "다올투자증권",
    "우리카드": "우리카드",
    # 케이비 한글 표기 (auto-extracted)
    "케이비국민카드": "케이비국민카드",
    "케이비캐피탈": "케이비캐피탈",
    "케이비손해보험": "KB손해보험",
    "케이비라이프생명보험": "케이비라이프생명보험",
    # 엔에이치 한글 표기 (DART 정식명은 "엔에이치농협캐피탈")
    "엔에이치농협캐피탈": "엔에이치농협캐피탈",
    # 시중 은행 (대부분 발행체로 직접 검색됨)
    "국민은행": "국민은행",
    "우리은행": "우리은행",
    "우리금융": "우리금융지주",
    "하나은행": "하나은행",
    "하나금융": "하나금융지주",
    "신한은행": "신한은행",
    "신한금융": "신한지주",
    "농협은행": "농협은행",
    "수협은행": "수협은행",
    "부산은행": "부산은행",
    "경남은행": "경남은행",
    "광주은행": "광주은행",
    "전북은행": "전북은행",
    "제주은행": "제주은행",
    "아이엠뱅크": "아이엠뱅크",
    "iM금융지주": "iM금융지주",
    # 기업은행 — OpenDART corp 명칭은 "기업은행"
    "기업은행": "기업은행",
    "중소기업은행": "기업은행",
    # 산업금융채권 = 한국산업은행 발행 (비상장이라 키워드검색 0건일 수 있음 — 별도 이슈)
    "산금": "한국산업은행",
    "산업금융채권": "한국산업은행",
    "한국산업은행": "한국산업은행",
    # 농업금융채권 = 농협은행 발행
    "농업금융채권": "농협은행",
    "농금": "농협은행",
    "농협금융": "농협금융지주",
    # 수산금융채권 = 수협은행 발행
    "수산금융채권": "수협은행",
    # 한국수출입금융 = 한국수출입은행
    "한국수출입금융": "한국수출입은행",
    "한국수출입은행": "한국수출입은행",
    # 한국주택금융공사 (MBS 등)
    "한국주택금융공사": "한국주택금융공사",
    "주택금융공사": "한국주택금융공사",
    # 기타 공기업/공공기관
    "한국도로공사": "한국도로공사",
    "도로공사": "한국도로공사",
    "한국철도공사": "한국철도공사",
    "한국토지주택공사": "한국토지주택공사",
    "토지주택채권": "한국토지주택공사",
    "주택도시보증공사": "주택도시보증공사",
    "한국지역난방공사": "지역난방공사",
    "지역난방공사": "지역난방공사",
    "한국장학재단": "한국장학재단",
    "중소벤처기업진흥공단": "중소벤처기업진흥공단",
    "중소벤처기업진흥채권": "중소벤처기업진흥공단",
    "공급망안정화기금": "공급망안정화기금",
    # 외국계 은행
    "스탠다드차타드은행": "한국스탠다드차타드은행",
    # 보험 (auto-extracted prefix without 보험 suffix)
    "코리안리재보험": "코리안리",
    "코리안리": "코리안리",
    "흥국화재": "흥국화재",
    "흥국생명": "흥국생명보험",
    "롯데손해보험": "롯데손해보험",
    "농협손해보험": "NH농협손해보험",
    # 캐피탈/지주
    "JB금융지주": "JB금융지주",
    "JB우리캐피탈": "제이비우리캐피탈",
    "JB 우리캐피탈": "제이비우리캐피탈",
    "DGB금융지주": "iM금융지주",
    # iM증권 (구 하이투자증권)
    "아이엠증권": "아이엠증권",
    # 회사채 발행체 (corp_code 검증)
    "신세계디에프": "신세계디에프",
    "에스케이인천석화": "SK인천석유화학",
    "씨제이 씨지브이": "씨제이씨지브이",
    "씨제이씨지브이": "씨제이씨지브이",
    "이마트": "이마트",
    "풀무원 신종자본증권": "풀무원식품",
    "풀무원": "풀무원식품",
    "풀무원식품": "풀무원식품",
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
RESULT_SEARCH_DAYS = 365
INDEX_SCAN_LIMIT = 80
PDF_SCAN_LIMIT = 80
RESULT_SCAN_LIMIT = 120
RESULT_BODY_SCAN_LIMIT = 40
RESULT_FRONT_TEXT_SCAN_LIMIT = 20
REQUEST_RETRIES = 3
RETRY_BACKOFF = 0.8
DOWNLOAD_WORKERS = 2
HTTP_MIN_INTERVAL = 0.8
CIRCUIT_FAIL_LIMIT = 3
CIRCUIT_COOLDOWN = 60
SEARCH_CACHE_SECONDS = 6 * 3600
CACHE_AUTO_PRUNE = True
CACHE_SEARCH_DAYS = 14
CACHE_DOCUMENT_DAYS = 90
CACHE_PDF_DAYS = 30

DEFAULT_RUNTIME_SETTINGS = {
    "search_days": SEARCH_DAYS,
    "result_search_days": RESULT_SEARCH_DAYS,
    "index_scan_limit": INDEX_SCAN_LIMIT,
    "pdf_scan_limit": PDF_SCAN_LIMIT,
    "result_scan_limit": RESULT_SCAN_LIMIT,
    "result_body_scan_limit": RESULT_BODY_SCAN_LIMIT,
    "result_front_text_scan_limit": RESULT_FRONT_TEXT_SCAN_LIMIT,
    "request_retries": REQUEST_RETRIES,
    "retry_backoff": RETRY_BACKOFF,
    "download_workers": DOWNLOAD_WORKERS,
    "http_min_interval": HTTP_MIN_INTERVAL,
    "circuit_fail_limit": CIRCUIT_FAIL_LIMIT,
    "circuit_cooldown": CIRCUIT_COOLDOWN,
    "search_cache_hours": SEARCH_CACHE_SECONDS / 3600,
    "cache_auto_prune": CACHE_AUTO_PRUNE,
    "cache_search_days": CACHE_SEARCH_DAYS,
    "cache_document_days": CACHE_DOCUMENT_DAYS,
    "cache_pdf_days": CACHE_PDF_DAYS,
    "auto_result": True,
    "force_refresh": False,
    "save_termsheet_pdf": True,
    "save_result_pdf": True,
    "use_opendart": True,
    "filter_termsheet_targets": True,
}

RUNTIME_PRESETS = {
    "빠른 모드": {
        "search_days": 60,
        "result_search_days": 120,
        "index_scan_limit": 30,
        "pdf_scan_limit": 20,
        "result_scan_limit": 20,
        "result_body_scan_limit": 12,
        "result_front_text_scan_limit": 8,
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
        "result_body_scan_limit": 70,
        "result_front_text_scan_limit": 30,
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
        "result_body_scan_limit": 90,
        "result_front_text_scan_limit": 45,
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

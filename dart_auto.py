"""
DART 텀싯 자동 다운로더 (비공식 웹 API)

- 사용자가 종목코드/종목명 입력 → 회사 + 회차로 DART 검색 → PDF 저장
- 종목명에 (신종) 또는 (후) 포함 시 신종자본증권 텀싯으로 매칭
- 그 외에는 기타파생결합사채/증권 또는 투자설명서로 매칭
- 발행취소 확인은 버튼으로 별도 실행, 보고서 PDF 저장 여부도 체크박스
"""
from __future__ import annotations

import io
import json
import os
import re
import datetime as dt
import threading
import time
from pathlib import Path
from tkinter import Tk, ttk, StringVar, Text, END, messagebox
import tkinter as tk

import requests

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

# ─────────────────────── 상수 ───────────────────────

if getattr(sys, "frozen", False):
    BUNDLE_DIR = Path(sys._MEIPASS)        # PyInstaller 임시 리소스 경로
    APP_DIR = Path(sys.executable).parent  # exe 옆 (사용자 데이터)
else:
    BUNDLE_DIR = Path(__file__).parent
    APP_DIR = Path(__file__).parent

ISSUERS_PATH = APP_DIR / "issuers.json"

# 내장 기본 매핑 (prefix → DART 등록 회사명). 긴 prefix 우선.
DEFAULT_ISSUERS = {
    "트루": "한국투자증권", "한화스마트": "한화투자증권", "키움YOU": "키움증권",
    "미래에셋캐피탈": "미래에셋캐피탈", "미래에셋생명": "미래에셋생명보험",
    "미래에셋자산운용": "미래에셋자산운용", "미래에셋": "미래에셋증권",
    "삼성생명": "삼성생명보험", "삼성화재": "삼성화재해상보험",
    "삼성카드": "삼성카드", "삼성자산운용": "삼성자산운용", "삼성": "삼성증권",
    "신한캐피탈": "신한캐피탈", "신한카드": "신한카드",
    "신한라이프": "신한라이프생명보험", "신한자산운용": "신한자산운용",
    "신한": "신한투자증권",
    "KB캐피탈": "케이비캐피탈", "KB카드": "케이비국민카드",
    "KB국민카드": "케이비국민카드", "KB라이프": "KB라이프생명보험",
    "KB손해보험": "KB손해보험", "KB자산운용": "케이비자산운용", "KB": "KB증권",
    "NH농협캐피탈": "NH농협캐피탈", "NH농협카드": "NH농협카드",
    "NH농협생명": "NH농협생명보험", "NH농협손해보험": "NH농협손해보험",
    "NH아문디": "NH-Amundi자산운용", "NH": "NH투자증권",
    "하나캐피탈": "하나캐피탈", "하나카드": "하나카드",
    "하나자산운용": "하나자산운용", "하나생명": "하나생명보험", "하나": "하나증권",
    "메리츠캐피탈": "메리츠캐피탈", "메리츠화재": "메리츠화재해상보험",
    "메리츠자산운용": "메리츠자산운용", "메리츠": "메리츠증권",
    "한화생명": "한화생명보험", "한화손해보험": "한화손해보험",
    "한화자산운용": "한화자산운용", "한화": "한화투자증권",
    "현대차증권": "현대차증권", "현대캐피탈": "현대캐피탈",
    "현대카드": "현대카드", "현대커머셜": "현대커머셜",
    "현대해상": "현대해상화재보험", "현대차": "현대차증권",
    "교보생명": "교보생명보험", "교보자산운용": "교보악사자산운용", "교보": "교보증권",
    "한국투자캐피탈": "한국투자캐피탈", "한국투자저축": "한국투자저축은행",
    "한국투자": "한국투자증권",
    "DB캐피탈": "DB캐피탈", "DB손해보험": "DB손해보험",
    "DB생명": "DB생명보험", "DB": "DB금융투자",
    "BNK캐피탈": "BNK캐피탈", "BNK": "BNK투자증권",
    "SK": "SK증권", "대신": "대신증권", "키움": "키움증권",
    "하이": "하이투자증권", "IBK": "아이비케이증권", "아이비케이": "아이비케이증권",
    "유안타": "유안타증권", "유진": "유진투자증권",
    "부국": "부국증권", "한양": "한양증권",
    "케이프": "케이프투자증권", "이베스트": "이베스트투자증권",
    "LS": "LS증권", "신영": "신영증권",
    "DS": "DS투자증권", "다올": "다올투자증권",
    "우리카드": "우리카드",
}

def load_issuers():
    """기본값 + 사용자 JSON 병합. 사용자 항목이 우선."""
    merged = dict(DEFAULT_ISSUERS)
    user = load_json(ISSUERS_PATH, {}) or {}
    for k, v in user.items():
        if k.startswith("_") or not isinstance(v, str) or not v.strip():
            continue
        merged[k.strip()] = v.strip()
    return merged

def save_user_issuers(user_dict):
    """사용자 매핑만 저장. 기본값과 같은 항목은 제외."""
    cleaned = {"_comment": "사용자 추가 매핑. 기본값은 코드에 내장."}
    for k, v in user_dict.items():
        if k.startswith("_") or not v:
            continue
        if DEFAULT_ISSUERS.get(k) == v:
            continue  # 기본값과 동일 → 저장 불필요
        cleaned[k] = v
    save_json(ISSUERS_PATH, cleaned)
STATE_DIR = APP_DIR / "state"
LOGO_PATH = BUNDLE_DIR / "kap_logo.png"
DOWNLOADS = Path.home() / "Downloads"

# 파스텔 팔레트
BG        = "#F5F0FA"   # 연보라
PANEL     = "#FFFFFF"
INPUT_BG  = "#FEFBF4"   # 연크림
ACCENT    = "#B5A7E6"   # 라벤더
ACCENT_DK = "#8573C9"
TEXT      = "#3A3550"
MUTED     = "#8A84A3"
LOG_BG    = "#F9F6FE"

DART_BASE  = "https://dart.fss.or.kr"
SEARCH_URL = f"{DART_BASE}/dsab007/detailSearch.ax"
INDEX_URL  = f"{DART_BASE}/dsaf001/main.do"
PDF_URL    = f"{DART_BASE}/pdf/download/pdf.do"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
    "Referer": f"{DART_BASE}/dsab007/main.do",
}
SLEEP = 0.3
SEARCH_DAYS = 90  # 텀싯/실적 검색 기간

# ─────────────────────── 유틸 ───────────────────────

def load_json(path, default=None):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default
    return default

def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def today_str():
    return dt.date.today().strftime("%Y%m%d")

def get_state():
    STATE_DIR.mkdir(exist_ok=True)
    p = STATE_DIR / f"{today_str()}.json"
    return p, load_json(p, {"searched": []})

def safe_filename(s):
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip()

# ─────────────────────── 입력 파싱 ───────────────────────

def parse_input_line(line):
    line = line.strip()
    if not line:
        return None
    parts = re.split(r"\s+", line, maxsplit=1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return "", parts[0]

def extract_round(stock_name):
    """종목명 끝의 회차. '134-1' 같은 세부회차도 통째 캡처."""
    # 괄호 이후 끝부분 숫자
    s = re.sub(r"\(.*?\)", "", stock_name)
    m = re.search(r"(\d+(?:-\d+)?)\s*회?\s*$", s)
    if not m:
        return (None, None)
    full = m.group(1)
    base = full.split("-")[0]
    return (full, base)

def find_issuer(stock_name, issuers):
    """
    긴 prefix 우선 매핑. 매핑 없으면 종목명에서 회사명 자동 추출.
    예: '아이비케이증권(DLB)450' → '아이비케이증권'
        '메리츠캐피탈 제10회' → '메리츠캐피탈'
    반환: (회사명, 매핑여부)
    """
    items = [(k, v) for k, v in issuers.items()
             if not k.startswith("_") and isinstance(v, str)]
    items.sort(key=lambda x: len(x[0]), reverse=True)
    for prefix, company in items:
        if stock_name.startswith(prefix):
            return (company, True)

    # fallback: 괄호/숫자 이전까지를 회사명으로 추정
    m = re.match(r"\s*([A-Za-z가-힣]+)", stock_name)
    if m:
        return (m.group(1), False)
    return (None, False)

def is_subordinated(stock_name):
    """(신종) 또는 (후) 포함 → 신종자본증권."""
    return bool(re.search(r"\((신종|후[^\)]*)\)", stock_name))

def extract_product_type(stock_name):
    """종목명 괄호에서 상품유형 추출. DLB/ELB/DLS/ELS/SUB(신종·후)/None."""
    if is_subordinated(stock_name):
        return "SUB"
    m = re.search(r"\((DLB|DLS|ELB|ELS)\)", stock_name, re.I)
    return m.group(1).upper() if m else None

def round_in(text, full, base):
    """
    타이틀 매칭. '제2,681회' 쉼표는 무시.
    full 우선, 없으면 base로 fallback. base는 세부회차(-1,-2) 타이틀도 허용.
    """
    if not full:
        return False
    t = re.sub(r"(?<=\d),(?=\d)", "", text)  # 매칭용으로만 쉼표 제거
    if full in t:
        return True
    if base and base != full:
        # 앞: 숫자/하이픈 아닌 것,  뒤: 숫자 아닌 것 (하이픈 허용 → '280-1'도 OK)
        if re.search(rf"(?<![\d\-]){re.escape(base)}(?!\d)", t):
            return True
    return False

# ─────────────────────── DART 비공식 API ───────────────────────

class Dart:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update(HEADERS)

    def search(self, company, start, end, report_name="", page_size=100):
        """
        공시 검색 → [(rcp_no, title), ...]
        title은 검색 결과 행의 보고서명 텍스트.
        """
        results = []
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
            try:
                r = self.s.post(SEARCH_URL, data=data, timeout=20)
                r.raise_for_status()
            except Exception as e:
                raise RuntimeError(f"검색 실패: {e}")
            html = r.text
            # 패턴: openReportViewer('rcpNo') ... >보고서명<
            pairs = re.findall(
                r"openReportViewer\(\s*['\"](\d{14})['\"][^>]*\)[^>]*>\s*([^<]+?)\s*<",
                html,
            )
            if not pairs:
                # fallback: rcpNo만
                rcps = re.findall(r"\b(\d{14})\b", html)
                pairs = [(r, "") for r in rcps]
            new = [p for p in pairs if p[0] not in {x[0] for x in results}]
            if not new:
                break
            results.extend(new)
            if len(new) < page_size // 2:
                break
            page += 1
            time.sleep(SLEEP)
        return results

    def get_dcm_no(self, rcp_no):
        dcm, _ = self.get_doc_info(rcp_no)
        return dcm

    def get_doc_info(self, rcp_no):
        """
        공시 인덱스 페이지에서 (dcm_no, 문서타이틀 리스트) 반환.
        문서타이틀은 tree.add(...) 3번째 인자 등 인덱스에 표시되는 문서명.
        """
        try:
            r = self.s.get(INDEX_URL, params={"rcpNo": rcp_no}, timeout=20)
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"인덱스 실패: {e}")
        html = r.text

        # dcm_no
        nums = re.findall(r"'(\d{8})'", html)
        dcm = next((n for n in nums if not n.startswith("00")), None)

        # 문서 타이틀: .add('x','y','타이틀', ...) 패턴 우선
        titles = re.findall(
            r"\.add\(\s*['\"][^'\"]*['\"]\s*,\s*['\"][^'\"]*['\"]\s*,\s*['\"]([^'\"]+)['\"]",
            html,
        )
        # fallback: 한글 포함 따옴표 문자열 (길이 8자 이상)
        if not titles:
            titles = [t for t in re.findall(r"['\"]([^'\"]{8,})['\"]", html)
                      if re.search(r"[가-힣]", t)]
        return dcm, titles

    def download_pdf(self, rcp_no, dcm_no):
        try:
            r = self.s.get(
                PDF_URL,
                params={"rcp_no": rcp_no, "dcm_no": dcm_no},
                timeout=120,
            )
            r.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"PDF 다운 실패: {e}")
        if not r.content.startswith(b"%PDF"):
            return None
        return r.content

# ─────────────────────── 매칭 로직 ───────────────────────

# 보고서명 키워드 그룹
KW_TERMSHEET_DERIV = ["일괄신고추가서류", "기타파생결합", "투자설명서"]
KW_TERMSHEET_SUBORD = ["신종자본증권", "후순위", "투자설명서", "증권신고서"]
KW_RESULT = ["증권발행실적보고서"]

def termsheet_keywords(product):
    """유형별 (must, also) 키워드."""
    if product in ("DLB", "ELB"):
        return (["기타파생결합사채"], ["투자설명서"])
    if product in ("DLS", "ELS"):
        return (["기타파생결합증권"], ["투자설명서"])
    if product == "SUB":
        return (["신종자본증권"], ["투자설명서", "증권신고서"])
    return (["일괄신고추가서류", "기타파생결합"], ["투자설명서", "증권신고서"])

def termsheet_candidates(pairs, product):
    """
    키워드로 1차 후보 필터링. 최신 rcpNo부터 정렬.
    반환: [(rcp, title, priority)]  priority 0=primary, 1=secondary
    """
    must, also = termsheet_keywords(product)
    out = []
    for rcp, title in pairs:
        if any(k in title for k in must):
            out.append((rcp, title, 0))
        elif any(k in title for k in also):
            out.append((rcp, title, 1))
    # rcpNo는 YYYYMMDD... 14자리 → 큰 순이 최근
    out.sort(key=lambda x: (x[2], -int(x[0])))
    return out

def pdf_front_text(pdf_bytes, max_pages=5):
    """PDF 앞쪽 max_pages 페이지 텍스트 추출 (회차 검색용)."""
    if not HAS_PDFPLUMBER:
        return ""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            return "\n".join((p.extract_text() or "") for p in pdf.pages[:max_pages])
    except Exception:
        return ""

def match_termsheet(pairs, round_full, round_base, product):
    """
    검색 결과 [(rcp_no, title), ...] 중 적합한 텀싯 1건 선정.
    product: 'DLB','ELB','DLS','ELS','SUB',None
    반환: (rcp_no, title, is_fallback)
    """
    # 유형별 키워드
    if product in ("DLB", "ELB"):
        must = ["기타파생결합사채"]; also = ["투자설명서"]
    elif product in ("DLS", "ELS"):
        must = ["기타파생결합증권"]; also = ["투자설명서"]
    elif product == "SUB":
        must = ["신종자본증권"]; also = ["투자설명서", "증권신고서"]
    else:
        must = ["일괄신고추가서류", "기타파생결합"]; also = ["투자설명서", "증권신고서"]

    primary = []   # must 키워드 매칭
    secondary = [] # also 키워드 매칭
    for rcp, title in pairs:
        if any(k in title for k in must):
            primary.append((rcp, title))
        elif any(k in title for k in also):
            secondary.append((rcp, title))

    def pick(cands):
        if not cands:
            return None
        if round_full:
            f = [c for c in cands if round_in(c[1], round_full, round_base)]
            if f:
                return (f[0][0], f[0][1], False)
        return None  # 회차 불일치 → None (fallback은 상위에서 결정)

    # primary에서 회차 일치 먼저, 없으면 secondary. 어디에도 없으면 None.
    hit = pick(primary) or pick(secondary)
    return hit if hit else (None, None, False)

def match_result(pairs, round_full, round_base):
    """증권발행실적보고서 매칭."""
    cand = [(rcp, title) for rcp, title in pairs if "증권발행실적보고서" in title]
    if round_full:
        f = [c for c in cand if round_in(c[1], round_full, round_base)]
        if f:
            cand = f
    return cand[0] if cand else (None, None)

# ─────────────────────── 발행실적 PDF 분석 ───────────────────────

def analyze_result_pdf(pdf_bytes):
    """
    반환: (status, label, reason)
    status ∈ {'cancelled','issued','unknown'}
    """
    if not HAS_PDFPLUMBER:
        return ("unknown", "알 수 없음", "pdfplumber 미설치")
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join((p.extract_text() or "") for p in pdf.pages[:5])
    except Exception as e:
        return ("unknown", "알 수 없음", f"PDF 파싱 실패: {e}")

    if "발행이 취소" in text or "발행취소" in text:
        return ("cancelled", "발행취소", "본문에 '발행취소'")
    for kw in ("배정금액", "청약금액", "총배정금액"):
        for m in re.finditer(rf"{kw}[^0-9가-힣]{{0,15}}([0-9,]+)", text):
            v = m.group(1).replace(",", "")
            if v.isdigit() and int(v) == 0:
                return ("cancelled", "발행취소", f"{kw}=0")
    if "전량 배정" in text or "전량배정" in text or "배정되었습니다" in text:
        return ("issued", "발행됨", "정상 배정 문구 확인")
    return ("unknown", "알 수 없음", "청약 상황 미공시")

# ─────────────────────── GUI ───────────────────────

class IssuerEditor:
    """발행사 매핑 편집 팝업."""
    def __init__(self, parent, app):
        self.app = app
        self.user_overrides = dict(load_json(ISSUERS_PATH, {}) or {})

        win = tk.Toplevel(parent)
        self.win = win
        win.title("발행사 매핑 편집")
        win.configure(bg=BG)
        win.geometry("620x560")

        tk.Label(win, text="발행사 매핑", bg=BG, fg=ACCENT_DK,
                 font=("맑은 고딕", 13, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(win, text="종목명 시작글자(prefix) → DART 등록 회사명. 긴 prefix가 우선 적용됩니다.",
                 bg=BG, fg=MUTED, font=("맑은 고딕", 9)).pack(anchor="w", padx=16)

        # 표
        frame = tk.Frame(win, bg=BG)
        frame.pack(fill="both", expand=True, padx=16, pady=10)
        cols = ("prefix", "company", "src")
        self.tree = ttk.Treeview(frame, columns=cols, show="headings", height=15)
        self.tree.heading("prefix", text="종목명 prefix")
        self.tree.heading("company", text="DART 회사명")
        self.tree.heading("src", text="구분")
        self.tree.column("prefix", width=200)
        self.tree.column("company", width=280)
        self.tree.column("src", width=80, anchor="center")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        # 입력부
        form = tk.Frame(win, bg=BG)
        form.pack(fill="x", padx=16)
        tk.Label(form, text="prefix", bg=BG, fg=TEXT,
                 font=("맑은 고딕", 9)).grid(row=0, column=0, sticky="w")
        tk.Label(form, text="회사명", bg=BG, fg=TEXT,
                 font=("맑은 고딕", 9)).grid(row=0, column=1, sticky="w", padx=(8, 0))
        self.prefix_var = tk.StringVar()
        self.company_var = tk.StringVar()
        tk.Entry(form, textvariable=self.prefix_var, font=("맑은 고딕", 10),
                 bg=INPUT_BG, relief="flat", width=22).grid(row=1, column=0, sticky="we")
        tk.Entry(form, textvariable=self.company_var, font=("맑은 고딕", 10),
                 bg=INPUT_BG, relief="flat", width=30).grid(row=1, column=1, sticky="we", padx=(8, 8))
        ttk.Button(form, text="추가 / 수정", command=self._add).grid(row=1, column=2)
        ttk.Button(form, text="삭제", style="Ghost.TButton",
                   command=self._delete).grid(row=1, column=3, padx=6)
        form.columnconfigure(1, weight=1)

        # 하단
        footer = tk.Frame(win, bg=BG)
        footer.pack(fill="x", padx=16, pady=(12, 14))
        tk.Label(footer, text="💡 '구분=기본'은 내장값입니다. 같은 prefix로 추가하면 내 설정이 우선 적용됩니다.",
                 bg=BG, fg=MUTED, font=("맑은 고딕", 9)).pack(side="left")
        ttk.Button(footer, text="닫기", style="Ghost.TButton",
                   command=win.destroy).pack(side="right")
        ttk.Button(footer, text="저장", command=self._save).pack(side="right", padx=6)

        self._refresh()

    def _current(self):
        """사용자 오버라이드를 기본값 위에 덮은 최종 dict."""
        m = dict(DEFAULT_ISSUERS)
        for k, v in self.user_overrides.items():
            if k.startswith("_") or not isinstance(v, str):
                continue
            m[k] = v
        return m

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        merged = self._current()
        rows = sorted(merged.items(), key=lambda x: (-len(x[0]), x[0]))
        for k, v in rows:
            if self.user_overrides.get(k) == v:
                src = "사용자"
            elif DEFAULT_ISSUERS.get(k) == v:
                src = "기본"
            else:
                src = "사용자"
            self.tree.insert("", "end", values=(k, v, src))

    def _on_select(self, _ev):
        sel = self.tree.focus()
        if not sel:
            return
        p, c, _ = self.tree.item(sel, "values")
        self.prefix_var.set(p)
        self.company_var.set(c)

    def _add(self):
        p = self.prefix_var.get().strip()
        c = self.company_var.get().strip()
        if not p or not c:
            messagebox.showwarning("입력 필요", "prefix와 회사명 모두 입력하세요.", parent=self.win)
            return
        self.user_overrides[p] = c
        self._refresh()
        self.prefix_var.set("")
        self.company_var.set("")

    def _delete(self):
        p = self.prefix_var.get().strip()
        if not p:
            return
        if p in self.user_overrides:
            del self.user_overrides[p]
            self._refresh()
            self.prefix_var.set("")
            self.company_var.set("")
        elif p in DEFAULT_ISSUERS:
            messagebox.showinfo("삭제 불가",
                                "내장 기본값은 삭제할 수 없습니다. 다른 회사명으로 덮어쓰세요.",
                                parent=self.win)

    def _save(self):
        save_user_issuers(self.user_overrides)
        self.app.issuers = load_issuers()
        messagebox.showinfo("저장 완료", "매핑이 저장되었습니다.", parent=self.win)
        self.win.destroy()


class App:
    def __init__(self, root):
        self.root = root
        root.title("DART 텀싯 자동 다운로더")
        root.geometry("840x660")

        self.issuers = load_issuers()
        self.dart = Dart()
        self._build_ui()

    def _build_ui(self):
        self.root.configure(bg=BG)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("맑은 고딕", 10))
        style.configure("Title.TLabel", background=BG, foreground=ACCENT_DK,
                        font=("맑은 고딕", 15, "bold"))
        style.configure("Sub.TLabel", background=BG, foreground=MUTED,
                        font=("맑은 고딕", 9))
        style.configure("TButton", background=ACCENT, foreground="white",
                        font=("맑은 고딕", 10, "bold"), padding=(12, 6),
                        borderwidth=0, relief="flat")
        style.map("TButton",
                  background=[("active", ACCENT_DK), ("pressed", ACCENT_DK)])
        style.configure("Ghost.TButton", background=PANEL, foreground=ACCENT_DK,
                        borderwidth=1, relief="solid")
        style.map("Ghost.TButton", background=[("active", INPUT_BG)])
        style.configure("TCheckbutton", background=BG, foreground=TEXT,
                        font=("맑은 고딕", 9))
        style.map("TCheckbutton", background=[("active", BG)])

        # ─ 상단 헤더 ─
        header = ttk.Frame(self.root, padding=(16, 14, 16, 10))
        header.pack(fill="x")

        self._logo_img = None
        if LOGO_PATH.exists():
            try:
                self._logo_img = tk.PhotoImage(file=str(LOGO_PATH))
                # 너무 크면 축소
                w = self._logo_img.width()
                if w > 120:
                    self._logo_img = self._logo_img.subsample(max(1, w // 100))
                tk.Label(header, image=self._logo_img, bg=BG).pack(side="left", padx=(0, 12))
            except Exception:
                self._logo_img = None
        if not self._logo_img:
            tk.Label(header, text="KAP", bg=ACCENT, fg="white",
                     font=("맑은 고딕", 14, "bold"),
                     padx=14, pady=6).pack(side="left", padx=(0, 12))

        title_box = ttk.Frame(header)
        title_box.pack(side="left", fill="x", expand=True)
        ttk.Label(title_box, text="DART 텀싯 자동 다운로더", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_box, text="파생결합증권 · 신종자본증권 발행 문서 수집", style="Sub.TLabel").pack(anchor="w")

        ttk.Button(header, text="발행사 매핑 편집", style="Ghost.TButton",
                   command=self.edit_issuers).pack(side="right")

        # ─ 본문 ─
        body = tk.Frame(self.root, bg=BG, padx=16, pady=6)
        body.pack(fill="both", expand=True)

        ttk.Label(body,
                  text="종목코드 / 종목명  (한 줄에 하나)   예:  KR6082971G42  미래에셋캐피탈134-1"
                  ).pack(anchor="w", pady=(0, 4))
        self.input_txt = Text(body, height=7, font=("Consolas", 10),
                              bg=INPUT_BG, fg=TEXT, relief="flat",
                              highlightthickness=1, highlightbackground=ACCENT,
                              highlightcolor=ACCENT_DK, padx=10, pady=8)
        self.input_txt.pack(fill="x", pady=(0, 6))

        tips = (
            "💡  종목코드와 종목명을 함께 입력해야 정확한 매칭이 가능합니다.\n"
            "     다운로드 후 파일을 열어 회차·상품유형이 맞는지 반드시 확인해주세요."
        )
        tk.Label(body, text=tips, bg=BG, fg=MUTED,
                 font=("맑은 고딕", 9), justify="left",
                 anchor="w").pack(fill="x", pady=(0, 8))

        btns = tk.Frame(body, bg=BG)
        btns.pack(fill="x")
        ttk.Button(btns, text="① 텀싯 다운로드", command=self.run_download).pack(side="left")
        ttk.Button(btns, text="② 발행취소 확인 (전체)", style="Ghost.TButton",
                   command=self.run_check).pack(side="left", padx=8)
        ttk.Button(btns, text="오늘 검색 목록", style="Ghost.TButton",
                   command=self.show_today).pack(side="right")

        ttk.Label(body, text="로그").pack(anchor="w", pady=(12, 4))
        self.log_txt = Text(body, height=18, font=("Consolas", 9),
                            bg=LOG_BG, fg=TEXT, relief="flat",
                            highlightthickness=1, highlightbackground="#E0D8F2",
                            padx=10, pady=8)
        self.log_txt.pack(fill="both", expand=True, pady=(0, 10))

        self.status = StringVar(value=f"저장 경로: {DOWNLOADS}")
        tk.Label(self.root, textvariable=self.status, anchor="w",
                 bg="#EDE4FA", fg=MUTED, padx=12, pady=5,
                 font=("맑은 고딕", 9)).pack(fill="x", side="bottom")

    def log(self, msg):
        ts = dt.datetime.now().strftime("%H:%M:%S")
        self.log_txt.insert(END, f"[{ts}] {msg}\n")
        self.log_txt.see(END)
        self.root.update_idletasks()

    def edit_issuers(self):
        IssuerEditor(self.root, self)

    def show_today(self):
        _, st = get_state()
        items = st.get("searched", [])
        if not items:
            messagebox.showinfo("오늘 검색 목록", "오늘 검색한 종목이 없습니다.")
            return
        msg = "\n".join(f"• [{i['stock_code']}] {i['stock_name']}" for i in items)
        messagebox.showinfo(f"오늘 검색 목록 ({len(items)}건)", msg)

    # ─── 텀싯 다운로드 ───

    def run_download(self):
        lines = [l for l in self.input_txt.get("1.0", END).splitlines() if l.strip()]
        if not lines:
            messagebox.showwarning("입력 없음", "종목을 입력하세요.")
            return
        threading.Thread(target=self._download_worker, args=(lines,), daemon=True).start()

    def _download_worker(self, lines):
        self.log(f"=== 텀싯 다운로드 시작 ({len(lines)}건) ===")
        completed = []   # 다운로드 성공 항목
        failed = []      # (stock_name, reason)
        today = dt.date.today()
        start = (today - dt.timedelta(days=SEARCH_DAYS)).strftime("%Y%m%d")
        end = today.strftime("%Y%m%d")
        state_path, state = get_state()

        for line in lines:
            parsed = parse_input_line(line)
            if not parsed:
                continue
            stock_code, stock_name = parsed
            self.log(f"→ [{stock_code}] {stock_name}")

            issuer, mapped = find_issuer(stock_name, self.issuers)
            if not issuer:
                self.log(f"   [못찾음] 회사명 추출 실패")
                failed.append((stock_name, "회사명 추출 실패"))
                continue

            product = extract_product_type(stock_name)
            sub = (product == "SUB")
            rfull, rbase = extract_round(stock_name)
            tag = "" if mapped else " (자동추출)"
            self.log(f"   발행사={issuer}{tag}, 회차={rfull or '미상'}, 유형={product or '미상'}")

            try:
                pairs = self.dart.search(issuer, start, end, report_name="")
            except Exception as e:
                self.log(f"   [오류] {e}")
                failed.append((stock_name, str(e)))
                continue
            time.sleep(SLEEP)
            self.log(f"   검색 결과 {len(pairs)}건")

            rcp, title, fb = match_termsheet(pairs, rfull, rbase, product)
            pdf = None  # 본문 fallback에서 재사용 가능

            if not rcp:
                cands = termsheet_candidates(pairs, product)[:15]

                # ── 1차: 인덱스 HTML만 조회해서 문서타이틀에서 회차 매칭 (PDF 다운로드 없음)
                hit_by_index = None  # (c_rcp, c_title, dcm)
                if cands:
                    self.log(f"   타이틀 매칭 실패 → 인덱스 조회 ({len(cands)}건 스캔)")
                for c_rcp, c_title, _pri in cands:
                    try:
                        dcm, titles = self.dart.get_doc_info(c_rcp)
                        time.sleep(SLEEP)
                    except Exception:
                        continue
                    if any(round_in(t, rfull, rbase) for t in titles):
                        hit_by_index = (c_rcp, c_title, dcm)
                        self.log(f"   인덱스 매칭: {c_title} (rcp={c_rcp})")
                        break

                if hit_by_index:
                    rcp, title, saved_dcm = hit_by_index
                    try:
                        pdf = self.dart.download_pdf(rcp, saved_dcm)
                        time.sleep(SLEEP)
                    except Exception as e:
                        self.log(f"   [오류] PDF 다운 실패: {e}")
                        failed.append((stock_name, str(e)))
                        continue
                else:
                    # ── 2차: PDF 본문 1~5페이지 확인 (최후수단)
                    self.log(f"   인덱스 매칭 실패 → PDF 본문 스캔")
                    for c_rcp, c_title, _pri in cands:
                        try:
                            dcm = self.dart.get_dcm_no(c_rcp)
                            time.sleep(SLEEP)
                            if not dcm:
                                continue
                            cand_pdf = self.dart.download_pdf(c_rcp, dcm)
                            time.sleep(SLEEP)
                        except Exception:
                            continue
                        if not cand_pdf:
                            continue
                        body = pdf_front_text(cand_pdf, max_pages=5)
                        if round_in(body, rfull, rbase):
                            rcp, title, pdf = c_rcp, c_title, cand_pdf
                            self.log(f"   본문 매칭: {title} (rcp={rcp})")
                            break

                if not rcp:
                    reason = f"회차 {rfull} {product or ''} 보고서 없음"
                    self.log(f"   [못찾음] {reason}")
                    failed.append((stock_name, reason))
                    continue
            else:
                note = " (대체매칭)" if fb else ""
                self.log(f"   매칭{note}: {title} (rcp={rcp})")

            # PDF 다운로드 (본문 fallback이면 이미 받아둔 것 재사용)
            if pdf is None:
                try:
                    dcm = self.dart.get_dcm_no(rcp)
                    time.sleep(SLEEP)
                    if not dcm:
                        self.log(f"   [오류] dcm_no 없음")
                        failed.append((stock_name, "dcm_no 없음"))
                        continue
                    pdf = self.dart.download_pdf(rcp, dcm)
                    time.sleep(SLEEP)
                except Exception as e:
                    self.log(f"   [오류] {e}")
                    failed.append((stock_name, str(e)))
                    continue
            if not pdf:
                self.log(f"   [오류] PDF 응답 비정상")
                failed.append((stock_name, "PDF 응답 비정상"))
                continue

            fname = f"{stock_code}_{safe_filename(stock_name)}.pdf" \
                    if stock_code else f"{safe_filename(stock_name)}.pdf"
            out = DOWNLOADS / fname
            out.write_bytes(pdf)
            self.log(f"   저장: {out}")

            entry = {
                "stock_code": stock_code,
                "stock_name": stock_name,
                "issuer": issuer,
                "rcp_no": rcp,
                "title": title,
                "subordinated": sub,
                "file": str(out),
            }
            state["searched"].append(entry)
            save_json(state_path, state)
            completed.append(entry)

        self.log("=== 완료 ===")
        self.root.after(0, lambda: self._show_result_popup(completed, failed))

    # ─── 결과 팝업 ───

    def _show_result_popup(self, completed, failed):
        win = tk.Toplevel(self.root)
        win.title("다운로드 결과")
        win.configure(bg=BG)
        win.geometry("560x500")

        tk.Label(win, text="텀싯 다운로드 결과",
                 bg=BG, fg=ACCENT_DK, font=("맑은 고딕", 13, "bold")).pack(anchor="w", padx=16, pady=(14, 4))
        tk.Label(win, text=f"성공 {len(completed)}건 · 실패 {len(failed)}건",
                 bg=BG, fg=MUTED, font=("맑은 고딕", 9)).pack(anchor="w", padx=16)

        # 스크롤 가능 목록
        outer = tk.Frame(win, bg=BG)
        outer.pack(fill="both", expand=True, padx=16, pady=10)
        canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=1,
                           highlightbackground="#E0D8F2")
        sb = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=PANEL)
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # 성공 목록 (체크박스 포함)
        check_vars = []
        if completed:
            tk.Label(inner, text="✓ 다운로드 완료", bg=PANEL, fg=ACCENT_DK,
                     font=("맑은 고딕", 10, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
            for entry in completed:
                row = tk.Frame(inner, bg=PANEL)
                row.pack(fill="x", padx=10, pady=2)
                var = tk.BooleanVar(value=False)
                check_vars.append((var, entry))
                cb = tk.Checkbutton(row, variable=var, bg=PANEL, activebackground=PANEL)
                cb.pack(side="left")
                tk.Label(row, text=f"[{entry['stock_code']}] {entry['stock_name']}",
                         bg=PANEL, fg=TEXT, font=("맑은 고딕", 9),
                         anchor="w").pack(side="left", fill="x", expand=True)

        if failed:
            tk.Label(inner, text="✕ 실패", bg=PANEL, fg="#C06565",
                     font=("맑은 고딕", 10, "bold")).pack(anchor="w", padx=10, pady=(14, 4))
            for name, reason in failed:
                tk.Label(inner, text=f"• {name}  —  {reason}",
                         bg=PANEL, fg="#8B5A5A", font=("맑은 고딕", 9),
                         anchor="w").pack(anchor="w", padx=20, pady=1)

        # 하단 액션
        tk.Label(win, text="↑ 체크된 종목만 증권발행실적보고서 확인",
                 bg=BG, fg=MUTED, font=("맑은 고딕", 9)).pack(anchor="w", padx=16)
        footer = tk.Frame(win, bg=BG)
        footer.pack(fill="x", padx=16, pady=(6, 14))

        def do_check():
            selected = [e for v, e in check_vars if v.get()]
            if not selected:
                messagebox.showinfo("선택 없음", "발행실적을 확인할 종목을 체크하세요.", parent=win)
                return
            save_pdf = save_var.get()
            win.destroy()
            threading.Thread(target=self._check_worker,
                             args=(selected, save_pdf), daemon=True).start()

        save_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(footer, text="발행실적보고서 PDF도 저장",
                        variable=save_var).pack(side="left")
        ttk.Button(footer, text="닫기", style="Ghost.TButton",
                   command=win.destroy).pack(side="right")
        ttk.Button(footer, text="발행실적 확인 실행",
                   command=do_check).pack(side="right", padx=6)

    # ─── 발행취소 확인 ───

    def run_check(self):
        # 전체 버튼: 오늘 검색한 모든 종목 + 사용자에게 저장여부 묻기
        _, state = get_state()
        items = state.get("searched", [])
        if not items:
            self.log("오늘 검색한 종목이 없습니다.")
            return
        save = messagebox.askyesno("발행취소 확인",
                                    f"오늘 검색한 {len(items)}건 전체를 확인합니다.\n"
                                    "발행실적보고서 PDF도 저장하시겠습니까?")
        threading.Thread(target=self._check_worker,
                         args=(items, save), daemon=True).start()

    def _check_worker(self, items=None, save_pdf=False):
        if items is None:
            _, state = get_state()
            items = state.get("searched", [])
        if not items:
            self.log("오늘 검색한 종목이 없습니다.")
            return
        self.log(f"=== 발행취소 확인 ({len(items)}건) ===")
        today = dt.date.today()
        start = (today - dt.timedelta(days=30)).strftime("%Y%m%d")
        end = today.strftime("%Y%m%d")

        results = []
        # 회사별로 검색 결과 캐시
        cache = {}
        for item in items:
            name = item["stock_name"]
            issuer = item["issuer"]
            self.log(f"→ {name}")

            if issuer not in cache:
                try:
                    cache[issuer] = self.dart.search(issuer, start, end)
                except Exception as e:
                    self.log(f"   [오류] {e}")
                    cache[issuer] = []
                time.sleep(SLEEP)

            rfull, rbase = extract_round(name)
            rcp, title = match_result(cache[issuer], rfull, rbase)
            if not rcp:
                self.log(f"   증권발행실적보고서 없음 → 알 수 없음")
                results.append((name, "unknown", "알 수 없음", "발행실적보고서 미게재"))
                continue

            try:
                dcm = self.dart.get_dcm_no(rcp)
                time.sleep(SLEEP)
                if not dcm:
                    raise RuntimeError("dcm_no 없음")
                pdf = self.dart.download_pdf(rcp, dcm)
                time.sleep(SLEEP)
            except Exception as e:
                self.log(f"   [오류] {e}")
                results.append((name, "unknown", "알 수 없음", str(e)))
                continue
            if not pdf:
                results.append((name, "unknown", "알 수 없음", "PDF 응답 비정상"))
                continue

            status, label, reason = analyze_result_pdf(pdf)
            self.log(f"   {label} ({reason})")

            if save_pdf:
                fname = f"{item['stock_code']}_{safe_filename(name)}_발행실적.pdf"
                (DOWNLOADS / fname).write_bytes(pdf)
                self.log(f"   보고서 저장: {DOWNLOADS / fname}")

            results.append((name, status, label, reason))

        cancelled = [r for r in results if r[1] == "cancelled"]
        issued = [r for r in results if r[1] == "issued"]
        unknown = [r for r in results if r[1] == "unknown"]
        msg = "━━ 결과 요약 ━━\n"
        msg += f"발행취소: {len(cancelled)}건\n"
        for n, _, l, r in cancelled:
            msg += f"  ✕ {n} — {r}\n"
        msg += f"\n알 수 없음: {len(unknown)}건\n"
        for n, _, l, r in unknown:
            msg += f"  ? {n} — {r}\n"
        msg += f"\n발행됨: {len(issued)}건\n"
        for n, _, l, r in issued:
            msg += f"  ✓ {n} — {r}\n"
        self.log(msg)
        messagebox.showinfo("발행 확인 결과", msg)


def main():
    root = Tk()
    App(root)
    root.mainloop()

if __name__ == "__main__":
    main()

from __future__ import annotations

import csv
import datetime as dt
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import tkinter as tk
from tkinter import END, Text, Tk, filedialog, messagebox, ttk

from dart_app import config, state
from dart_app.domain.security_name import extract_product_type, extract_round, find_issuer
from dart_app.integrations.dart_web import DART_BASE, Dart
from dart_app.services.record_workflow import RecordWorkflow, RecordWorkflowOptions
from dart_app.runtime import cache_stats, clear_cache
from dart_app.ui.dialogs import IssuerEditor, SettingsDialog
from dart_app.utils.files import stock_output_dir
from dart_app.domain.input_parser import parse_input_lines
from dart_app.utils.text import clean_text


class App:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("DART 텀싯 자동 처리")
        self.root.geometry("1420x920")
        self._main_thread_id = threading.get_ident()
        self._ui_queue: queue.Queue = queue.Queue()
        self._worker_running = threading.Event()
        self._stop_event = threading.Event()
        self._task_buttons = []
        self.record_rows: dict[str, str] = {}
        self.record_data: dict[str, dict] = {}
        self.detail_candidate_map: dict[str, dict] = {}
        self.issuers = state.load_issuers()

        settings = state.load_settings()
        self.apply_runtime_settings(settings)
        self.save_root_var = tk.StringVar(value=str(state.normalize_save_root(settings.get("save_root"))))
        self.opendart_key_var = tk.StringVar(value=settings.get("opendart_api_key", state.discover_opendart_api_key()))
        self.auto_result_var = tk.BooleanVar(value=bool(settings.get("auto_result", True)))
        self.force_refresh_var = tk.BooleanVar(value=bool(settings.get("force_refresh", False)))
        self.save_termsheet_pdf_var = tk.BooleanVar(value=bool(settings.get("save_termsheet_pdf", True)))
        self.save_result_pdf_var = tk.BooleanVar(value=bool(settings.get("save_result_pdf", True)))
        self.use_opendart_var = tk.BooleanVar(value=bool(settings.get("use_opendart", True)))
        self.status = tk.StringVar()
        self.cache_info_var = tk.StringVar()
        self.summary_var = tk.StringVar()
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_text_var = tk.StringVar(value="대기")
        self.profile_var = tk.StringVar(value="균형 모드")
        self._use_opendart_value = bool(self.use_opendart_var.get())
        self._opendart_api_key_value = state.normalize_api_key(self.opendart_key_var.get())
        self._auto_result_value = bool(self.auto_result_var.get())
        self._progress_total = 0
        self._progress_done = 0
        self._progress_failed = 0

        self._build_ui()
        self._update_save_status()
        self._update_summary()
        self.refresh_cache_info()
        self.root.after(80, self._drain_ui_queue)

    def apply_runtime_settings(self, settings):
        runtime = state.normalize_runtime_settings(settings)
        config.SEARCH_DAYS = runtime["search_days"]
        config.RESULT_SEARCH_DAYS = runtime["result_search_days"]
        config.INDEX_SCAN_LIMIT = runtime["index_scan_limit"]
        config.PDF_SCAN_LIMIT = runtime["pdf_scan_limit"]
        config.RESULT_SCAN_LIMIT = runtime["result_scan_limit"]
        config.REQUEST_RETRIES = runtime["request_retries"]
        config.RETRY_BACKOFF = runtime["retry_backoff"]
        config.DOWNLOAD_WORKERS = runtime["download_workers"]
        config.HTTP_MIN_INTERVAL = runtime["http_min_interval"]
        config.CIRCUIT_FAIL_LIMIT = runtime["circuit_fail_limit"]
        config.CIRCUIT_COOLDOWN = runtime["circuit_cooldown"]
        config.SEARCH_CACHE_SECONDS = int(runtime["search_cache_hours"] * 3600)
        import dart_app.domain.document_matching as document_matching

        document_matching.INDEX_SCAN_LIMIT = config.INDEX_SCAN_LIMIT
        document_matching.PDF_SCAN_LIMIT = config.PDF_SCAN_LIMIT
        document_matching.RESULT_SCAN_LIMIT = config.RESULT_SCAN_LIMIT
        return runtime

    def _build_ui(self):
        self.root.configure(bg=config.BG)
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=26)

        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")
        ttk.Label(top, text="DART 텀싯/발행실적 자동 처리", font=("Malgun Gothic", 16, "bold")).pack(side="left")
        ttk.Label(top, textvariable=self.status, foreground=config.MUTED).pack(side="right")
        ttk.Label(top, textvariable=self.summary_var, foreground=config.ACCENT_DK).pack(side="right", padx=16)

        save_bar = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        save_bar.pack(fill="x")
        ttk.Label(save_bar, text="저장 폴더").pack(side="left")
        ttk.Entry(save_bar, textvariable=self.save_root_var).pack(side="left", fill="x", expand=True, padx=6)
        ttk.Button(save_bar, text="찾기", command=self.choose_save_root).pack(side="left")
        ttk.Button(save_bar, text="저장", command=self.save_root_setting).pack(side="left", padx=4)
        ttk.Checkbutton(save_bar, text="발행실적 자동 확인", variable=self.auto_result_var).pack(side="left", padx=12)
        ttk.Checkbutton(save_bar, text="캐시 무시", variable=self.force_refresh_var).pack(side="left")

        control_bar = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        control_bar.pack(fill="x")
        ttk.Label(control_bar, text="모드").pack(side="left")
        self.profile_combo = ttk.Combobox(
            control_bar,
            textvariable=self.profile_var,
            values=list(config.RUNTIME_PRESETS.keys()),
            state="readonly",
            width=12,
        )
        self.profile_combo.pack(side="left", padx=6)
        ttk.Button(control_bar, text="모드 적용", command=self.apply_selected_profile).pack(side="left", padx=(0, 12))
        ttk.Checkbutton(control_bar, text="텀싯 PDF 저장", variable=self.save_termsheet_pdf_var).pack(side="left")
        ttk.Checkbutton(control_bar, text="발행실적 PDF 저장", variable=self.save_result_pdf_var).pack(side="left", padx=12)
        ttk.Checkbutton(control_bar, text="OpenDART 사용", variable=self.use_opendart_var).pack(side="left")
        ttk.Button(control_bar, text="현재 옵션 저장", command=self.save_root_setting).pack(side="right")

        progress_bar = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        progress_bar.pack(fill="x")
        ttk.Progressbar(progress_bar, variable=self.progress_var, maximum=100).pack(side="left", fill="x", expand=True)
        ttk.Label(progress_bar, textvariable=self.progress_text_var, width=34, anchor="e").pack(side="left", padx=(8, 0))

        main = ttk.PanedWindow(self.root, orient="horizontal")
        main.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        left = ttk.Frame(main, padding=8)
        main.add(left, weight=1)
        right = ttk.Frame(main, padding=8)
        main.add(right, weight=3)

        ttk.Label(left, text="입력").pack(anchor="w")
        self.input_txt = Text(left, height=16, bg=config.INPUT_BG, fg=config.TEXT, wrap="none", undo=True)
        self.input_txt.pack(fill="both", expand=False, pady=(4, 8))

        left_buttons = ttk.Frame(left)
        left_buttons.pack(fill="x", pady=4)
        for text, command in (
            ("미리보기", self.preview_records),
            ("정규화", lambda: self._normalize_input_text(self._target_or_preview_records())),
            ("전체 대상", lambda: self.set_all_targets(True)),
            ("대상 해제", lambda: self.set_all_targets(False)),
            ("실패 대상", self.select_failed),
            ("검토 대상", self.select_review),
            ("완료 제외", self.select_not_done),
        ):
            ttk.Button(left_buttons, text=text, command=command).pack(side="left", padx=(0, 4), pady=2)

        run_buttons = ttk.LabelFrame(left, text="실행")
        run_buttons.pack(fill="x", pady=8)
        self._add_task_button(run_buttons, "대상 다운로드", self.run_download)
        self._add_task_button(run_buttons, "대상 확인", self.run_check)
        self._add_task_button(run_buttons, "대상 발행실적 갱신", self.run_result_refresh)
        self._add_task_button(run_buttons, "실패 재시도", self.retry_failed)
        self._add_task_button(run_buttons, "검토필요 재시도", self.retry_review)
        self._add_task_button(run_buttons, "중지", self.stop_worker)

        tools = ttk.LabelFrame(left, text="도구")
        tools.pack(fill="x", pady=8)
        ttk.Button(tools, text="DART 상태", command=self.run_status_check).pack(fill="x", pady=2)
        ttk.Button(tools, text="설정", command=self.edit_settings).pack(fill="x", pady=2)
        ttk.Button(tools, text="발행사 매핑", command=self.edit_issuers).pack(fill="x", pady=2)
        ttk.Button(tools, text="오늘 작업", command=self.show_today).pack(fill="x", pady=2)

        ttk.Label(left, text="로그").pack(anchor="w", pady=(8, 0))
        self.log_txt = Text(left, height=12, bg=config.LOG_BG, fg=config.TEXT, wrap="word")
        self.log_txt.pack(fill="both", expand=True)

        cols = ("check", "code", "name", "issuer", "round", "product", "status", "termsheet", "result", "folder")
        self.records_tree = ttk.Treeview(right, columns=cols, show="headings", selectmode="browse")
        headings = {
            "check": "대상",
            "code": "종목코드",
            "name": "종목명",
            "issuer": "발행사",
            "round": "회차",
            "product": "유형",
            "status": "처리현황",
            "termsheet": "텀싯",
            "result": "발행실적",
            "folder": "저장 폴더",
        }
        widths = {"check": 54, "code": 126, "name": 230, "issuer": 120, "round": 70, "product": 64, "status": 120, "termsheet": 160, "result": 160, "folder": 240}
        for col in cols:
            self.records_tree.heading(col, text=headings[col])
            self.records_tree.column(col, width=widths[col], anchor="center" if col in ("check", "round", "product") else "w")
        self.records_tree.pack(fill="both", expand=True)
        self.records_tree.bind("<<TreeviewSelect>>", self._on_record_select)
        self.records_tree.bind("<Button-1>", self._on_record_click)
        self.records_tree.bind("<Double-1>", self._on_record_double_click)
        self.records_tree.tag_configure("done", background="#ECF8EF")
        self.records_tree.tag_configure("running", background="#EEF4FF")
        self.records_tree.tag_configure("review", background="#FFF7E6")
        self.records_tree.tag_configure("failed", background="#FDECEC")

        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True, pady=(8, 0))
        self.verify_tab = ttk.Frame(notebook, padding=8)
        self.result_tab = ttk.Frame(notebook, padding=8)
        self.cache_tab = ttk.Frame(notebook, padding=8)
        notebook.add(self.verify_tab, text="탐지 근거")
        notebook.add(self.result_tab, text="발행실적")
        notebook.add(self.cache_tab, text="캐시/내보내기")
        self._build_verify_tab()
        self._build_result_tab()
        self._build_cache_tab()

    def _add_task_button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        button.pack(fill="x", pady=2)
        if text != "중지":
            self._task_buttons.append(button)
        return button

    def _build_verify_tab(self):
        cols = ("grade", "source", "score", "title", "reason", "evidence")
        self.detail_candidate_tree = ttk.Treeview(self.verify_tab, columns=cols, show="headings", height=8)
        for col, width in (("grade", 80), ("source", 80), ("score", 64), ("title", 300), ("reason", 220), ("evidence", 420)):
            self.detail_candidate_tree.heading(col, text=col)
            self.detail_candidate_tree.column(col, width=width)
        self.detail_candidate_tree.pack(fill="both", expand=True)
        self.detail_candidate_tree.bind("<Double-1>", lambda _e: self.open_selected_candidate_from_detail())
        ttk.Button(self.verify_tab, text="현재 후보 DART 열기", command=self.open_selected_candidate_from_detail).pack(anchor="e", pady=6)

    def _build_result_tab(self):
        self.result_txt = Text(self.result_tab, height=10, bg=config.INPUT_BG, fg=config.TEXT, wrap="word")
        self.result_txt.pack(fill="both", expand=True)
        buttons = ttk.Frame(self.result_tab)
        buttons.pack(fill="x", pady=6)
        ttk.Button(buttons, text="PDF 열기", command=self.open_selected_pdf).pack(side="left")
        ttk.Button(buttons, text="폴더 열기", command=self.open_selected_folder).pack(side="left", padx=6)
        ttk.Button(buttons, text="CSV 내보내기", command=self.export_results_csv).pack(side="right")

    def _build_cache_tab(self):
        ttk.Label(self.cache_tab, textvariable=self.cache_info_var).pack(anchor="w", pady=4)
        buttons = ttk.Frame(self.cache_tab)
        buttons.pack(anchor="w", pady=6)
        ttk.Button(buttons, text="새로고침", command=self.refresh_cache_info).pack(side="left")
        ttk.Button(buttons, text="검색 캐시 삭제", command=lambda: self.clear_cache_ui("search")).pack(side="left", padx=6)
        ttk.Button(buttons, text="PDF 캐시 삭제", command=lambda: self.clear_cache_ui("pdf")).pack(side="left")
        ttk.Button(buttons, text="전체 캐시 삭제", command=lambda: self.clear_cache_ui("all")).pack(side="left", padx=6)

    def current_save_root(self):
        return state.normalize_save_root(self.save_root_var.get())

    def apply_selected_profile(self):
        name = self.profile_var.get()
        settings = state.normalize_runtime_settings(config.RUNTIME_PRESETS.get(name, config.DEFAULT_RUNTIME_SETTINGS))
        self.apply_runtime_settings(settings)
        self.auto_result_var.set(bool(settings.get("auto_result", True)))
        self.force_refresh_var.set(bool(settings.get("force_refresh", False)))
        self.save_termsheet_pdf_var.set(bool(settings.get("save_termsheet_pdf", True)))
        self.save_result_pdf_var.set(bool(settings.get("save_result_pdf", True)))
        self.use_opendart_var.set(bool(settings.get("use_opendart", True)))
        self._sync_worker_options()
        self._update_save_status()
        self.log(f"실행 모드 적용: {name}")

    def _sync_worker_options(self):
        self._use_opendart_value = bool(self.use_opendart_var.get())
        self._opendart_api_key_value = state.normalize_api_key(self.opendart_key_var.get())
        self._auto_result_value = bool(self.auto_result_var.get())

    def _update_save_status(self):
        key_state = "OpenDART 사용" if self.use_opendart_var.get() and state.normalize_api_key(self.opendart_key_var.get()) else "OpenDART 미사용"
        self.status.set(f"{key_state} | 저장: {self.current_save_root()}")

    def _update_summary(self):
        rows = list(self.record_data.values())
        total = len(rows)
        target_count = sum(1 for row in rows if self._is_target(row))
        done = sum(1 for row in rows if row.get("status") == "완료")
        failed = sum(1 for row in rows if any(token in str(row.get("status", "")) for token in ("실패", "미발견")))
        review = sum(1 for row in rows if "검토" in str(row.get("status", "")) or "검토" in str(row.get("termsheet_status", "")) or "검토" in str(row.get("result_status", "")))
        self.summary_var.set(f"전체 {total} | 대상 {target_count} | 완료 {done} | 검토 {review} | 실패 {failed}")

    def _tag_for_data(self, data):
        status = str(data.get("status", ""))
        termsheet = str(data.get("termsheet_status", ""))
        result = str(data.get("result_status", ""))
        if "실패" in status or "미발견" in status:
            return "failed"
        if "검토" in status or "검토" in termsheet or "검토" in result:
            return "review"
        if status == "완료":
            return "done"
        if any(token in status for token in ("검색", "확인", "저장", "갱신")):
            return "running"
        return ""

    def _reset_progress(self, total, label):
        self._progress_total = max(0, int(total or 0))
        self._progress_done = 0
        self._progress_failed = 0
        self.progress_var.set(0)
        self.progress_text_var.set(f"{label}: 0/{self._progress_total}")

    def _advance_progress(self, ok):
        self._progress_done += 1
        if not ok:
            self._progress_failed += 1
        pct = 0 if not self._progress_total else self._progress_done / self._progress_total * 100
        self.progress_var.set(pct)
        self.progress_text_var.set(
            f"진행 {self._progress_done}/{self._progress_total} | 실패 {self._progress_failed}"
        )

    def choose_save_root(self):
        initial = str(self.current_save_root() if self.current_save_root().exists() else Path.home())
        selected = filedialog.askdirectory(parent=self.root, initialdir=initial)
        if selected:
            self.save_root_var.set(selected)
            self.save_root_setting(show_message=False)

    def save_root_setting(self, show_message=True):
        try:
            root = self.current_save_root()
            root.mkdir(parents=True, exist_ok=True)
            settings = state.load_settings()
            settings.update({
                "save_root": str(root),
                "opendart_api_key": state.normalize_api_key(self.opendart_key_var.get()),
                "auto_result": self.auto_result_var.get(),
                "force_refresh": self.force_refresh_var.get(),
                "save_termsheet_pdf": self.save_termsheet_pdf_var.get(),
                "save_result_pdf": self.save_result_pdf_var.get(),
                "use_opendart": self.use_opendart_var.get(),
            })
            state.save_settings(settings)
            self._sync_worker_options()
            self._update_save_status()
            if show_message:
                messagebox.showinfo("저장 완료", "설정을 저장했습니다.", parent=self.root)
        except Exception as exc:
            messagebox.showerror("저장 실패", str(exc), parent=self.root)

    def _run_on_ui_thread(self, func, *args, **kwargs):
        if threading.get_ident() == self._main_thread_id:
            return func(*args, **kwargs)
        self._ui_queue.put((func, args, kwargs))
        return None

    def _drain_ui_queue(self):
        try:
            while True:
                func, args, kwargs = self._ui_queue.get_nowait()
                func(*args, **kwargs)
        except queue.Empty:
            pass
        try:
            self.root.after(80, self._drain_ui_queue)
        except tk.TclError:
            pass

    def _log(self, msg):
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        self.log_txt.insert(END, f"[{stamp}] {msg}\n")
        self.log_txt.see(END)
        self.root.update_idletasks()

    def log(self, msg):
        self._run_on_ui_thread(self._log, msg)

    def _short_text(self, value, limit=80):
        if isinstance(value, (list, tuple)):
            value = ", ".join(str(item) for item in value)
        value = clean_text(str(value or ""))
        return value if len(value) <= limit else value[: limit - 1] + "…"

    def _record_key(self, stock_code, stock_name):
        return f"{str(stock_code or '').strip().upper()}|{str(stock_name or '').strip()}"

    def _is_target(self, data):
        return bool(data.get("target", data.get("checked", True)))

    def _record_display_values(self, data):
        return (
            "☑" if self._is_target(data) else "☐",
            data.get("stock_code", ""),
            data.get("stock_name", ""),
            data.get("issuer", ""),
            data.get("round_full", ""),
            data.get("product", ""),
            data.get("status", "대기"),
            self._short_text(data.get("termsheet_status", ""), 36),
            self._short_text(data.get("result_status", ""), 36),
            self._short_text(data.get("folder", ""), 48),
        )

    def _target_or_preview_records(self):
        if self.record_data:
            records = self._target_records()
            if not records:
                messagebox.showinfo("대상 필요", "대상으로 지정된 종목이 없습니다.", parent=self.root)
            return records
        return self.preview_records()

    def preview_records(self):
        raw = self.input_txt.get("1.0", END).splitlines()
        records = parse_input_lines(raw)
        self._set_record_rows(records)
        self._normalize_input_text(records)
        return records

    def _format_input_records(self, records):
        lines = []
        for code, name in records:
            if code:
                lines.append(code)
            lines.append(name)
        return "\n".join(lines)

    def _normalize_input_text(self, records):
        if records is None:
            return
        text = self._format_input_records(records)
        self.input_txt.delete("1.0", END)
        self.input_txt.insert("1.0", text)

    def _set_record_rows(self, records):
        return self._run_on_ui_thread(self._set_record_rows_ui, records)

    def _set_record_rows_ui(self, records):
        self.records_tree.delete(*self.records_tree.get_children())
        self.record_rows.clear()
        self.record_data.clear()
        for code, name in records:
            issuer, mapped = find_issuer(name, self.issuers)
            round_full, round_base = extract_round(name)
            product = extract_product_type(name) or ""
            key = self._record_key(code, name)
            data = {
                "target": True,
                "stock_code": code,
                "stock_name": name,
                "issuer": issuer or "",
                "issuer_mapped": mapped,
                "round_full": round_full or "",
                "round_base": round_base or "",
                "product": product,
                "status": "대기",
                "termsheet_status": "",
                "result_status": "",
                "folder": str(stock_output_dir(self.current_save_root(), code)),
            }
            iid = str(len(self.record_rows))
            self.record_rows[key] = iid
            self.record_data[key] = data
            self.records_tree.insert("", "end", iid=iid, values=self._record_display_values(data), tags=(self._tag_for_data(data),))
        if records:
            self.records_tree.selection_set("0")
        self._refresh_detail_tabs()
        self._update_summary()

    def _ensure_record_row_ui(self, stock_code, stock_name):
        key = self._record_key(stock_code, stock_name)
        iid = self.record_rows.get(key)
        if iid and self.records_tree.exists(iid):
            return key, iid
        data = {
            "target": True,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "status": "대기",
            "folder": str(stock_output_dir(self.current_save_root(), stock_code)),
        }
        iid = str(len(self.record_rows))
        self.record_rows[key] = iid
        self.record_data[key] = data
        self.records_tree.insert("", "end", iid=iid, values=self._record_display_values(data), tags=(self._tag_for_data(data),))
        self._update_summary()
        return key, iid

    def update_record(self, stock_code, stock_name, **updates):
        self._run_on_ui_thread(self._update_record_ui, stock_code, stock_name, updates)

    def _update_record_ui(self, stock_code, stock_name, updates):
        key, iid = self._ensure_record_row_ui(stock_code, stock_name)
        data = self.record_data.setdefault(key, {})
        data.update(updates)
        if data.get("file") and not data.get("folder"):
            data["folder"] = str(Path(data["file"]).parent)
        self.records_tree.item(iid, values=self._record_display_values(data), tags=(self._tag_for_data(data),))
        if iid in self.records_tree.selection():
            self._refresh_detail_tabs(data)
        self._update_summary()

    def _selected_record_key_iid(self):
        selected = self.records_tree.selection()
        if not selected:
            return None, None
        iid = selected[0]
        for key, row_iid in self.record_rows.items():
            if row_iid == iid:
                return key, iid
        return None, None

    def _selected_record_silent(self):
        key, _iid = self._selected_record_key_iid()
        if not key:
            return None
        return self.record_data.get(key)

    def _selected_record(self):
        data = self._selected_record_silent()
        if not data:
            messagebox.showinfo("대상 필요", "상세를 볼 종목을 클릭하세요.", parent=self.root)
        return data

    def _candidate_rows_for_record(self, data):
        rows = []
        rows.extend(data.get("candidates") or [])
        rows.extend(data.get("result_candidates") or [])
        return rows

    def _refresh_detail_tabs(self, data=None):
        data = data or self._selected_record_silent()
        self.detail_candidate_tree.delete(*self.detail_candidate_tree.get_children())
        self.detail_candidate_map.clear()
        self.result_txt.delete("1.0", END)
        if not data:
            return
        for idx, cand in enumerate(self._candidate_rows_for_record(data)):
            iid = str(idx)
            self.detail_candidate_map[iid] = cand
            self.detail_candidate_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    cand.get("grade", ""),
                    cand.get("source", ""),
                    cand.get("score", ""),
                    self._short_text(cand.get("title", ""), 60),
                    self._short_text(cand.get("reject_reason", ""), 45),
                    self._short_text(cand.get("evidence", ""), 80),
                ),
            )
        lines = [
            f"종목: {data.get('stock_code', '')} {data.get('stock_name', '')}",
            f"공식 문서명: {data.get('official_title', '')}",
            f"텀싯: {data.get('termsheet_status', '')}",
            f"발행실적: {data.get('result_status', '')}",
            f"발행실적 판단: {data.get('result_label', '')} / {data.get('result_confidence', '')}",
            f"판단 사유: {data.get('result_reason', '')}",
            f"저장 폴더: {data.get('folder', '')}",
            f"텀싯 PDF: {data.get('file', '')}",
            f"발행실적 PDF: {data.get('result_file', '')}",
        ]
        evidence = data.get("result_evidence") or []
        if evidence:
            lines.append("")
            lines.append("근거:")
            lines.extend(f"- {item}" for item in evidence[:10])
        self.result_txt.insert("1.0", "\n".join(lines))

    def _on_record_select(self, _event=None):
        key, iid = self._selected_record_key_iid()
        data = self.record_data.get(key) if key else None
        if data:
            self._set_record_target_ui(iid, True)
        self._refresh_detail_tabs(data)

    def _on_record_click(self, event):
        col = self.records_tree.identify_column(event.x)
        iid = self.records_tree.identify_row(event.y)
        if col != "#1":
            if iid:
                self._set_record_target_ui(iid, True)
            return
        if iid:
            self._toggle_record_target_ui(iid)
            return "break"
        return None

    def _on_record_double_click(self, event):
        col = self.records_tree.identify_column(event.x)
        if col in ("#10", "#8", "#9"):
            self.open_selected_folder() if col == "#10" else self.open_selected_pdf()

    def _record_data_for_iid(self, iid):
        key = next((key for key, row_iid in self.record_rows.items() if row_iid == iid), None)
        if not key:
            return None
        return self.record_data.get(key)

    def _set_record_target_ui(self, iid, target):
        data = self._record_data_for_iid(iid)
        if not data:
            return
        if self._is_target(data) == bool(target):
            return
        data["target"] = bool(target)
        data.pop("checked", None)
        self.records_tree.item(iid, values=self._record_display_values(data), tags=(self._tag_for_data(data),))
        self._update_summary()

    def _toggle_record_target_ui(self, iid):
        data = self._record_data_for_iid(iid)
        if not data:
            return
        self._set_record_target_ui(iid, not self._is_target(data))

    def set_all_targets(self, target):
        for key, data in self.record_data.items():
            data["target"] = bool(target)
            data.pop("checked", None)
            iid = self.record_rows.get(key)
            if iid:
                self.records_tree.item(iid, values=self._record_display_values(data))
        self._update_summary()

    def _select_by_predicate(self, predicate):
        for key, data in self.record_data.items():
            data["target"] = bool(predicate(data))
            data.pop("checked", None)
            iid = self.record_rows.get(key)
            if iid:
                self.records_tree.item(iid, values=self._record_display_values(data), tags=(self._tag_for_data(data),))
        self._update_summary()

    def select_failed(self):
        self._select_by_predicate(
            lambda data: "실패" in str(data.get("status", "")) or "미발견" in str(data.get("status", ""))
        )

    def select_review(self):
        self._select_by_predicate(
            lambda data: "검토" in str(data.get("status", ""))
            or "검토" in str(data.get("termsheet_status", ""))
            or "검토" in str(data.get("result_status", ""))
        )

    def select_not_done(self):
        self._select_by_predicate(lambda data: data.get("status") != "완료")

    def _target_records(self):
        return [
            (data.get("stock_code", ""), data.get("stock_name", ""))
            for data in self.record_data.values()
            if self._is_target(data)
        ]

    def _records_matching(self, predicate):
        return [
            (data.get("stock_code", ""), data.get("stock_name", ""))
            for data in self.record_data.values()
            if predicate(data)
        ]

    def _set_worker_running(self, running):
        if running:
            self._worker_running.set()
            self._stop_event.clear()
        else:
            self._worker_running.clear()
        for button in self._task_buttons:
            button.configure(state="disabled" if running else "normal")

    def _start_worker(self, label, target, *args):
        if self._worker_running.is_set():
            messagebox.showinfo("실행 중", "이미 작업이 실행 중입니다.", parent=self.root)
            return
        self._sync_worker_options()
        self._set_worker_running(True)
        self.log(f"{label} 시작")

        def runner():
            try:
                target(*args)
            except Exception as exc:
                self.log(f"{label} 실패: {exc}")
            finally:
                self._run_on_ui_thread(self._set_worker_running, False)
                self.log(f"{label} 종료")

        threading.Thread(target=runner, daemon=True).start()

    def _start_download_records(self, records, reset_rows=True, label="텀싯 다운로드"):
        if reset_rows:
            self._set_record_rows(records)
        self._start_worker(
            label,
            self._download_worker,
            records,
            self.current_save_root(),
            self.save_termsheet_pdf_var.get(),
            self.save_result_pdf_var.get(),
            self.auto_result_var.get(),
            self.force_refresh_var.get(),
        )

    def run_download(self):
        records = self._target_or_preview_records()
        if records:
            self._start_download_records(records, reset_rows=False, label="대상 다운로드")

    def run_check(self):
        records = self._target_or_preview_records()
        if records:
            self._start_worker("대상 확인", self._check_worker, records, False, False, self.current_save_root(), self.force_refresh_var.get())

    def run_current_check(self):
        data = self._selected_record()
        if data:
            record = [(data.get("stock_code", ""), data.get("stock_name", ""))]
            self._start_worker("현재 종목 확인", self._check_worker, record, False, False, self.current_save_root(), self.force_refresh_var.get())

    def run_result_refresh(self):
        records = self._target_or_preview_records()
        if records:
            self._start_worker(
                "대상 발행실적 갱신",
                self._result_worker,
                records,
                self.current_save_root(),
                self.save_result_pdf_var.get(),
                self.force_refresh_var.get(),
            )

    def run_current_result_refresh(self):
        data = self._selected_record()
        if data:
            record = [(data.get("stock_code", ""), data.get("stock_name", ""))]
            self._start_worker(
                "현재 종목 발행실적 갱신",
                self._result_worker,
                record,
                self.current_save_root(),
                self.save_result_pdf_var.get(),
                self.force_refresh_var.get(),
            )

    def retry_failed(self):
        records = self._records_matching(lambda data: "실패" in str(data.get("status", "")) or "미발견" in str(data.get("status", "")))
        if records:
            self._start_download_records(records, reset_rows=False, label="실패 재시도")

    def retry_review(self):
        records = self._records_matching(lambda data: "검토" in str(data.get("termsheet_status", "")) or "검토" in str(data.get("result_status", "")))
        if records:
            self._start_download_records(records, reset_rows=False, label="검토필요 재시도")

    def stop_worker(self):
        self._stop_event.set()
        self.log("중지 요청됨")

    def _make_client(self):
        if not self._use_opendart_value:
            return Dart("")
        return Dart(self._opendart_api_key_value or state.discover_opendart_api_key())

    def _make_workflow(self, save_root, save_termsheet_pdf, save_result_pdf, auto_result, force_refresh):
        options = RecordWorkflowOptions(
            save_root=save_root,
            search_days=config.SEARCH_DAYS,
            result_search_days=config.RESULT_SEARCH_DAYS,
            save_termsheet_pdf=save_termsheet_pdf,
            save_result_pdf=save_result_pdf,
            auto_result=auto_result,
            force_refresh=force_refresh,
        )
        return RecordWorkflow(
            self.issuers,
            self._make_client,
            options,
            self.update_record,
            should_stop=self._stop_event.is_set,
        )

    def _process_record(self, record, save_root, save_termsheet_pdf, save_result_pdf, auto_result, force_refresh):
        workflow = self._make_workflow(
            save_root,
            save_termsheet_pdf=save_termsheet_pdf,
            save_result_pdf=save_result_pdf,
            auto_result=auto_result,
            force_refresh=force_refresh,
        )
        return workflow.process_record(record)

    def _process_result_record(self, record, save_root, save_result_pdf, force_refresh):
        workflow = self._make_workflow(
            save_root,
            save_termsheet_pdf=False,
            save_result_pdf=save_result_pdf,
            auto_result=False,
            force_refresh=force_refresh,
        )
        return workflow.process_result_record(record)

    def _download_worker(self, records, save_root, save_termsheet_pdf=True, save_result_pdf=True, auto_result=False, force_refresh=False):
        self._run_records(
            records,
            save_root,
            save_termsheet_pdf=save_termsheet_pdf,
            save_result_pdf=save_result_pdf,
            auto_result=auto_result,
            force_refresh=force_refresh,
        )

    def _result_worker(self, records, save_root, save_result_pdf=True, force_refresh=False):
        records = list(records or [])
        if not records:
            self.log("처리할 종목이 없습니다.")
            return
        completed = 0
        failed = 0
        self._run_on_ui_thread(self._reset_progress, len(records), "발행실적")
        workers = max(1, int(config.DOWNLOAD_WORKERS))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self._process_result_record, record, save_root, save_result_pdf, force_refresh): record
                for record in records
            }
            for future in as_completed(futures):
                if self._stop_event.is_set():
                    break
                code, name = futures[future]
                try:
                    _code, _name, ok = future.result()
                    completed += 1 if ok else 0
                    failed += 0 if ok else 1
                    self._run_on_ui_thread(self._advance_progress, ok)
                    self.log(f"{code} {name}: 발행실적 {'갱신' if ok else '미발견'}")
                except Exception as exc:
                    failed += 1
                    self._run_on_ui_thread(self._advance_progress, False)
                    self.update_record(code, name, status="실패", result_status=str(exc))
                    self.log(f"{code} {name}: 발행실적 실패 - {exc}")
        self._run_on_ui_thread(self._show_result_popup, completed, failed)

    def _check_worker(self, items=None, save_termsheet_pdf=False, save_result_pdf=False, save_root=None, force_refresh=False, auto_result=None):
        self._run_records(
            items or self._target_records(),
            save_root or self.current_save_root(),
            save_termsheet_pdf=save_termsheet_pdf,
            save_result_pdf=save_result_pdf,
            auto_result=self._auto_result_value if auto_result is None else bool(auto_result),
            force_refresh=force_refresh,
        )

    def _run_records(self, records, save_root, save_termsheet_pdf, save_result_pdf, auto_result, force_refresh):
        completed = 0
        failed = 0
        records = list(records or [])
        if not records:
            self.log("처리할 종목이 없습니다.")
            return
        workers = max(1, int(config.DOWNLOAD_WORKERS))
        self._run_on_ui_thread(self._reset_progress, len(records), "처리")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self._process_record,
                    record,
                    save_root,
                    save_termsheet_pdf,
                    save_result_pdf,
                    auto_result,
                    force_refresh,
                ): record
                for record in records
            }
            for future in as_completed(futures):
                if self._stop_event.is_set():
                    break
                code, name = futures[future]
                try:
                    _code, _name, ok = future.result()
                    completed += 1 if ok else 0
                    failed += 0 if ok else 1
                    self._run_on_ui_thread(self._advance_progress, ok)
                    self.log(f"{code} {name}: {'완료' if ok else '미발견'}")
                except Exception as exc:
                    failed += 1
                    self._run_on_ui_thread(self._advance_progress, False)
                    self.update_record(code, name, status="실패", termsheet_status=str(exc))
                    self.log(f"{code} {name}: 실패 - {exc}")
        self._run_on_ui_thread(self._show_result_popup, completed, failed)

    def _show_result_popup(self, completed, failed):
        messagebox.showinfo("작업 완료", f"완료 {completed}건, 실패/미발견 {failed}건", parent=self.root)

    def run_status_check(self):
        self._start_worker("DART 상태 확인", self._status_worker)

    def _status_worker(self):
        status = self._make_client().check_status()
        self.log(f"DART 상태: {status['summary']}")
        for check in status["checks"]:
            self.log(f"- {check['name']}: {check['detail']}")

    def edit_issuers(self):
        IssuerEditor(self.root, self)

    def edit_settings(self):
        SettingsDialog(self.root, self)

    def refresh_cache_info(self):
        stats = cache_stats(config.CACHE_DIR)
        mb = stats["bytes"] / (1024 * 1024)
        self.cache_info_var.set(f"캐시 파일 {stats['files']}개 / {mb:.1f} MB / {config.CACHE_DIR}")

    def clear_cache_ui(self, kind):
        if not messagebox.askyesno("캐시 삭제", f"{kind} 캐시를 삭제할까요?", parent=self.root):
            return
        try:
            removed = clear_cache(config.CACHE_DIR, kind)
            self.refresh_cache_info()
            self.log(f"캐시 삭제: {removed}개")
        except Exception as exc:
            messagebox.showerror("삭제 실패", str(exc), parent=self.root)

    def _open_target(self, target, label):
        if not target:
            messagebox.showinfo("열 수 없음", f"{label} 경로가 없습니다.", parent=self.root)
            return
        target = str(target)
        try:
            if target.startswith("http://") or target.startswith("https://"):
                os.startfile(target)
            else:
                path = Path(target)
                if path.exists():
                    os.startfile(str(path))
                else:
                    messagebox.showinfo("경로 없음", target, parent=self.root)
        except Exception as exc:
            messagebox.showerror("열기 실패", str(exc), parent=self.root)

    def open_selected_pdf(self):
        data = self._selected_record()
        if data:
            self._open_target(data.get("file") or data.get("result_file"), "PDF")

    def open_selected_folder(self):
        data = self._selected_record()
        if data:
            self._open_target(data.get("folder"), "폴더")

    def open_selected_candidate_from_detail(self):
        selected = self.detail_candidate_tree.selection()
        if not selected:
            return
        cand = self.detail_candidate_map.get(selected[0]) or {}
        rcp_no = cand.get("rcp_no")
        self._open_target(f"{DART_BASE}/dsaf001/main.do?rcpNo={rcp_no}" if rcp_no else "", "DART")

    def show_selected_candidates(self):
        data = self._selected_record()
        if not data:
            return
        rows = self._candidate_rows_for_record(data)
        messagebox.showinfo("후보", "\n".join(str(row) for row in rows[:20]) or "후보 없음", parent=self.root)

    def export_results_csv(self):
        if not self.record_data:
            return
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        fields = ["stock_code", "stock_name", "issuer", "round_full", "product", "status", "termsheet_status", "result_status", "result_reason", "file", "result_file", "folder"]
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            writer.writeheader()
            for data in self.record_data.values():
                writer.writerow({field: data.get(field, "") for field in fields})
        self.log(f"CSV 저장: {path}")

    def show_today(self):
        state_path, data = state.get_state()
        self.log(f"오늘 상태 파일: {state_path}")
        records = data.get("searched") or []
        if records and isinstance(records[0], (list, tuple)):
            self._set_record_rows(records)


def main():
    root = Tk()
    App(root)
    root.mainloop()

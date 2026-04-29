from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from dart_app import config, state


class IssuerEditor:
    """발행사 매핑 편집 팝업."""

    def __init__(self, parent, app):
        self.app = app
        self.user_overrides = state.load_json(config.ISSUERS_PATH, {}) or {}
        self.win = tk.Toplevel(parent)
        self.win.title("발행사 매핑")
        self.win.configure(bg=config.BG)
        self.win.geometry("760x520")
        self.win.transient(parent)

        ttk.Label(self.win, text="발행사 매핑").pack(anchor="w", padx=14, pady=(12, 2))
        ttk.Label(
            self.win,
            text="종목명 앞부분을 DART 회사명으로 연결합니다. 기본값과 다른 사용자 항목만 저장됩니다.",
            foreground=config.MUTED,
        ).pack(anchor="w", padx=14, pady=(0, 10))

        body = ttk.Frame(self.win)
        body.pack(fill="both", expand=True, padx=14, pady=8)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(body, columns=("prefix", "company", "source"), show="headings", height=14)
        self.tree.heading("prefix", text="종목명 패턴")
        self.tree.heading("company", text="DART 회사명")
        self.tree.heading("source", text="구분")
        self.tree.column("prefix", width=220)
        self.tree.column("company", width=260)
        self.tree.column("source", width=80, anchor="center")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(body, command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self._on_select)

        form = ttk.Frame(self.win)
        form.pack(fill="x", padx=14, pady=8)
        self.prefix_var = tk.StringVar()
        self.company_var = tk.StringVar()
        ttk.Label(form, text="패턴").grid(row=0, column=0, sticky="w")
        ttk.Entry(form, textvariable=self.prefix_var, width=24).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(form, text="회사명").grid(row=0, column=2, sticky="w")
        ttk.Entry(form, textvariable=self.company_var, width=28).grid(row=0, column=3, sticky="ew", padx=6)
        form.columnconfigure(3, weight=1)

        buttons = ttk.Frame(self.win)
        buttons.pack(fill="x", padx=14, pady=(4, 14))
        ttk.Button(buttons, text="추가/수정", command=self._add).pack(side="left")
        ttk.Button(buttons, text="삭제", command=self._delete).pack(side="left", padx=6)
        ttk.Button(buttons, text="저장", command=self._save).pack(side="right")
        ttk.Button(buttons, text="닫기", command=self.win.destroy).pack(side="right", padx=6)

        self._refresh()

    def _current(self):
        merged = dict(config.DEFAULT_ISSUERS)
        for key, value in (self.user_overrides or {}).items():
            if key.startswith("_") or not isinstance(value, str):
                continue
            merged[key] = value
        return merged

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for prefix, company in sorted(self._current().items()):
            source = "사용자" if self.user_overrides.get(prefix) else "기본"
            self.tree.insert("", "end", values=(prefix, company, source))

    def _on_select(self, _ev):
        item = self.tree.focus()
        if not item:
            return
        prefix, company, _source = self.tree.item(item, "values")
        self.prefix_var.set(prefix)
        self.company_var.set(company)

    def _add(self):
        prefix = self.prefix_var.get().strip()
        company = self.company_var.get().strip()
        if not prefix or not company:
            messagebox.showwarning("입력 필요", "패턴과 회사명을 모두 입력하세요.", parent=self.win)
            return
        self.user_overrides[prefix] = company
        self._refresh()

    def _delete(self):
        prefix = self.prefix_var.get().strip()
        if not prefix:
            return
        if prefix in self.user_overrides:
            self.user_overrides.pop(prefix, None)
            self._refresh()
            self.prefix_var.set("")
            self.company_var.set("")
        elif prefix in config.DEFAULT_ISSUERS:
            messagebox.showinfo("기본 항목", "기본 매핑은 삭제할 수 없습니다. 같은 패턴을 다른 회사명으로 저장해 덮어쓸 수 있습니다.", parent=self.win)

    def _save(self):
        state.save_user_issuers(self.user_overrides)
        self.app.issuers = state.load_issuers()
        messagebox.showinfo("저장 완료", "발행사 매핑을 저장했습니다.", parent=self.win)
        self.win.destroy()


class SettingsDialog:
    """검색/매칭/네트워크 동작 설정."""

    FIELD_GROUPS = {
        "검색": (
            ("search_days", "텀싯 검색 기간(일)", "텀싯/투자설명서 검색 기간"),
            ("result_search_days", "발행실적 검색 기간(일)", "증권발행실적보고서 검색 기간"),
            ("index_scan_limit", "목차 탐색 개수", "검색 결과 중 목차까지 확인할 최대 개수"),
            ("pdf_scan_limit", "본문 탐색 개수", "PDF/뷰어 본문까지 확인할 최대 개수"),
            ("result_scan_limit", "발행실적 탐색 개수", "발행실적 후보 본문 탐색 범위"),
            ("result_body_scan_limit", "발행실적 본문 확인", "OpenDART 본문까지 확인할 발행실적 후보 개수"),
            ("result_front_text_scan_limit", "발행실적 PDF 확인", "PDF 앞부분까지 확인할 발행실적 후보 개수"),
        ),
        "속도/차단": (
            ("download_workers", "동시 작업 수", "발행사 그룹 병렬 처리 수"),
            ("search_cache_hours", "검색 캐시 시간", "검색 결과 캐시 유지 시간"),
            ("http_min_interval", "요청 간격(초)", "DART 요청 사이 최소 대기 시간"),
            ("request_retries", "재시도 횟수", "일시적 연결 오류 재시도 횟수"),
            ("retry_backoff", "재시도 대기(초)", "재시도마다 증가하는 대기 시간"),
        ),
        "캐시 보관": (
            ("cache_search_days", "검색 캐시 보관(일)", "디스크에 남은 검색 결과 캐시 보관 기간"),
            ("cache_document_days", "문서 캐시 보관(일)", "목차/뷰어/OpenDART 문서 캐시 보관 기간"),
            ("cache_pdf_days", "PDF 캐시 보관(일)", "내부 PDF 캐시 보관 기간"),
        ),
        "안전장치": (
            ("circuit_fail_limit", "차단 기준 실패 수", "연속 실패 시 잠시 우회/대기"),
            ("circuit_cooldown", "차단 유지(초)", "연속 실패 후 쉬는 시간"),
        ),
    }

    def __init__(self, parent, app):
        self.app = app
        self.settings = state.load_settings()
        self.vars: dict[str, tk.StringVar] = {}
        self.bool_vars: dict[str, tk.BooleanVar] = {}
        self.win = tk.Toplevel(parent)
        self.win.title("설정")
        self.win.configure(bg=config.BG)
        self.win.geometry("760x620")
        self.win.transient(parent)

        ttk.Label(self.win, text="설정").pack(anchor="w", padx=14, pady=(12, 2))
        ttk.Label(self.win, text="검색 범위, 병렬 처리, 캐시, 발행실적 처리 방식을 조정합니다.", foreground=config.MUTED).pack(
            anchor="w", padx=14, pady=(0, 10)
        )

        preset_bar = ttk.Frame(self.win)
        preset_bar.pack(fill="x", padx=14, pady=(0, 8))
        for name in config.RUNTIME_PRESETS:
            ttk.Button(preset_bar, text=name, command=lambda n=name: self._apply_preset(n)).pack(side="left", padx=(0, 6))
        ttk.Button(preset_bar, text="기본값", command=self._reset_defaults).pack(side="right")

        notebook = ttk.Notebook(self.win)
        notebook.pack(fill="both", expand=True, padx=14, pady=8)
        for tab_name, fields in self.FIELD_GROUPS.items():
            frame = ttk.Frame(notebook, padding=12)
            notebook.add(frame, text=tab_name)
            frame.columnconfigure(1, weight=1)
            for row, (key, label, desc) in enumerate(fields):
                self._add_number_field(frame, row, key, label, desc)

        api_frame = ttk.LabelFrame(self.win, text="OpenDART")
        api_frame.pack(fill="x", padx=14, pady=8)
        self.opendart_key_var = tk.StringVar(value=self.settings.get("opendart_api_key", ""))
        ttk.Entry(api_frame, textvariable=self.opendart_key_var, show="*", width=48).pack(side="left", fill="x", expand=True, padx=8, pady=8)

        options = ttk.Frame(self.win)
        options.pack(fill="x", padx=14, pady=4)
        self.auto_result_var = tk.BooleanVar(value=bool(self.settings.get("auto_result", True)))
        self.force_refresh_var = tk.BooleanVar(value=bool(self.settings.get("force_refresh", False)))
        self.save_termsheet_pdf_var = tk.BooleanVar(value=bool(self.settings.get("save_termsheet_pdf", True)))
        self.save_result_pdf_var = tk.BooleanVar(value=bool(self.settings.get("save_result_pdf", True)))
        self.use_opendart_var = tk.BooleanVar(value=bool(self.settings.get("use_opendart", True)))
        self.cache_auto_prune_var = tk.BooleanVar(value=bool(self.settings.get("cache_auto_prune", True)))
        self.bool_vars["auto_result"] = self.auto_result_var
        self.bool_vars["force_refresh"] = self.force_refresh_var
        self.bool_vars["save_termsheet_pdf"] = self.save_termsheet_pdf_var
        self.bool_vars["save_result_pdf"] = self.save_result_pdf_var
        self.bool_vars["use_opendart"] = self.use_opendart_var
        self.bool_vars["cache_auto_prune"] = self.cache_auto_prune_var
        ttk.Checkbutton(options, text="텀싯 처리 후 발행실적보고서도 자동 확인", variable=self.auto_result_var).pack(side="left")
        ttk.Checkbutton(options, text="검색 캐시 무시하고 새로 조회", variable=self.force_refresh_var).pack(side="left", padx=16)
        ttk.Checkbutton(options, text="오래된 캐시 자동 정리", variable=self.cache_auto_prune_var).pack(side="left")

        save_options = ttk.Frame(self.win)
        save_options.pack(fill="x", padx=14, pady=4)
        ttk.Checkbutton(save_options, text="텀싯 PDF 저장", variable=self.save_termsheet_pdf_var).pack(side="left")
        ttk.Checkbutton(save_options, text="발행실적 PDF 저장", variable=self.save_result_pdf_var).pack(side="left", padx=16)
        ttk.Checkbutton(save_options, text="OpenDART 공식 API 사용", variable=self.use_opendart_var).pack(side="left")

        buttons = ttk.Frame(self.win)
        buttons.pack(fill="x", padx=14, pady=(4, 14))
        ttk.Button(buttons, text="적용", command=lambda: self._save(close=False)).pack(side="right")
        ttk.Button(buttons, text="저장 후 닫기", command=lambda: self._save(close=True)).pack(side="right", padx=6)
        ttk.Button(buttons, text="닫기", command=self.win.destroy).pack(side="right")

    def _add_number_field(self, parent, row, key, label, desc):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=6)
        var = tk.StringVar(value=str(self.settings.get(key, config.DEFAULT_RUNTIME_SETTINGS.get(key, ""))))
        self.vars[key] = var
        ttk.Entry(parent, textvariable=var, width=14).grid(row=row, column=1, sticky="w", padx=8)
        ttk.Label(parent, text=desc, foreground=config.MUTED).grid(row=row, column=2, sticky="w", padx=8)

    def _settings_from_form(self):
        values = {key: var.get() for key, var in self.vars.items()}
        values.update({key: var.get() for key, var in self.bool_vars.items()})
        values["opendart_api_key"] = state.normalize_api_key(self.opendart_key_var.get())
        values["save_root"] = str(self.app.current_save_root())
        return state.normalize_runtime_settings(values) | {
            "opendart_api_key": values["opendart_api_key"],
            "save_root": values["save_root"],
        }

    def _reset_defaults(self):
        defaults = config.DEFAULT_RUNTIME_SETTINGS
        for key, var in self.vars.items():
            var.set(str(defaults.get(key, "")))
        for key, var in self.bool_vars.items():
            var.set(bool(defaults.get(key, False)))

    def _apply_preset(self, name):
        preset = state.normalize_runtime_settings(config.RUNTIME_PRESETS.get(name, config.DEFAULT_RUNTIME_SETTINGS))
        for key, var in self.vars.items():
            var.set(str(preset.get(key, "")))
        for key, var in self.bool_vars.items():
            var.set(bool(preset.get(key, False)))

    def _save(self, close=False):
        settings = self._settings_from_form()
        state.save_settings(settings)
        self.app.apply_runtime_settings(settings)
        self.app.auto_result_var.set(bool(settings.get("auto_result", True)))
        self.app.force_refresh_var.set(bool(settings.get("force_refresh", False)))
        self.app.save_termsheet_pdf_var.set(bool(settings.get("save_termsheet_pdf", True)))
        self.app.save_result_pdf_var.set(bool(settings.get("save_result_pdf", True)))
        self.app.use_opendart_var.set(bool(settings.get("use_opendart", True)))
        self.app.opendart_key_var.set(settings.get("opendart_api_key", ""))
        self.app._update_save_status()
        self.app.log(
            f"설정 적용: 검색 {config.SEARCH_DAYS}일, 발행실적 {config.RESULT_SEARCH_DAYS}일, "
            f"동시 작업 {config.DOWNLOAD_WORKERS}, 캐시 {config.SEARCH_CACHE_SECONDS // 3600:g}시간"
        )
        if close:
            self.win.destroy()

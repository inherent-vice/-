from __future__ import annotations

import datetime as dt
import os
import sys
import threading
from collections import Counter
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, QUrl
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    QSpinBox,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from dart_app import config, state
from dart_app.domain.input_parser import parse_input_lines
from dart_app.domain.security_name import extract_product_type, extract_round, find_issuer
from dart_app.integrations.dart_web import Dart
from dart_app.qt_app.models import RecordsTableModel
from dart_app.qt_app.theme import COLORS, app_stylesheet
from dart_app.runtime import cache_stats, clear_cache, prune_cache
from dart_app.services.record_workflow import RecordWorkflow, RecordWorkflowOptions
from dart_app.utils.files import stock_output_dir


TERMSHEET_TARGET_PRODUCTS = {"DLB", "DLS", "ELB", "ELS", "SUB"}


class IssuerEditorDialog(QDialog):
    """발행사 매핑 편집 다이얼로그.

    DEFAULT_ISSUERS와 사용자 issuers.json을 머지해 보여주고, 사용자가 추가/수정한
    항목만 issuers.json에 저장합니다. 기본값과 동일한 항목은 저장되지 않습니다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("발행사 매핑")
        self.resize(820, 560)
        self.user_overrides = dict(state.load_json(config.ISSUERS_PATH, {}) or {})

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("발행사 매핑")
        title.setStyleSheet("font-weight: 500; font-size: 12pt;")
        layout.addWidget(title)
        hint = QLabel(
            "종목명 앞부분(prefix)을 DART 회사명으로 연결합니다. "
            "기본값과 다른 사용자 항목만 issuers.json에 저장됩니다."
        )
        hint.setProperty("role", "muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        filter_row = QHBoxLayout()
        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("패턴 또는 회사명으로 검색")
        self.filter_edit.textChanged.connect(self._refresh_table)
        filter_row.addWidget(QLabel("검색"))
        filter_row.addWidget(self.filter_edit, 1)
        layout.addLayout(filter_row)

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["종목명 prefix", "DART 회사명", "구분"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Stretch)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.itemSelectionChanged.connect(self._on_select)
        layout.addWidget(self.table, 1)

        form = QGridLayout()
        form.setHorizontalSpacing(8)
        form.setVerticalSpacing(6)
        form.addWidget(QLabel("패턴"), 0, 0)
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("예: 메리츠")
        form.addWidget(self.prefix_edit, 0, 1)
        form.addWidget(QLabel("회사명"), 0, 2)
        self.company_edit = QLineEdit()
        self.company_edit.setPlaceholderText("예: 메리츠증권")
        form.addWidget(self.company_edit, 0, 3)
        form.setColumnStretch(1, 1)
        form.setColumnStretch(3, 1)
        layout.addLayout(form)

        action_row = QHBoxLayout()
        add_button = QPushButton("추가/수정")
        add_button.clicked.connect(self._add_or_update)
        delete_button = QPushButton("삭제")
        delete_button.clicked.connect(self._delete)
        action_row.addWidget(add_button)
        action_row.addWidget(delete_button)
        action_row.addStretch(1)
        layout.addLayout(action_row)

        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel, self)
        button_box.button(QDialogButtonBox.Save).setText("저장")
        button_box.button(QDialogButtonBox.Cancel).setText("취소")
        button_box.accepted.connect(self._save)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self._refresh_table()

    def _merged(self):
        merged = dict(config.DEFAULT_ISSUERS)
        for prefix, company in (self.user_overrides or {}).items():
            if prefix.startswith("_") or not isinstance(company, str) or not company.strip():
                continue
            merged[prefix.strip()] = company.strip()
        return merged

    def _refresh_table(self):
        needle = self.filter_edit.text().strip().lower() if hasattr(self, "filter_edit") else ""
        merged = self._merged()
        rows = sorted(merged.items())
        if needle:
            rows = [(p, c) for p, c in rows if needle in p.lower() or needle in c.lower()]
        self.table.setRowCount(len(rows))
        for row, (prefix, company) in enumerate(rows):
            source = "사용자" if prefix in self.user_overrides else "기본"
            self.table.setItem(row, 0, QTableWidgetItem(prefix))
            self.table.setItem(row, 1, QTableWidgetItem(company))
            self.table.setItem(row, 2, QTableWidgetItem(source))

    def _on_select(self):
        items = self.table.selectedItems()
        if not items:
            return
        row = items[0].row()
        prefix_item = self.table.item(row, 0)
        company_item = self.table.item(row, 1)
        if prefix_item and company_item:
            self.prefix_edit.setText(prefix_item.text())
            self.company_edit.setText(company_item.text())

    def _add_or_update(self):
        prefix = self.prefix_edit.text().strip()
        company = self.company_edit.text().strip()
        if not prefix or not company:
            QMessageBox.warning(self, "입력 필요", "패턴과 회사명을 모두 입력하세요.")
            return
        self.user_overrides[prefix] = company
        self._refresh_table()

    def _delete(self):
        prefix = self.prefix_edit.text().strip()
        if not prefix:
            return
        if prefix in self.user_overrides:
            self.user_overrides.pop(prefix, None)
            self.prefix_edit.clear()
            self.company_edit.clear()
            self._refresh_table()
            return
        if prefix in config.DEFAULT_ISSUERS:
            QMessageBox.information(
                self,
                "기본 항목",
                "기본 매핑은 직접 삭제할 수 없습니다. 같은 패턴을 다른 회사명으로 저장해 덮어쓸 수 있습니다.",
            )

    def _save(self):
        state.save_user_issuers(self.user_overrides)
        self.accept()


def configure_qt_environment():
    os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.fonts=false")
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen" and not os.environ.get("QT_QPA_FONTDIR"):
        windows_fonts = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        if windows_fonts.exists():
            os.environ["QT_QPA_FONTDIR"] = str(windows_fonts)


def apply_runtime_settings(settings):
    runtime = state.normalize_runtime_settings(settings)
    config.SEARCH_DAYS = runtime["search_days"]
    config.RESULT_SEARCH_DAYS = runtime["result_search_days"]
    config.INDEX_SCAN_LIMIT = runtime["index_scan_limit"]
    config.PDF_SCAN_LIMIT = runtime["pdf_scan_limit"]
    config.RESULT_SCAN_LIMIT = runtime["result_scan_limit"]
    config.RESULT_BODY_SCAN_LIMIT = runtime["result_body_scan_limit"]
    config.RESULT_FRONT_TEXT_SCAN_LIMIT = runtime["result_front_text_scan_limit"]
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
    document_matching.RESULT_BODY_SCAN_LIMIT = config.RESULT_BODY_SCAN_LIMIT
    document_matching.RESULT_FRONT_TEXT_SCAN_LIMIT = config.RESULT_FRONT_TEXT_SCAN_LIMIT
    return runtime


class WorkflowSignals(QObject):
    record_update = Signal(str, str, dict)
    log = Signal(str)
    progress = Signal(bool)
    finished = Signal(int, int)


class WorkflowRunnable(QRunnable):
    def __init__(
        self,
        records,
        issuers,
        options: RecordWorkflowOptions,
        use_opendart,
        opendart_api_key,
        stop_event,
        mode="termsheet",
    ):
        super().__init__()
        self.records = list(records or [])
        self.issuers = issuers
        self.options = options
        self.use_opendart = bool(use_opendart)
        self.opendart_api_key = str(opendart_api_key or "")
        self.stop_event = stop_event
        self.mode = mode
        self.signals = WorkflowSignals()

    def run(self):
        completed = 0
        failed = 0
        try:
            workflow = RecordWorkflow(
                self.issuers,
                self._make_client,
                self.options,
                self._emit_record_update,
                should_stop=self.stop_event.is_set,
            )
            for record in self.records:
                if self.stop_event.is_set():
                    break
                try:
                    stock_code, stock_name = record
                except (TypeError, ValueError) as exc:
                    failed += 1
                    self.signals.progress.emit(False)
                    self.signals.log.emit(f"잘못된 입력 레코드: {record!r} - {exc}")
                    continue
                try:
                    if self.mode == "result":
                        _code, _name, ok = workflow.process_result_record(record)
                        label = "발행실적 갱신" if ok else "발행실적 미발견"
                    else:
                        _code, _name, ok = workflow.process_record(record)
                        label = "완료" if ok else "미발견"
                    completed += 1 if ok else 0
                    failed += 0 if ok else 1
                    self.signals.progress.emit(bool(ok))
                    self.signals.log.emit(f"{stock_code} {stock_name}: {label}")
                except Exception as exc:
                    failed += 1
                    self.signals.progress.emit(False)
                    status_key = "result_status" if self.mode == "result" else "termsheet_status"
                    self.signals.record_update.emit(stock_code, stock_name, {"status": "실패", status_key: str(exc)})
                    self.signals.log.emit(f"{stock_code} {stock_name}: 실패 - {exc}")
        except Exception as exc:
            if not self.stop_event.is_set():
                failed += 1
                self.signals.log.emit(f"작업 초기화 실패: {exc}")
        finally:
            self.signals.finished.emit(completed, failed)

    def _make_client(self):
        return Dart(self.opendart_api_key if self.use_opendart else "")

    def _emit_record_update(self, stock_code, stock_name, **updates):
        self.signals.record_update.emit(str(stock_code), str(stock_name), dict(updates))


class StatusSignals(QObject):
    log = Signal(str)
    finished = Signal()


class StatusRunnable(QRunnable):
    def __init__(self, use_opendart, opendart_api_key):
        super().__init__()
        self.use_opendart = bool(use_opendart)
        self.opendart_api_key = str(opendart_api_key or "")
        self.signals = StatusSignals()

    def run(self):
        try:
            client = Dart(self.opendart_api_key if self.use_opendart else "")
            status = client.check_status()
            self.signals.log.emit(f"DART 상태: {status['summary']}")
            for check in status["checks"]:
                self.signals.log.emit(f"- {check['name']}: {check['detail']}")
        except Exception as exc:
            self.signals.log.emit(f"DART 상태 확인 실패: {exc}")
        finally:
            self.signals.finished.emit()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DART Termsheet Desk")
        self.resize(1440, 920)
        self.setMinimumSize(1160, 760)

        self.issuers = state.load_issuers()
        self.settings = state.load_settings()
        apply_runtime_settings(self.settings)

        self.thread_pool = QThreadPool.globalInstance()
        self.stop_event = threading.Event()
        self.active_workers = []
        self.running = False
        self.completed = 0
        self.failed = 0
        self.input_source_name = ""

        self.model = RecordsTableModel(self)
        self.model.dataChanged.connect(self._on_model_data_changed)
        self._build_ui()
        self._refresh_cache_info()
        self._set_running(False)
        self._refresh_detail()
        if self.settings.get("cache_auto_prune", True):
            QTimer.singleShot(1200, self._auto_prune_cache)

    def _on_model_data_changed(self, _top_left, _bottom_right, roles):
        if not roles or Qt.CheckStateRole in roles:
            self._set_input_summary(self.model.records())

    def _build_ui(self):
        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(18, 14, 18, 18)
        root_layout.setSpacing(14)
        self.setCentralWidget(root)

        root_layout.addWidget(self._build_app_bar())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_left_rail())
        splitter.addWidget(self._build_workspace())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([380, 980])
        root_layout.addWidget(splitter, 1)

    def _make_days_spin(self, value, tooltip):
        return self._make_count_spin(value, 1, 3650, "일", tooltip)

    def _make_count_spin(self, value, min_value, max_value, suffix, tooltip):
        spin = QSpinBox()
        spin.setRange(int(min_value), int(max_value))
        spin.setSuffix(suffix)
        spin.setValue(int(value))
        spin.setToolTip(tooltip)
        spin.setMinimumWidth(92)
        return spin

    def _make_hours_spin(self, value, tooltip):
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 720.0)
        spin.setDecimals(1)
        spin.setSingleStep(0.5)
        spin.setSuffix("시간")
        spin.setValue(float(value))
        spin.setToolTip(tooltip)
        spin.setMinimumWidth(104)
        return spin

    def _build_app_bar(self):
        bar = QFrame()
        bar.setObjectName("AppBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(4, 0, 4, 12)
        layout.setSpacing(14)

        mark = QLabel("✣")
        mark.setStyleSheet(f"font-size: 24px; color: {COLORS['ink']}; background: transparent;")
        layout.addWidget(mark)

        title = QLabel("DART Termsheet Desk")
        title.setObjectName("BrandTitle")
        layout.addWidget(title)

        subtitle = QLabel("텀싯 · 발행실적 · PDF 저장")
        subtitle.setObjectName("SubtleText")
        subtitle.setProperty("role", "muted")
        layout.addWidget(subtitle)
        layout.addStretch(1)

        self.summary_label = QLabel("대기")
        self.summary_label.setProperty("role", "muted")
        layout.addWidget(self.summary_label)

        self.primary_button = QPushButton("대상 다운로드")
        self.primary_button.setObjectName("PrimaryButton")
        self.primary_button.clicked.connect(self.run_download)
        layout.addWidget(self.primary_button)

        self.stop_button = QPushButton("중지")
        self.stop_button.setObjectName("DangerButton")
        self.stop_button.clicked.connect(self.stop_worker)
        layout.addWidget(self.stop_button)
        return bar

    def _build_left_rail(self):
        scroll = QScrollArea()
        scroll.setObjectName("LeftRailScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setMinimumWidth(340)
        scroll.setMaximumWidth(460)
        self.left_scroll = scroll

        rail = QFrame()
        rail.setObjectName("LeftRail")
        rail.setMinimumWidth(340)
        rail.setMaximumWidth(460)
        layout = QVBoxLayout(rail)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(9)

        input_header = QHBoxLayout()
        label = QLabel("입력")
        label.setStyleSheet("font-weight: 600; background: transparent;")
        input_header.addWidget(label)
        input_header.addStretch(1)
        self.load_file_button = QPushButton("파일 불러오기")
        self.load_file_button.clicked.connect(self.choose_input_file)
        input_header.addWidget(self.load_file_button)
        layout.addLayout(input_header)

        self.input_text = QTextEdit()
        self.input_text.setPlaceholderText("KR6HN0008746  하나증권(DLB)2681")
        self.input_text.setMinimumHeight(112)
        layout.addWidget(self.input_text)

        self.input_summary_label = QLabel("붙여넣거나 파일을 불러온 뒤 입력 정리를 누르세요.")
        self.input_summary_label.setWordWrap(True)
        self.input_summary_label.setProperty("role", "muted")
        layout.addWidget(self.input_summary_label)

        self.save_root_edit = QLineEdit(str(state.normalize_save_root(self.settings.get("save_root"))))
        self.save_root_edit.setVisible(False)
        self.save_root_display = QLabel("")
        self.save_root_display.setWordWrap(False)
        self.save_root_display.setProperty("role", "muted")
        self.save_root_display.setTextInteractionFlags(Qt.TextSelectableByMouse)
        browse = QPushButton("변경")
        browse.clicked.connect(self.choose_save_root)
        self.save_root_button = browse
        self.open_save_root_button = QPushButton("열기")
        self.open_save_root_button.clicked.connect(self.open_save_root)
        save_row = QHBoxLayout()
        save_row.addWidget(self.save_root_display, 1)
        save_row.addWidget(browse)
        save_row.addWidget(self.open_save_root_button)
        layout.addLayout(save_row)
        self._update_save_root_display()

        option_title = QLabel("기본 옵션")
        option_title.setObjectName("SectionTitle")
        layout.addWidget(option_title)

        options = QGridLayout()
        options.setHorizontalSpacing(12)
        options.setVerticalSpacing(8)
        self.auto_result_check = QCheckBox("발행실적 자동 확인")
        self.auto_result_check.setChecked(bool(self.settings.get("auto_result", True)))
        self.force_refresh_check = QCheckBox("캐시 무시")
        self.force_refresh_check.setChecked(bool(self.settings.get("force_refresh", False)))
        self.save_termsheet_check = QCheckBox("텀싯 PDF 저장")
        self.save_termsheet_check.setChecked(bool(self.settings.get("save_termsheet_pdf", True)))
        self.save_result_check = QCheckBox("발행실적 PDF 저장")
        self.save_result_check.setChecked(bool(self.settings.get("save_result_pdf", True)))
        self.use_opendart_check = QCheckBox("OpenDART 사용")
        self.use_opendart_check.setChecked(bool(self.settings.get("use_opendart", True)))
        self.filter_termsheet_targets_check = QCheckBox("텀싯 대상만 처리")
        self.filter_termsheet_targets_check.setChecked(bool(self.settings.get("filter_termsheet_targets", True)))
        self.filter_termsheet_targets_check.setToolTip("텀싯 작업은 DLB/DLS/ELB/ELS/신종(SUB)만 포함하고 기타 상품은 제외합니다.")
        self.filter_termsheet_targets_check.stateChanged.connect(self._refresh_summary_from_model)
        options.addWidget(self.auto_result_check, 0, 0)
        options.addWidget(self.save_termsheet_check, 0, 1)
        options.addWidget(self.save_result_check, 1, 0)
        options.addWidget(self.use_opendart_check, 1, 1)
        options.addWidget(self.filter_termsheet_targets_check, 2, 0, 1, 2)
        layout.addLayout(options)

        self.advanced_toggle_button = QPushButton("고급 옵션 보기")
        self.advanced_toggle_button.setCheckable(True)
        self.advanced_toggle_button.toggled.connect(self._toggle_advanced_options)

        self.advanced_controls = QFrame()
        self.advanced_controls.setObjectName("AdvancedPanel")
        advanced_layout = QVBoxLayout(self.advanced_controls)
        advanced_layout.setContentsMargins(12, 12, 12, 12)
        advanced_layout.setSpacing(8)
        advanced_layout.addWidget(self.force_refresh_check)

        initial_key = state.normalize_api_key(self.settings.get("opendart_api_key")) or state.discover_opendart_api_key()
        self.opendart_key_edit = QLineEdit(initial_key)
        self.opendart_key_edit.setPlaceholderText("OpenDART API key")
        self.opendart_key_edit.setEchoMode(QLineEdit.Password)
        self.opendart_key_edit.setToolTip("OpenDART API 키는 화면에 노출되지 않도록 기본 마스킹됩니다.")
        key_row = QHBoxLayout()
        key_label = QLabel("OpenDART 키")
        key_label.setProperty("role", "muted")
        key_row.addWidget(key_label)
        key_row.addWidget(self.opendart_key_edit, 1)
        advanced_layout.addLayout(key_row)

        status_button = QPushButton("DART 상태")
        status_button.clicked.connect(self.run_status_check)
        save_button = QPushButton("옵션 저장")
        save_button.clicked.connect(self.save_settings)
        issuer_button = QPushButton("발행사 매핑")
        issuer_button.clicked.connect(self.open_issuer_editor)
        maintenance_grid = QGridLayout()
        maintenance_grid.setHorizontalSpacing(8)
        maintenance_grid.setVerticalSpacing(8)
        maintenance_grid.addWidget(status_button, 0, 0)
        maintenance_grid.addWidget(issuer_button, 0, 1)
        maintenance_grid.addWidget(save_button, 1, 0, 1, 2)
        advanced_layout.addLayout(maintenance_grid)
        self.advanced_controls.setVisible(False)

        workflow_title = QLabel("작업 순서")
        workflow_title.setObjectName("SectionTitle")
        layout.addWidget(workflow_title)
        run_grid = QGridLayout()
        self.preview_button = QPushButton("입력 정리")
        self.preview_button.clicked.connect(lambda: self.preview_records(clear_source=True))
        check_button = QPushButton("대상 확인")
        check_button.clicked.connect(self.run_check)
        result_button = QPushButton("발행실적 갱신")
        result_button.clicked.connect(self.run_result_refresh)
        run_grid.addWidget(self.preview_button, 0, 0)
        run_grid.addWidget(check_button, 0, 1)
        run_grid.addWidget(result_button, 1, 0, 1, 2)
        layout.addLayout(run_grid)

        self.worker_buttons = [
            self.primary_button,
            self.load_file_button,
            self.save_root_button,
            self.open_save_root_button,
            self.advanced_toggle_button,
            self.preview_button,
            check_button,
            result_button,
            status_button,
            issuer_button,
            save_button,
        ]

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setMinimumHeight(24)
        self.progress.setMaximumHeight(28)
        self.progress.setFormat("작업 대기")
        layout.addWidget(self.progress)
        layout.addWidget(self.advanced_toggle_button)
        layout.addWidget(self.advanced_controls)

        dark = QFrame()
        dark.setObjectName("DarkPanel")
        self.log_panel = dark
        dark_layout = QVBoxLayout(dark)
        dark_layout.setContentsMargins(12, 12, 12, 12)
        dark_layout.setSpacing(6)
        dark_layout.addWidget(QLabel("작업 로그"))
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(100)
        dark_layout.addWidget(self.log_text, 1)
        self.log_toggle_button = QPushButton("작업 로그 보기")
        self.log_toggle_button.setCheckable(True)
        self.log_toggle_button.toggled.connect(self._toggle_log_panel)
        layout.addWidget(self.log_toggle_button)
        self.log_panel.setVisible(False)
        layout.addWidget(dark)
        scroll.setWidget(rail)
        return scroll

    def _build_workspace(self):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        table_frame = QFrame()
        table_frame.setObjectName("TableFrame")
        table_layout = QVBoxLayout(table_frame)
        table_layout.setContentsMargins(16, 16, 16, 16)
        table_layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("처리 대상")
        title.setStyleSheet("font-weight: 600; background: transparent;")
        header.addWidget(title)
        header.addStretch(1)
        self.cache_label = QLabel("")
        self.cache_label.setProperty("role", "muted")
        header.addWidget(self.cache_label)
        table_layout.addLayout(header)

        self.table_hint_label = QLabel("입력 정리 후 처리 대상이 여기에 표시됩니다. 체크를 해제한 행은 다운로드에서 제외됩니다.")
        self.table_hint_label.setWordWrap(True)
        self.table_hint_label.setProperty("role", "muted")
        table_layout.addWidget(self.table_hint_label)

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.verticalHeader().setVisible(False)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table.setColumnWidth(0, 58)
        self.table.setColumnWidth(1, 130)
        self.table.setColumnWidth(2, 220)
        self.table.setColumnWidth(6, 90)
        self.table.clicked.connect(self._refresh_detail)
        self.table.doubleClicked.connect(self._open_selected_artifact)
        table_layout.addWidget(self.table, 1)
        layout.addWidget(table_frame, 3)

        layout.addWidget(self._build_inspector(), 2)
        return container

    def _build_inspector(self):
        inspector = QFrame()
        inspector.setObjectName("Inspector")
        layout = QVBoxLayout(inspector)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        self.detail_title = QLabel("선택된 종목 없음")
        self.detail_title.setStyleSheet("font-weight: 600; background: transparent;")
        layout.addWidget(self.detail_title)

        action_row = QHBoxLayout()
        self.candidate_summary_label = QLabel("검증 후보 없음")
        self.candidate_summary_label.setWordWrap(True)
        self.candidate_summary_label.setProperty("role", "muted")
        action_row.addWidget(self.candidate_summary_label, 1)
        self.open_file_button = QPushButton("PDF 열기")
        self.open_file_button.clicked.connect(self._open_selected_file)
        self.open_folder_button = QPushButton("폴더 열기")
        self.open_folder_button.clicked.connect(self._open_selected_folder)
        action_row.addWidget(self.open_file_button)
        action_row.addWidget(self.open_folder_button)
        layout.addLayout(action_row)

        self.tabs = QTabWidget()
        self.candidate_table = QTableWidget(0, 6)
        self.candidate_table.setHorizontalHeaderLabels(["판정", "근거", "점수", "문서명", "일치 근거", "제외 사유"])
        self.candidate_table.horizontalHeader().setStretchLastSection(True)
        self.candidate_table.verticalHeader().setVisible(False)
        self.tabs.addTab(self.candidate_table, "검증 상세")

        self.result_detail = QTextEdit()
        self.result_detail.setReadOnly(True)
        self.tabs.addTab(self.result_detail, "발행실적")

        cache_tab = QWidget()
        cache_layout = QVBoxLayout(cache_tab)
        self.cache_detail = QLabel("")
        self.cache_detail.setWordWrap(True)
        cache_layout.addWidget(self.cache_detail)

        policy_note = QLabel("보관일이 지난 내부 검색/문서/PDF 캐시만 정리합니다. 저장 폴더의 결과 PDF는 건드리지 않습니다.")
        policy_note.setWordWrap(True)
        policy_note.setProperty("role", "muted")
        cache_layout.addWidget(policy_note)

        policy = state.normalize_runtime_settings(self.settings)
        policy_grid = QGridLayout()
        policy_grid.setHorizontalSpacing(12)
        policy_grid.setVerticalSpacing(8)
        self.cache_auto_prune_check = QCheckBox("자동 정리")
        self.cache_auto_prune_check.setChecked(bool(policy.get("cache_auto_prune", True)))
        self.cache_auto_prune_check.setToolTip("앱을 열 때 보관일이 지난 내부 캐시를 자동으로 정리합니다.")
        self.cache_search_days_spin = self._make_days_spin(
            policy["cache_search_days"], "DART 검색 결과 캐시 파일 보관일"
        )
        self.cache_document_days_spin = self._make_days_spin(
            policy["cache_document_days"], "목차/뷰어/OpenDART 문서 캐시 파일 보관일"
        )
        self.cache_pdf_days_spin = self._make_days_spin(policy["cache_pdf_days"], "내부 PDF 캐시 파일 보관일")
        self.search_cache_hours_spin = self._make_hours_spin(
            policy["search_cache_hours"], "DART 검색 결과를 새로 조회하지 않고 재사용할 시간"
        )
        self.result_scan_limit_spin = self._make_count_spin(
            policy["result_scan_limit"], 1, 500, "건", "발행실적 후보로 볼 전체 검색 결과 개수"
        )
        self.result_body_scan_limit_spin = self._make_count_spin(
            policy["result_body_scan_limit"], 1, 500, "건", "OpenDART 본문까지 확인할 발행실적 후보 개수"
        )
        self.result_front_text_scan_limit_spin = self._make_count_spin(
            policy["result_front_text_scan_limit"], 1, 500, "건", "PDF 앞부분까지 확인할 발행실적 후보 개수"
        )
        policy_grid.addWidget(self.cache_auto_prune_check, 0, 0)
        policy_grid.addWidget(QLabel("검색 보관"), 0, 1)
        policy_grid.addWidget(self.cache_search_days_spin, 0, 2)
        policy_grid.addWidget(QLabel("문서 보관"), 1, 0)
        policy_grid.addWidget(self.cache_document_days_spin, 1, 1)
        policy_grid.addWidget(QLabel("PDF 보관"), 1, 2)
        policy_grid.addWidget(self.cache_pdf_days_spin, 1, 3)
        policy_grid.addWidget(QLabel("검색 유효"), 2, 0)
        policy_grid.addWidget(self.search_cache_hours_spin, 2, 1)
        policy_grid.addWidget(QLabel("실적 전체"), 2, 2)
        policy_grid.addWidget(self.result_scan_limit_spin, 2, 3)
        policy_grid.addWidget(QLabel("실적 본문"), 3, 0)
        policy_grid.addWidget(self.result_body_scan_limit_spin, 3, 1)
        policy_grid.addWidget(QLabel("실적 PDF"), 3, 2)
        policy_grid.addWidget(self.result_front_text_scan_limit_spin, 3, 3)
        policy_grid.setColumnStretch(4, 1)
        cache_layout.addLayout(policy_grid)

        policy_row = QHBoxLayout()
        self.cache_policy_save_button = QPushButton("정책 저장")
        self.cache_policy_save_button.clicked.connect(lambda: self.save_settings(show_message=True))
        self.cache_prune_button = QPushButton("오래된 캐시 정리")
        self.cache_prune_button.clicked.connect(self.prune_cache_ui)
        refresh_button = QPushButton("새로고침")
        refresh_button.clicked.connect(self._refresh_cache_info)
        policy_row.addWidget(self.cache_policy_save_button)
        policy_row.addWidget(self.cache_prune_button)
        policy_row.addWidget(refresh_button)
        policy_row.addStretch(1)
        cache_layout.addLayout(policy_row)

        clear_row = QHBoxLayout()
        self.cache_action_buttons = [self.cache_policy_save_button, self.cache_prune_button, refresh_button]
        for label, kind in (
            ("검색 캐시 삭제", "search"),
            ("문서 캐시 삭제", "document"),
            ("PDF 캐시 삭제", "pdf"),
            ("전체 캐시 삭제", "all"),
        ):
            button = QPushButton(label)
            if kind == "all":
                button.setObjectName("DangerButton")
            button.clicked.connect(lambda _checked=False, k=kind: self.clear_cache_ui(k))
            clear_row.addWidget(button)
            self.cache_action_buttons.append(button)
        clear_row.addStretch(1)
        cache_layout.addLayout(clear_row)
        cache_layout.addStretch(1)
        self.tabs.addTab(cache_tab, "캐시")

        layout.addWidget(self.tabs, 1)
        return inspector

    def preview_records(self, clear_source=False):
        if clear_source:
            self.input_source_name = ""
        records = parse_input_lines(self.input_text.toPlainText().splitlines())
        rows = [self._initial_record_data(record) for record in records]
        self.model.set_records(rows)
        self._sync_filter_markers()
        self._set_input_summary(self.model.records())
        if rows:
            self.table.selectRow(0)
            self._refresh_detail()
        return [(row["stock_code"], row["stock_name"]) for row in rows]

    def _refresh_summary_from_model(self):
        self._sync_filter_markers()
        self._set_input_summary(self.model.records())

    def _set_input_summary(self, rows):
        summary = self._records_summary(rows)
        self.summary_label.setText(self._records_summary(rows, compact=True))
        if not rows:
            self.input_summary_label.setText("입력된 종목이 없습니다.")
            if hasattr(self, "table_hint_label"):
                self.table_hint_label.show()
            return
        if hasattr(self, "table_hint_label"):
            self.table_hint_label.hide()
        prefix = f"{self.input_source_name} · " if self.input_source_name else ""
        self.input_summary_label.setText(prefix + summary)

    def _records_summary(self, rows, compact=False):
        if not rows:
            return "대상 0건"
        products = Counter(row.get("product") or "기타" for row in rows)
        mapped = sum(1 for row in rows if row.get("issuer_mapped"))
        selected_count = sum(1 for row in rows if row.get("target", True))
        selected_rows = [row for row in rows if row.get("target", True)]
        target_count = sum(1 for row in selected_rows if self._is_termsheet_target_row(row))
        excluded_count = selected_count - target_count
        runtime_count = target_count if self.filter_termsheet_targets_check.isChecked() else selected_count
        runtime = self._estimated_runtime_label(runtime_count)
        if compact:
            parts = [self._target_count_label(selected_count, len(rows))]
            if self.filter_termsheet_targets_check.isChecked() and excluded_count:
                parts.append(f"텀싯 처리 {target_count:,}건")
                parts.append(f"제외 {excluded_count:,}건")
            if runtime:
                parts.append(runtime.replace("예상 ", ""))
            return " · ".join(parts)

        parts = [self._target_count_label(selected_count, len(rows))]
        for key in ("DLB", "DLS", "SUB", "기타"):
            if products.get(key):
                parts.append(f"{key} {products[key]:,}")
        if len(products) > 4:
            others = sum(count for key, count in products.items() if key not in {"DLB", "DLS", "SUB", "기타"})
            if others:
                parts.append(f"기타상품 {others:,}")
        parts.append(f"발행사 매핑 {mapped:,}/{len(rows):,}")
        if self.filter_termsheet_targets_check.isChecked() and excluded_count:
            parts.append(f"텀싯 처리 {target_count:,}/{len(rows):,}")
            parts.append(f"기타 제외 {excluded_count:,}")
        if runtime:
            parts.append(runtime)
        return " · ".join(parts)

    def _target_count_label(self, selected_count, total_count):
        if selected_count == total_count:
            return f"대상 {total_count:,}건"
        return f"대상 {selected_count:,}/{total_count:,}건"

    def _estimated_runtime_label(self, count):
        if count < 100:
            return ""
        workers = max(1, int(getattr(config, "DOWNLOAD_WORKERS", 1) or 1))
        min_interval = max(0.1, float(getattr(config, "HTTP_MIN_INTERVAL", 0.8) or 0.8))
        minutes = max(1, round((count * min_interval / workers) / 60))
        return f"예상 최소 {minutes:,}분+"

    def _is_termsheet_target_row(self, row):
        return str(row.get("product") or "").upper() in TERMSHEET_TARGET_PRODUCTS

    def _sync_filter_markers(self):
        if not hasattr(self, "filter_termsheet_targets_check"):
            return
        enabled = self.filter_termsheet_targets_check.isChecked()
        for row in self.model.records():
            if self._is_termsheet_target_row(row):
                continue
            status = str(row.get("status") or "")
            termsheet_status = str(row.get("termsheet_status") or "")
            if enabled and status in {"", "대기", "제외 예정"} and termsheet_status in {"", "상품 유형 제외 예정"}:
                self.model.upsert(
                    row.get("stock_code"),
                    row.get("stock_name"),
                    {"status": "제외 예정", "termsheet_status": "상품 유형 제외 예정"},
                )
            elif not enabled and status == "제외 예정" and termsheet_status == "상품 유형 제외 예정":
                self.model.upsert(
                    row.get("stock_code"),
                    row.get("stock_name"),
                    {"status": "대기", "termsheet_status": ""},
                )

    def _initial_record_data(self, record):
        stock_code, stock_name = record
        issuer, mapped = find_issuer(stock_name, self.issuers)
        round_full, round_base = extract_round(stock_name)
        product = extract_product_type(stock_name)
        return {
            "target": True,
            "stock_code": stock_code,
            "stock_name": stock_name,
            "issuer": issuer or "",
            "issuer_mapped": mapped,
            "round_full": round_full or "",
            "round_base": round_base or "",
            "product": product or "",
            "status": "대기",
            "termsheet_status": "",
            "result_status": "",
            "folder": str(stock_output_dir(self.current_save_root(), stock_code)),
        }

    def run_download(self):
        records = self._records_or_preview(mode="termsheet")
        self._start_records(records, mode="termsheet", save_termsheet_pdf=self.save_termsheet_check.isChecked(), auto_result=self.auto_result_check.isChecked())

    def run_check(self):
        records = self._records_or_preview(mode="termsheet")
        self._start_records(records, mode="termsheet", save_termsheet_pdf=False, auto_result=False)

    def run_result_refresh(self):
        records = self._records_or_preview(mode="result")
        self._start_records(records, mode="result", save_termsheet_pdf=False, auto_result=False)

    def _records_or_preview(self, mode="termsheet"):
        if not self.model.records():
            self.preview_records()
        rows = self.model.records()
        rows = [row for row in rows if row.get("target", True)]
        if mode == "termsheet" and self.filter_termsheet_targets_check.isChecked():
            included = [row for row in rows if self._is_termsheet_target_row(row)]
            excluded = [row for row in rows if not self._is_termsheet_target_row(row)]
            for row in excluded:
                self.model.upsert(
                    row.get("stock_code"),
                    row.get("stock_name"),
                    {"status": "제외", "termsheet_status": "상품 유형 제외"},
                )
            if excluded:
                self.log(f"텀싯 대상 외 상품 제외: {len(excluded):,}건")
            rows = included
        records = [(row["stock_code"], row["stock_name"]) for row in rows]
        if not records:
            self.summary_label.setText("처리 대상 없음")
            self.log("처리 대상이 없습니다. 텀싯 대상 필터를 해제하거나 입력을 확인하세요.")
        return records

    def _start_records(self, records, mode, save_termsheet_pdf, auto_result):
        if self.running or not records:
            return
        if len(records) >= 300 and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
            runtime = self._estimated_runtime_label(len(records))
            runtime_text = f"\n\n{runtime}" if runtime else ""
            answer = QMessageBox.question(
                self,
                "대량 작업 확인",
                f"{len(records):,}건을 처리합니다. DART 요청이 오래 걸릴 수 있고, 작업 중 중지할 수 있습니다.{runtime_text}\n\n계속할까요?",
            )
            if answer != QMessageBox.Yes:
                return
        self.save_settings(show_message=False)
        self.stop_event.clear()
        self.completed = 0
        self.failed = 0
        self.progress.setRange(0, max(1, len(records)))
        self.progress.setValue(0)
        self.progress.setFormat("진행 %v/%m")
        options = RecordWorkflowOptions(
            save_root=self.current_save_root(),
            search_days=config.SEARCH_DAYS,
            result_search_days=config.RESULT_SEARCH_DAYS,
            save_termsheet_pdf=save_termsheet_pdf,
            save_result_pdf=self.save_result_check.isChecked(),
            auto_result=auto_result,
            force_refresh=self.force_refresh_check.isChecked(),
        )
        worker = WorkflowRunnable(
            records,
            self.issuers,
            options,
            self.use_opendart_check.isChecked(),
            self.opendart_key_edit.text().strip(),
            self.stop_event,
            mode=mode,
        )
        worker.signals.record_update.connect(self._on_record_update)
        worker.signals.log.connect(self.log)
        worker.signals.progress.connect(self._on_progress)
        worker.signals.finished.connect(lambda completed, failed, w=worker: self._on_finished(completed, failed, w))
        self.active_workers.append(worker)
        self._set_running(True)
        self.log(("발행실적" if mode == "result" else "텀싯") + f" 작업 시작: {len(records)}건")
        self.log(
            "옵션: "
            f"OpenDART {'사용' if self.use_opendart_check.isChecked() else '미사용'}, "
            f"캐시 {'무시' if self.force_refresh_check.isChecked() else '사용'}, "
            f"저장 {self.current_save_root()}"
        )
        self.thread_pool.start(worker)

    def run_status_check(self):
        if self.running:
            return
        self.progress.setRange(0, 0)
        self.progress.setFormat("상태 확인 중")
        worker = StatusRunnable(self.use_opendart_check.isChecked(), self.opendart_key_edit.text().strip())
        worker.signals.log.connect(self.log)
        worker.signals.finished.connect(lambda w=worker: self._on_status_finished(w))
        self.active_workers.append(worker)
        self._set_running(True)
        self.log("DART 상태 확인 시작")
        self.thread_pool.start(worker)

    def stop_worker(self):
        self.stop_event.set()
        self.log("중지 요청됨")

    def _on_record_update(self, stock_code, stock_name, updates):
        self.model.upsert(stock_code, stock_name, updates)
        self._refresh_detail()

    def _on_progress(self, ok):
        self.completed += 1 if ok else 0
        self.failed += 0 if ok else 1
        self.progress.setValue(self.progress.value() + 1)
        self.summary_label.setText(f"완료 {self.completed} · 실패/미발견 {self.failed}")

    def _on_finished(self, completed, failed, worker=None):
        self._release_worker(worker)
        self._set_running(False)
        self._refresh_cache_info()
        self._auto_prune_cache()
        self.progress.setFormat(f"완료 {completed} / 실패·미발견 {failed}")
        self.summary_label.setText(f"완료 {completed} · 실패/미발견 {failed}")
        self.log(f"작업 종료: 완료 {completed}건, 실패/미발견 {failed}건")

    def _on_status_finished(self, worker=None):
        self._release_worker(worker)
        self._set_running(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("작업 대기")
        self.log("DART 상태 확인 종료")

    def _release_worker(self, worker):
        if worker in self.active_workers:
            self.active_workers.remove(worker)

    def _toggle_advanced_options(self, checked):
        self.advanced_controls.setVisible(bool(checked))
        self.advanced_toggle_button.setText("고급 옵션 숨기기" if checked else "고급 옵션 보기")
        if checked:
            QTimer.singleShot(0, lambda: self.left_scroll.ensureWidgetVisible(self.advanced_controls, 0, 12))

    def _toggle_log_panel(self, checked):
        self.log_panel.setVisible(bool(checked))
        self.log_toggle_button.setText("작업 로그 숨기기" if checked else "작업 로그 보기")

    def _set_running(self, running):
        self.running = bool(running)
        for button in self.worker_buttons:
            button.setEnabled(not running)
        for button in getattr(self, "cache_action_buttons", []):
            button.setEnabled(not running)
        self.stop_button.setEnabled(running)

    def _refresh_detail(self):
        row = self.table.currentIndex().row()
        record = self.model.record_at(row)
        if not record:
            self.detail_title.setText("선택된 종목 없음")
            self.candidate_summary_label.setText("검증 후보 없음")
            self.candidate_table.clearSpans()
            self.candidate_table.setRowCount(1)
            self.candidate_table.setSpan(0, 0, 1, self.candidate_table.columnCount())
            hint_item = QTableWidgetItem("입력 정리 후 대상 행을 선택하면 검증 후보가 표시됩니다.")
            hint_item.setFlags(Qt.ItemIsEnabled)
            self.candidate_table.setItem(0, 0, hint_item)
            self.result_detail.setPlainText("입력 정리 후 행을 선택하면 발행실적 검증 근거가 표시됩니다.")
            self.open_file_button.setEnabled(False)
            self.open_folder_button.setEnabled(False)
            self.open_file_button.hide()
            self.open_folder_button.hide()
            return
        self.open_file_button.show()
        self.open_folder_button.show()
        self.detail_title.setText(f"{record.get('stock_code', '')} · {record.get('stock_name', '')}")
        candidates = self._candidate_rows_for_record(record)
        visible_candidates = self._visible_candidates(candidates)
        self.candidate_summary_label.setText(self._candidate_summary(candidates, visible_candidates))
        self.candidate_table.clearSpans()
        self.candidate_table.setRowCount(len(visible_candidates))
        for row_index, candidate in enumerate(visible_candidates):
            values = [
                candidate.get("grade", ""),
                candidate.get("source", ""),
                candidate.get("score", ""),
                candidate.get("title", ""),
                ", ".join(candidate.get("evidence") or []),
                candidate.get("reject_reason", ""),
            ]
            for col_index, value in enumerate(values):
                self.candidate_table.setItem(row_index, col_index, QTableWidgetItem(str(value or "")))
        self.candidate_table.resizeColumnsToContents()
        self.open_file_button.setEnabled(bool(record.get("file") or record.get("result_file")))
        self.open_folder_button.setEnabled(bool(record.get("folder")))

        result_lines = [
            f"상태: {record.get('result_status', '')}",
            f"사유: {record.get('result_reason', '')}",
            "",
            "근거:",
        ]
        result_lines.extend(f"- {item}" for item in (record.get("result_evidence") or []))
        if record.get("result_file"):
            result_lines.extend(["", f"PDF: {record.get('result_file')}"])
        self.result_detail.setPlainText("\n".join(result_lines).strip())

    def _candidate_rows_for_record(self, record):
        return [
            *(record.get("candidates") or []),
            *(record.get("result_candidates") or []),
        ]

    def _visible_candidates(self, candidates, limit=80):
        if len(candidates) <= limit:
            return list(candidates)
        visible = []
        seen = set()

        def append(candidate):
            key = (
                candidate.get("rcp_no"),
                candidate.get("dcm_no"),
                candidate.get("title"),
                candidate.get("source"),
                candidate.get("grade"),
            )
            if key in seen:
                return
            seen.add(key)
            visible.append(candidate)

        for candidate in candidates:
            if candidate.get("grade") != "제외":
                append(candidate)
        for candidate in candidates:
            if len(visible) >= limit:
                break
            append(candidate)
        return visible

    def _candidate_summary(self, candidates, visible):
        total = len(candidates)
        if not total:
            return "검증 후보 없음"
        grades = Counter(candidate.get("grade") or "미분류" for candidate in candidates)
        sources = Counter(candidate.get("source") or "unknown" for candidate in candidates)
        hidden = total - len(visible)
        parts = [
            f"전체 {total:,}건",
            f"확정/검토 {total - grades.get('제외', 0):,}건",
            f"제외 {grades.get('제외', 0):,}건",
        ]
        if sources:
            parts.append("근거 " + ", ".join(f"{key}:{value}" for key, value in sources.most_common(3)))
        if hidden > 0:
            parts.append(f"주요 {len(visible):,}건만 표시, {hidden:,}건 접힘")
        return " · ".join(parts)

    def selected_record(self):
        return self.model.record_at(self.table.currentIndex().row())

    def choose_save_root(self):
        path = QFileDialog.getExistingDirectory(self, "저장 폴더 선택", str(self.current_save_root()))
        if path:
            self._set_save_root(path)
            self.save_settings(show_message=False)
            self.log(f"저장 폴더 변경: {path}")

    def open_save_root(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.current_save_root())))

    def _set_save_root(self, path):
        self.save_root_edit.setText(str(state.normalize_save_root(path)))
        self._update_save_root_display()

    def _update_save_root_display(self):
        path = self.current_save_root()
        text = str(path)
        self.save_root_display.setText(self._compact_path_text(path))
        self.save_root_display.setToolTip(text)

    def _compact_path_text(self, path):
        text = str(path)
        normalized = text.replace("/", "\\")
        if normalized.startswith("\\\\"):
            parts = [part for part in normalized[2:].split("\\") if part]
            if len(parts) >= 3:
                return f"저장: {parts[-1]}"
            return text
        parts = [part for part in normalized.split("\\") if part]
        if len(parts) >= 3:
            return f"저장: {parts[-1]}"
        return text

    def choose_input_file(self):
        path, _filter = QFileDialog.getOpenFileName(
            self,
            "종목 파일 선택",
            str(Path.cwd()),
            "Text files (*.txt *.tsv *.csv);;All files (*.*)",
        )
        if path:
            self.load_input_file(path)

    def load_input_file(self, path):
        path = Path(path)
        raw = path.read_bytes()
        last_error = None
        for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError as exc:
                last_error = exc
        else:
            raise UnicodeDecodeError("unknown", raw, 0, 1, str(last_error))
        self.input_text.setPlainText(text)
        self.input_source_name = path.name
        records = self.preview_records()
        self.log(f"파일 불러오기: {path} ({len(records):,}건)")
        return records

    def current_save_root(self):
        return state.normalize_save_root(self.save_root_edit.text())

    def open_issuer_editor(self):
        dialog = IssuerEditorDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.issuers = state.load_issuers()
            self.log("발행사 매핑을 갱신했습니다.")
            QMessageBox.information(self, "저장 완료", "발행사 매핑을 저장했습니다.")

    def save_settings(self, show_message=True):
        settings = state.load_settings()
        settings.update({
            "save_root": str(self.current_save_root()),
            "opendart_api_key": self.opendart_key_edit.text().strip(),
            "auto_result": self.auto_result_check.isChecked(),
            "force_refresh": self.force_refresh_check.isChecked(),
            "save_termsheet_pdf": self.save_termsheet_check.isChecked(),
            "save_result_pdf": self.save_result_check.isChecked(),
            "use_opendart": self.use_opendart_check.isChecked(),
            "filter_termsheet_targets": self.filter_termsheet_targets_check.isChecked(),
            "search_cache_hours": self.search_cache_hours_spin.value(),
            "result_scan_limit": self.result_scan_limit_spin.value(),
            "result_body_scan_limit": self.result_body_scan_limit_spin.value(),
            "result_front_text_scan_limit": self.result_front_text_scan_limit_spin.value(),
            "cache_auto_prune": self.cache_auto_prune_check.isChecked(),
            "cache_search_days": self.cache_search_days_spin.value(),
            "cache_document_days": self.cache_document_days_spin.value(),
            "cache_pdf_days": self.cache_pdf_days_spin.value(),
        })
        state.save_settings(settings)
        self.settings = state.load_settings()
        apply_runtime_settings(self.settings)
        if show_message:
            QMessageBox.information(self, "저장 완료", "설정을 저장했습니다.")

    def _cache_policy_from_ui(self):
        return {
            "cache_auto_prune": self.cache_auto_prune_check.isChecked(),
            "cache_search_days": self.cache_search_days_spin.value(),
            "cache_document_days": self.cache_document_days_spin.value(),
            "cache_pdf_days": self.cache_pdf_days_spin.value(),
        }

    def prune_cache_ui(self):
        if self.running:
            return
        self.save_settings(show_message=False)
        try:
            removed = prune_cache(config.CACHE_DIR, self.settings)
            mb = removed["bytes"] / (1024 * 1024)
            self.log(f"오래된 캐시 정리: {removed['files']}개 / {mb:.1f} MB")
            self._refresh_cache_info()
            QMessageBox.information(self, "캐시 정리", f"오래된 캐시 {removed['files']}개를 정리했습니다.")
        except Exception as exc:
            QMessageBox.critical(self, "정리 실패", str(exc))

    def _auto_prune_cache(self):
        if self.running or not self.cache_auto_prune_check.isChecked():
            return
        try:
            removed = prune_cache(config.CACHE_DIR, {**self.settings, **self._cache_policy_from_ui()})
            if removed["files"]:
                mb = removed["bytes"] / (1024 * 1024)
                self.log(f"자동 캐시 정리: {removed['files']}개 / {mb:.1f} MB")
                self._refresh_cache_info()
        except Exception as exc:
            self.log(f"자동 캐시 정리 실패: {exc}")

    def clear_cache_ui(self, kind):
        if QMessageBox.question(self, "캐시 삭제", f"{kind} 캐시를 삭제할까요?") != QMessageBox.Yes:
            return
        try:
            removed = clear_cache(config.CACHE_DIR, kind)
            self.log(f"캐시 삭제: {removed}개")
            self._refresh_cache_info()
        except Exception as exc:
            QMessageBox.critical(self, "삭제 실패", str(exc))

    def _refresh_cache_info(self):
        stats = cache_stats(config.CACHE_DIR)
        mb = stats["bytes"] / (1024 * 1024)
        dominant = self._dominant_cache_group_summary(stats)
        dominant_text = f" · 최대 {dominant}" if dominant else ""
        self.cache_label.setText(f"캐시 {stats['files']}개 / {mb:.1f} MB{dominant_text}")
        if hasattr(self, "cache_detail"):
            runtime = state.normalize_runtime_settings(self.settings)
            ttl_hours = self.search_cache_hours_spin.value() if hasattr(self, "search_cache_hours_spin") else runtime["search_cache_hours"]
            result_scan = self.result_scan_limit_spin.value() if hasattr(self, "result_scan_limit_spin") else runtime["result_scan_limit"]
            body_scan = (
                self.result_body_scan_limit_spin.value()
                if hasattr(self, "result_body_scan_limit_spin")
                else runtime["result_body_scan_limit"]
            )
            front_scan = (
                self.result_front_text_scan_limit_spin.value()
                if hasattr(self, "result_front_text_scan_limit_spin")
                else runtime["result_front_text_scan_limit"]
            )
            self.cache_detail.setText(
                f"캐시 위치: {config.CACHE_DIR}\n"
                f"파일: {stats['files']}개\n"
                f"크기: {mb:.1f} MB\n"
                f"구성: {self._cache_group_summary(stats)}\n"
                f"검색 캐시 유효: {ttl_hours:g}시간\n"
                f"발행실적 확인: 전체 {result_scan}건 / 본문 {body_scan}건 / PDF {front_scan}건"
            )

    def _cache_group_summary(self, stats):
        labels = {
            "search": "검색",
            "document": "문서",
            "pdf": "PDF",
            "other": "기타",
        }
        parts = []
        for key in ("search", "document", "pdf", "other"):
            group = (stats.get("groups") or {}).get(key) or {}
            files = int(group.get("files") or 0)
            size_mb = float(group.get("bytes") or 0) / (1024 * 1024)
            if files or size_mb:
                parts.append(f"{labels[key]} {files}개/{size_mb:.1f} MB")
        return " · ".join(parts) if parts else "없음"

    def _dominant_cache_group_summary(self, stats):
        labels = {
            "search": "검색",
            "document": "문서",
            "pdf": "PDF",
            "other": "기타",
        }
        groups = stats.get("groups") or {}
        best_key = ""
        best_group = {}
        best_bytes = -1
        for key, group in groups.items():
            size = int((group or {}).get("bytes") or 0)
            if size > best_bytes:
                best_key = key
                best_group = group or {}
                best_bytes = size
        if best_bytes <= 0:
            return ""
        files = int(best_group.get("files") or 0)
        size_mb = best_bytes / (1024 * 1024)
        return f"{labels.get(best_key, best_key)} {files}개 {size_mb:.1f} MB"

    def log(self, message):
        stamp = dt.datetime.now().strftime("%H:%M:%S")
        self.log_text.append(f"[{stamp}] {message}")

    def _open_selected_artifact(self):
        record = self.selected_record()
        if not record:
            return
        self.open_path(record.get("file") or record.get("result_file") or record.get("folder"))

    def _open_selected_file(self):
        record = self.selected_record()
        if record:
            self.open_path(record.get("file") or record.get("result_file"))

    def _open_selected_folder(self):
        record = self.selected_record()
        if record:
            self.open_path(record.get("folder"))

    def open_path(self, path):
        if not path:
            return
        path = str(path)
        if path.startswith("http://") or path.startswith("https://"):
            QDesktopServices.openUrl(QUrl(path))
        elif Path(path).exists():
            os.startfile(path)


def main():
    configure_qt_environment()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("DART Termsheet Desk")
    app.setStyleSheet(app_stylesheet())
    app.setFont(QFont("Malgun Gothic", 10))
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

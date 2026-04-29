# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> Behavioral guidelines (Think Before Coding / Simplicity / Surgical Changes / Goal-Driven Execution) live in `AGENTS.md`. Read that first. This file describes architecture and commands only.

## Project purpose

Desktop utility for KAP 파생상품평가본부 구조화평가팀 daily termsheet operations. Given Korean derivative bond/note tickers (e.g. `KR6HN0008746  하나증권(DLB)2681`), the app finds the matching **termsheet PDF** on DART (금융감독원 전자공시시스템) and saves it under
`\\10.10.10.11\파생상품평가본부\B.구조화평가팀\2_Term Sheet 모음\금리구조화채권\{종목코드}\`.
A secondary action verifies issuance status via 증권발행실적보고서.

`state/<YYYYMMDD>.json` is the daily searched-stock log; it auto-resets by date and drives the "발행취소 확인" review and per-stock popup.

## Top-level entry points

| Launcher | UI | Notes |
|---|---|---|
| `python dart_auto.py` | Tkinter (legacy) | Backward-compatible shim — `import dart_auto` returns `dart_app.legacy` so existing tests/tools can still patch module globals like `CACHE_DIR`, `SETTINGS_PATH`. |
| `python dart_qt.py` *or* `python -m dart_app.qt_app` | PySide6 | Newer Qt surface with `QMainWindow` + `QTableView` + worker `QRunnable`s. |

Both UIs share the same domain/services/integrations layer. Picking a UI does not change DART or OpenDART behavior.

## Package layout

```
dart_app/
├── config.py            # Resource paths, design tokens, runtime defaults & presets, DEFAULT_ISSUERS dict (~90 entries)
├── runtime.py           # JSON load/save, save_root normalization, settings coercion, cache helpers (read/write/clear/stats)
├── state.py             # User-facing settings/issuers/state APIs built on runtime.py
├── legacy.py            # Re-exports + thin wrappers; preserves the dart_auto module surface tests/tools depend on
├── models.py            # @dataclass DTOs: DocumentCandidateScore, TermsheetMatchResult, ResultReportMatch, ResultAnalysis, ResultAmount
├── domain/
│   ├── input_parser.py      # parse_input_lines: pair (종목코드, 종목명) lines
│   ├── security_name.py     # find_issuer (longest-prefix), extract_round, extract_product_type, round_in/round_in_exact
│   ├── document_matching.py # 3-stage termsheet matcher + result-report matcher (see below)
│   ├── result_analysis.py   # 발행취소 vs 발행됨 classifier from extracted text
│   └── structured_bond.py   # Optional CouponCheck DB row normalization
├── integrations/
│   ├── dart_web.py          # Unofficial DART web scraper: detailSearch.ax / dsaf001 / pdf.do — global rate-limit lock, circuit breaker, on-disk caches under cache/dart_*
│   └── opendart.py          # Official OpenDART API client (corp_code zip, document text fallback). Optional; gated by OPENDART_API_KEY.
├── services/
│   ├── document_access.py   # DartDocumentAccess: per-record memo cache around index_html / doc_info / pdf_for / front_text / document_text
│   ├── record_workflow.py   # RecordWorkflow: UI-neutral pipeline that drives one record end-to-end and emits update callbacks
│   ├── http_guard.py        # Shared retry/backoff helpers
│   └── structured_bond_db.py # CouponCheck SQL Server fallback (best-effort, optional)
├── ui/                  # Tkinter app + dialogs (legacy)
├── qt_app/              # PySide6 app (theme.py, models.py with QAbstractTableModel, app.py with worker QRunnables)
└── utils/               # files (safe path/filename, output_pdf_path, unique_path), pdf (text extraction via pdfplumber/pdfminer.six), text (clean_text/html_body_text)
```

`dart_auto.py` itself is a one-line shim that swaps `sys.modules['dart_auto']` for `dart_app.legacy`. Anything new should live in the `dart_app` package; only edit `legacy.py` when something genuinely needs to remain on the historical `dart_auto` surface.

## Termsheet matching — 3-tier fallback

DART search results carry **generic titles** like `일괄신고추가서류(기타파생결합사채)` — 회차 is usually missing. `find_termsheet_document` escalates:

1. **Title match** — filter by product-specific keywords (`termsheet_keywords`): DLB/ELB → `기타파생결합사채`; DLS/ELS → `기타파생결합증권`; SUB(신종) → `신종자본증권`. If the round number appears in the title, accept.
2. **Index HTML match** — fetch each candidate's `dsaf001/main.do` page (~100 KB) and parse document titles from the `tree.add(...)` JS calls. 회차 often lives there.
3. **PDF body scan (last resort)** — download up to `PDF_SCAN_LIMIT` candidate PDFs and OCR-free text-extract the first 5 pages; search those for the round number.

`find_result_report_document` follows the same shape with `RESULT_SCAN_LIMIT` for 증권발행실적보고서.

**Invariants — do not break:**
- Never fall back to "most recent candidate" when round doesn't match. The user explicitly rejected this; it produced silently-wrong files.
- Product type from stock-name parenthesis (`(DLB)`, `(DLS)`, `(신종)`, `(후…)`) strictly filters report keywords. Crossing DLB↔DLS is a known bug source.
- `round_in()` strips commas inside digits (`제2,681회` matches `2681`) and allows base match when full (`280-1`) fails, but requires non-digit boundaries (so `280` does not match `2800`).
- Longest `find_issuer` prefix wins — `미래에셋캐피탈` must match before `미래에셋`. Unmatched prefixes fall back to auto-extracting `[A-Za-z가-힣]+` from the stock name.

## DART access strategy

- **`Dart` (`integrations/dart_web.py`)** is unofficial web scraping, not an API. HTML structure changes break parsing. Primary regex risks: `openReportViewer\('(\d{14})'[^>]*>([^<]+)<` for search results, `'(\d{8})'` for `dcmNo` in the index page.
- A class-level lock + min-interval throttle + circuit breaker protects the whole process from being flagged. Don't bypass `_paced_session_request`.
- **`OpenDart` (`integrations/opendart.py`)** is the official API and is gated by `OPENDART_API_KEY` / `OPEN_DART_API_KEY` / `DART_API_KEY` (env vars or `.env` next to the exe). When enabled, `DartDocumentAccess.document_text` provides clean document text used as an extra matching signal. Always optional — features must degrade gracefully when the key is absent.
- Disk caches live under `cache/`: `dart_search/`, `dart_index/`, `dart_pdf/`, `dart_viewer/`, `opendart/search/`, `opendart/document/`. `clear_cache(kind)` honors `search` / `pdf` / `document` / `all` and refuses to delete outside the cache root.

## Resource paths (PyInstaller-aware)

```python
if getattr(sys, "frozen", False):
    BUNDLE_DIR = Path(sys._MEIPASS)          # bundled read-only resources
    APP_DIR    = Path(sys.executable).parent # user-writable, next to the exe
else:
    APP_DIR    = Path(__file__).resolve().parents[1]
    BUNDLE_DIR = APP_DIR
```

`kap_logo.png` and `dart_icon.ico` are bundled. `issuers.json`, `settings.json`, `state/`, `cache/` sit next to the exe (user-writable).

## Common commands

Working directory: `C:\Devs\Dart\cathyleee02-prog-minus-clone`. Python 3 via the `py` launcher on Windows.

```powershell
# Install deps
python -m pip install -r requirements.txt

# Run from source
python dart_auto.py            # Tkinter UI
python dart_qt.py              # PySide6 UI
python -m dart_app.qt_app      # equivalent to dart_qt.py

# Syntax check
python -B -m py_compile dart_auto.py dart_qt.py

# Unit tests (uses unittest, not pytest)
python -B -m unittest discover -s tests
python -B -m unittest tests.test_matching          # one module
python -B -m unittest tests.test_matching.MatchTermsheetTests.test_round_match  # one test (adjust class/method)

# Live DART end-to-end (writes to e2e_output/)
python -B tools/e2e_check.py
python -B tools/qt_live_check.py --status-only
python -B tools/qt_live_check.py --limit 1 --output-dir .\e2e_output\qt_live_opendart
```

### PyInstaller build

Korean characters in paths historically broke PyInstaller's path decoding. Build from a non-Korean directory:

```powershell
mkdir C:\temp\dart_build
cp dart_auto.py kap_logo.png dart_icon.ico C:\temp\dart_build\
cp -Recurse dart_app C:\temp\dart_build\
cd C:\temp\dart_build
py -m PyInstaller --onefile --windowed --noconfirm `
   --icon dart_icon.ico --name "DART_텀싯다운로더" `
   --add-data "kap_logo.png;." --hidden-import dart_app `
   dart_auto.py
# copy dist\DART_텀싯다운로더.exe back into the project root
```

`rcedit` cannot retarget a PyInstaller `--onefile` exe — it corrupts the bundled Python runtime. To change the icon, rebuild from source with `--icon`.

## Runtime settings & presets

`config.DEFAULT_RUNTIME_SETTINGS` and `config.RUNTIME_PRESETS` (`빠른 모드` / `균형 모드` / `정밀 모드` / `안전 모드`) drive scan limits, retry/backoff, http min-interval, circuit breaker, search-cache TTL, and toggles like `auto_result`, `force_refresh`, `save_termsheet_pdf`, `save_result_pdf`, `use_opendart`. `runtime.normalize_runtime_settings()` is the single coercion path — both UIs route through it. Per-UI `apply_runtime_settings` then mirrors the values into module globals (`config.SEARCH_DAYS` etc.) and into `dart_app.domain.document_matching.{INDEX,PDF,RESULT}_SCAN_LIMIT`.

## Tests

- `tests/test_matching.py` — domain-level coverage for parsing, matching, candidate scoring, result analysis. The bulk of the suite.
- `tests/test_record_workflow.py` — `RecordWorkflow` orchestration with mocked clients and document access.
- `tests/test_qt_app.py` — Qt smoke tests run against `QT_QPA_PLATFORM=offscreen`. The test file sets the env var on import; do not change that.

Mock HTTP and PDF inputs in unit tests; reserve real DART access for the `tools/*_check.py` scripts. The project uses `unittest` (not pytest) — keep new tests in that style.

## Visual design direction

Active redesign target: warm cream + coral accent + dark navy "evidence" surfaces (Claude.com-inspired). Tokens live in `dart_app/qt_app/theme.py` (Qt) and the legacy `BG/PANEL/ACCENT/...` constants in `dart_app/config.py` (Tkinter). Full plan, palette, and phase-by-phase work is in `DESIGN.md`. Keep coral scarce — only one primary action coral per visible area.

## Pitfalls

- **DART HTML drift breaks parsing.** When live searches start failing, run the in-app `DART 상태 확인` first; it pings the main page and search endpoint independently.
- **Windowed exe swallows stack traces.** The release exe is `--windowed` (no console). Wrap suspect CLI runs in a `.bat` with `pause` when debugging.
- **`dart_auto` import surface is load-bearing.** Tests, `tools/e2e_check.py`, and any user scripts patch module-level globals on `dart_auto`. When moving code into `dart_app/*`, re-export through `dart_app/legacy.py` so the surface stays intact.
- **OpenDART rate limits.** OpenDART caps at ~10k requests/day per key; cache aggressively (`cache/opendart/document/`) and prefer the unofficial path for bulk metadata.
- **Cache deletion is path-guarded.** `runtime._safe_rmtree` refuses targets outside the cache root — preserve that check on any cache-management edits.

## Supporting files

- `issuers.json` — lazily created next to the exe when the user edits issuer mappings via the GUI; only diffs-from-default persisted. Absent until first edit.
- `settings.json` — lazily created when the user saves runtime settings or save root.
- `state/<YYYYMMDD>.json` — today's searched-stock log; auto-resets by date.
- `kap_logo.png` — 242×54 logo with white background removed via PIL (alpha=0 for RGB > 235). Bundled.
- `dart_icon.ico` — DART brand icon converted from gif. Bundled via `--icon`.
- `.env` (untracked) — optional `OPENDART_API_KEY=...`. Searched at `APP_DIR/.env`, `APP_DIR.parent/.env`, CWD `.env`.

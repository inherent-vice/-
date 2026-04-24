# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Behavioral guidelines (Karpathy)

Bias toward caution over speed. For trivial edits, use judgment.

**Think before coding.** State assumptions explicitly. If multiple interpretations exist, present them — don't pick silently. If a simpler approach exists, say so. When unclear, stop and ask.

**Simplicity first.** Write the minimum code that solves the problem. No speculative features. No abstractions for single-use code. No configurability that wasn't requested. No error handling for impossible scenarios. If 200 lines could be 50, rewrite.

**Surgical changes.** Touch only what the request requires. Don't "improve" adjacent code, comments, or formatting. Don't refactor things that aren't broken. Match existing style. Mention unrelated dead code — don't delete it unless asked. Remove imports/variables only when *your* changes orphaned them. Every changed line should trace directly to the user's request.

**Goal-driven execution.** Define verifiable success criteria before starting.
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
```

## Project purpose

Desktop GUI utility for the KAP 파생상품평가본부. The user inputs Korean derivative bond/note tickers (e.g., `KR6HN0008746  하나증권(DLB)2681`), and the app locates the matching **termsheet PDF** on DART (금융감독원 전자공시시스템). By default it saves under `\\10.10.10.11\파생상품평가본부\B.구조화평가팀\2_Term Sheet 모음\금리구조화채권\{종목코드}\`, and the main window can override/persist that root in `settings.json`. Secondary button verifies issuance status (발행취소 vs 발행됨) via 증권발행실적보고서.

Daily-use tool: `state/YYYYMMDD.json` records what was searched today and auto-resets by date.

## Architecture

The entire app is a single file (`dart_auto.py`, ~1000 lines). Key units:

| Section | Role |
|---|---|
| `DEFAULT_ISSUERS` dict | Built-in prefix→company map (78 entries). User overrides in `issuers.json` merged on top via `load_issuers()`. |
| `Dart` class | Unofficial DART web scraper — **does not use opendart.fss.or.kr API**. Three endpoints: `dsab007/detailSearch.ax` (search by company name), `dsaf001/main.do` (index page → dcmNo + document titles), `pdf/download/pdf.do` (final PDF). |
| `extract_*` / `find_issuer` / `round_in` | Pure parsing helpers. Input like `하나증권(DLB)2681` → issuer `하나증권`, product `DLB`, round `(full=2681, base=2681)`. |
| `match_termsheet` | 3-stage matching pipeline (see below). |
| `App` (Tk root) | Main window — pastel theme, KAP logo, input textarea, result popup. |
| `IssuerEditor` | Toplevel dialog for editing issuer mappings at runtime. Saves only diffs-from-default to `issuers.json`. |

### Termsheet matching — 3-tier fallback

DART search results only contain **generic titles** like `일괄신고추가서류(기타파생결합사채)` — 회차 is usually not in the title. The matching logic escalates:

1. **Title match** — filter candidates by report-type keywords specific to product type (DLB/ELB → `기타파생결합사채`; DLS/ELS → `기타파생결합증권`; SUB=신종 → `신종자본증권`). Then check if round number appears in title.
2. **Index HTML match** — if title match fails, fetch each candidate's `dsaf001/main.do` page (cheap, ~100KB) and extract document titles from the `tree.add(...)` JS calls. 회차 often lives there.
3. **PDF body scan (last resort)** — download up to `PDF_SCAN_LIMIT` candidate PDFs and extract the first 5 pages; search those for the round number.

Only the matched PDF is kept. Candidates fetched in stages 2–3 are discarded.

**Important invariants:**
- Never fallback to "most recent candidate" when round doesn't match — the user explicitly rejected this (yielded silently-wrong files).
- Product type from stock-name parenthesis (`(DLB)`, `(DLS)`, `(신종)`, `(후…)`) strictly filters report keywords — crossing DLB↔DLS is a known bug source.
- `round_in()` strips commas inside digits (`제2,681회` matches `2681`) and allows base match when full (`280-1`) fails, but requires non-digit boundaries to avoid `280` matching `2800`.
- Longest `find_issuer` prefix wins — `미래에셋캐피탈` must match before `미래에셋`. Unmatched prefixes fall back to auto-extracting `[A-Za-z가-힣]+` from the stock name.

### Resource paths (PyInstaller aware)

```python
if getattr(sys, "frozen", False):
    BUNDLE_DIR = Path(sys._MEIPASS)          # bundled read-only resources
    APP_DIR    = Path(sys.executable).parent # writable user data next to exe
else:
    BUNDLE_DIR = APP_DIR = Path(__file__).parent
```

`kap_logo.png` is bundled (read-only). `issuers.json`, `settings.json`, and `state/` sit next to the exe (user-writable).

## Common commands

**Run from source** (Windows, Python 3.14 via `py` launcher):
```bash
cd C:\Devs\신규
py dart_auto.py
```

**Install dependencies:**
```bash
python -m pip install -r requirements.txt
```

**Rebuild the exe.** Korean path `C:\Devs\신규` breaks PyInstaller's path decoding, so **always build from a non-Korean directory**:
```
mkdir C:\temp\dart_build
cp dart_auto.py kap_logo.png dart_icon.ico C:\temp\dart_build\
cd C:\temp\dart_build
py -m PyInstaller --onefile --windowed --noconfirm \
   --icon dart_icon.ico \
   --name "DART_텀싯다운로더" \
   --add-data "kap_logo.png;." \
   dart_auto.py
# then copy dist\DART_텀싯다운로더.exe back into C:\Devs\신규\
```

**Syntax check:**
```
python -B -c "src=open('dart_auto.py', encoding='utf-8').read(); compile(src, 'dart_auto.py', 'exec')"
```

**Unit tests:**
```
python -B -m unittest discover -s tests
```

**Real DART end-to-end check:**
```
python -B tools/e2e_check.py
```

Unit tests cover core parsing and matching helpers. Manual verification is still required for the GUI and live DART downloads. In the GUI, use `DART 상태 확인` first when searches fail; it checks the DART main page and search endpoint separately.

## Known pitfalls

- **DART is unofficial web-scraping, not an API.** HTML structure changes break parsing. Primary regex risks: `openReportViewer\('(\d{14})'[^>]*>([^<]+)<` for search results, `'(\d{8})'` for dcmNo in index page.
- **rcedit cannot retarget PyInstaller onefile exes** — it corrupts the bundled Python runtime (truncates file from MB to KB). To change an exe's icon, rebuild from source with `--icon`.
- **Korean paths + PyInstaller** — see build command above.
- **Windows console windows close instantly on exception.** The GUI exe is `--windowed` (no console) — wrap suspect CLI runs in a `.bat` with `pause` when debugging.

## Supporting files

- `issuers.json` — lazily created next to the exe when the user edits issuer mappings via the GUI; only diffs-from-default persisted. Absent until first edit.
- `settings.json` — lazily created next to the exe when the user saves the main-window save root. Default root is the shared `금리구조화채권` folder.
- `state/<YYYYMMDD>.json` — today's searched-stock log; drives the "② 발행취소 확인" and per-stock popup. Auto-resets by date.
- `kap_logo.png` — 242×54 logo with white background removed via PIL (set alpha=0 for RGB>235). Bundled into the exe.
- `dart_icon.ico` — DART brand logo converted from gif for taskbar/exe icon. Bundled via `--icon`.

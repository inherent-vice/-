# Repository Guidelines

## Operating Rules

These rules are meant to keep Codex/Claude work small, verifiable, and aligned
with the current repository shape.

- Inspect the codebase and this file before editing.
- Choose the smallest reasonable path when a choice is low-risk; ask only when
  the choice changes behavior, data, credentials, or deployment.
- Touch only files needed for the requested task. Do not clean adjacent code or
  generated output opportunistically.
- Preserve user changes in dirty worktrees. Do not revert unrelated edits.
- Keep Korean UI/report strings readable UTF-8 text.
- Define the verification command before changing behavior, then run the focused
  tests or smoke checks that prove the change.

## Canonical Root

The Git repository is:

```text
C:\Devs\Dart\cathyleee02-prog-minus-clone
```

`C:\Devs\Dart` is a workspace folder, not a Git repo. Treat files directly under
that folder as scratch inputs or generated analysis artifacts unless a task
explicitly says otherwise.

## Project Purpose

This is a Python desktop utility for KAP structured-product daily operations.
Given Korean derivative bond/note tickers, it finds matching DART termsheet PDFs
and optionally verifies issuance status via `증권발행실적보고서`.

## Entry Points

- `python dart_qt.py`: launch the PySide6 UI. This is the newer UI surface.
- `python -m dart_app.qt_app`: equivalent Qt launcher.
- `python dart_auto.py`: launch the legacy Tkinter UI and preserve the old
  `dart_auto` import surface.

Do not put new application behavior into `dart_auto.py`; it is only a
compatibility shim.

## Module Map

- `dart_app/domain/`: parsing, issuer/round/product extraction, document
  matching, result analysis. Keep business rules here.
- `dart_app/integrations/`: DART web scraper and optional OpenDART API client.
  Do not bypass DART pacing/circuit-breaker code.
- `dart_app/services/`: UI-neutral seams such as `RecordWorkflow` and
  `DartDocumentAccess`.
- `dart_app/ui/`: legacy Tkinter adapter.
- `dart_app/qt_app/`: PySide6 adapter, table model, and theme.
- `dart_app/runtime.py`, `state.py`, `config.py`: runtime JSON, settings,
  cache, resources, and defaults.
- `dart_app/legacy.py`: compatibility adapter for tests/tools/user scripts that
  still import and patch `dart_auto`.
- `tests/`: `unittest` tests. Keep new tests in this style.
- `tools/`: live or app-like smoke checks that may hit DART.

For domain vocabulary and invariants, read `CONTEXT.md`. For UI visual direction,
read `DESIGN.md`.

## Build, Test, And Development Commands

- `python -m pip install -r requirements.txt`
- `python -B -m py_compile dart_auto.py dart_qt.py`
- `python -B -m unittest discover -s tests`
- `python dart_qt.py`
- `python dart_auto.py`
- `python -B tools/e2e_check.py`
- `python -B tools/qt_live_check.py --status-only`

Live checks write to `e2e_output/` and may use network/API quota. Prefer unit
tests unless the user asks for live validation or the bug is network-dependent.

## Non-Negotiable DART Rules

- Never fall back to the most recent DART document when round/product evidence
  does not match.
- Preserve product filtering: DLB/ELB, DLS/ELS, and SUB/후순위 must not cross.
- Preserve longest-prefix issuer matching.
- Keep `%PDF-` validation before caching/downstream parsing PDF bytes.
- Keep `RESULT_SCAN_LIMIT` separate from `PDF_SCAN_LIMIT`.
- `force_refresh` increases DART/OpenDART request volume; live validation must
  mirror the real worker path when diagnosing speed or rate-limit behavior.

## Runtime Files

Keep these untracked:

- `cache/`
- `state/`
- `settings.json`
- `issuers.json`
- `.env`
- `e2e_output/`
- `.ruff_cache/`
- `__pycache__/`

Do not commit API keys, downloaded PDFs, local settings, or production extracts.

## Commit And PR Notes

Use concise Conventional Commit prefixes such as `feat:`, `fix:`, `docs:`,
`test:`, or `chore:`. PRs should describe user-visible behavior and list exact
verification commands.

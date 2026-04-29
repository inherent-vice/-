# DART Domain Context

This file names the domain concepts and invariants future agents should preserve.

## Core Concepts

- **Record**: one `(stock_code, stock_name)` pair from pasted text or an input
  file.
- **Issuer mapping**: prefix-based mapping from a Korean stock name to a DART
  company search name. Longest prefix wins.
- **Round**: issuance round parsed from `stock_name`, including forms like
  `2681`, `280-1`, and comma-formatted Korean text in DART documents.
- **Product type**: parsed product family such as `DLB`, `ELB`, `DLS`, `ELS`, or
  `SUB`/후순위.
- **Termsheet candidate**: a DART search result that may contain the official
  termsheet. Generic DART titles often omit the round, so candidate evidence can
  come from title, index HTML, OpenDART document text, viewer text, or PDF text.
- **Issuance-result candidate**: a DART result report candidate for
  `증권발행실적보고서`, used to classify issued/cancelled/unknown state.
- **Document evidence**: structured candidate rows shown in the UI explaining why
  a candidate was accepted or rejected.

## Important Seams

- `RecordWorkflow` in `dart_app/services/record_workflow.py` owns the UI-neutral
  per-record pipeline. Prefer changing this seam for workflow behavior instead
  of duplicating logic in Tkinter or Qt.
- `DartDocumentAccess` in `dart_app/services/document_access.py` owns per-run
  document memoization for index HTML, doc info, PDF bytes, viewer text, and
  OpenDART text.
- `Dart` in `dart_app/integrations/dart_web.py` owns unofficial DART scraping,
  disk cache, pacing, retries, and circuit breaker behavior.
- `OpenDart` in `dart_app/integrations/opendart.py` is optional and must degrade
  cleanly when no API key is available.
- `dart_app/legacy.py` is an adapter for old `dart_auto` imports. Keep it thin.

## Matching Invariants

- Do not select the most recent document without round/product evidence.
- Product families must not cross: DLB/ELB, DLS/ELS, and SUB/후순위 have distinct
  termsheet/report title evidence.
- Round matching must avoid partial digit matches: `280` must not match `2800`.
- `round_in()` may strip commas inside digits and may use base round fallback for
  split rounds such as `280-1` only when the evidence is bounded.
- Candidate evidence should explain the source: title, index, body, identifier,
  PDF fallback, or rejection reason.
- Invalid PDF bytes must not be cached as successful PDFs.

## Runtime Invariants

- `settings.json`, `issuers.json`, `state/`, `cache/`, `.env`, and
  `e2e_output/` are local runtime files and stay untracked.
- Cache deletion must stay path-guarded under the configured cache root.
- `RESULT_SCAN_LIMIT` is separate from `PDF_SCAN_LIMIT`.
- `force_refresh=True` bypasses persistent caches for first requests and can
  amplify live DART/OpenDART traffic.

## UI Adapters

- Qt (`dart_app/qt_app/`) and Tkinter (`dart_app/ui/`) should share domain,
  integration, service, runtime, and state modules.
- UI code may format labels, tables, dialogs, and file-opening behavior, but it
  should not reimplement candidate matching or DART access.

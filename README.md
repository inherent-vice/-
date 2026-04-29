# DART Termsheet Desk

Desktop utility for KAP structured-product operations. It reads stock-code/name
pairs, searches DART for matching termsheet PDFs, saves results by stock code,
and can verify issuance status through `증권발행실적보고서`.

## Start Here

```powershell
cd C:\Devs\Dart\cathyleee02-prog-minus-clone
python -m pip install -r requirements.txt
python dart_qt.py
```

Legacy Tkinter is still available with:

```powershell
python dart_auto.py
```

## Repository Map

- `dart_qt.py`: PySide6 launcher.
- `dart_auto.py`: legacy compatibility shim.
- `dart_app/domain/`: parsing, issuer matching, DART candidate scoring, result
  analysis.
- `dart_app/integrations/`: DART web and OpenDART clients.
- `dart_app/services/`: UI-neutral workflow and document access seams.
- `dart_app/qt_app/`: current Qt UI.
- `dart_app/ui/`: legacy Tkinter UI.
- `tests/`: unit tests.
- `tools/`: live/app-like smoke checks.

Read `AGENTS.md` before editing and `CONTEXT.md` for domain invariants.

## Verification

```powershell
python -B -m py_compile dart_auto.py dart_qt.py
python -B -m unittest discover -s tests
```

Live checks:

```powershell
python -B tools/qt_live_check.py --status-only
python -B tools/e2e_check.py
```

Live checks may hit DART/OpenDART and write to `e2e_output/`.

## Runtime State

The app stores local state next to the source checkout or executable:

- `settings.json`
- `issuers.json`
- `state/<YYYYMMDD>.json`
- `cache/`
- `e2e_output/`

These are intentionally untracked.

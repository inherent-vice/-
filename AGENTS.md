# Repository Guidelines

## Project Structure & Module Organization

This repository is a compact Windows desktop utility for downloading DART termsheet and issuance-result PDFs. The main application lives in `dart_auto.py`; keep source changes there unless a requested change clearly needs a new module. Static GUI assets are `kap_logo.png` and `dart_icon.ico`. Tests live under `tests/`. Runtime user data is intentionally untracked: `issuers.json` stores user issuer overrides, `settings.json` stores the save root, and `state/YYYYMMDD.json` stores daily search history. Downloads are saved under the configured root using the stock code as a folder name, for example `...\금리구조화채권\KR6MZ0005MV0\...pdf`.

## Build, Test, and Development Commands

- `python dart_auto.py`: run the Tkinter GUI locally.
- `python -B -c "src=open('dart_auto.py', encoding='utf-8').read(); compile(src, 'dart_auto.py', 'exec')"`: syntax-check without writing `.pyc` files.
- `python -B -m unittest discover -s tests`: run the unit tests.
- `python -B tools/e2e_check.py`: run the real DART end-to-end check for the Meritz DLB sample.
- `python -m pip install requests pdfplumber pyinstaller`: install expected runtime/build dependencies.
- Build from a non-Korean path, then copy the artifacts and run:

```powershell
python -m PyInstaller --onefile --windowed --noconfirm `
  --icon dart_icon.ico `
  --name "DART_텀싯다운로더" `
  --add-data "kap_logo.png;." `
  dart_auto.py
```

## Coding Style & Naming Conventions

Use Python 3, 4-space indentation, and UTF-8 source text. Follow the existing procedural style: small parsing helpers at module level, DART networking in `Dart`, GUI behavior in `App` and `IssuerEditor`. Prefer explicit names such as `round_full`, `round_base`, `stock_name`, and `issuer`. Keep Korean UI strings readable and do not convert them to escaped text.

## Testing Guidelines

For logic changes, add focused tests for pure helpers such as `extract_round()`, `find_issuer()`, `round_in()`, `match_termsheet()`, and `match_result()`. Name tests `test_<function>_<case>.py` under `tests/`. Manual verification should include at least one DLB/ELB case, one DLS/ELS case, and one 신종/후순위 case.

## Commit & Pull Request Guidelines

The current history uses a simple Conventional Commit style, for example `chore: initial commit — DART termsheet downloader GUI`. Continue with concise prefixes such as `fix:`, `feat:`, `docs:`, and `chore:`. Pull requests should explain the user-facing behavior, list manual verification steps, and include screenshots when GUI layout changes.

## Security & Configuration Tips

This app scrapes DART web pages rather than using the OpenDART API, so HTML changes can break regex parsing. Never fall back to the most recent document unless the requested round is verified. Do not commit downloaded PDFs, `issuers.json`, `state/`, build output, or local editor settings.
Use the GUI's `DART 상태 확인` button before debugging matching logic when searches fail.

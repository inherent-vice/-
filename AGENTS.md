# Repository Guidelines

## Agent Behavioral Guidelines (Karpathy-Inspired)

Based on `forrestchang/andrej-karpathy-skills`. These rules are meant to reduce common LLM coding mistakes. They bias toward caution over speed; use judgment for trivial one-line edits.

### 1. Think Before Coding

Do not assume, hide confusion, or silently choose between plausible interpretations.

- State assumptions explicitly before implementing.
- If multiple interpretations exist, present them and ask when the choice matters.
- If a simpler approach exists, say so and explain the tradeoff.
- If something is unclear, stop, name the ambiguity, and ask.

### 2. Simplicity First

Write the minimum code that solves the requested problem.

- Do not add features beyond what was asked.
- Do not add abstractions for single-use code.
- Do not add configurability that was not requested.
- Do not add error handling for impossible scenarios.
- If a solution is growing from 50 lines to 200 lines, simplify before continuing.

### 3. Surgical Changes

Touch only what the request requires and clean up only the side effects of your own changes.

- Do not improve adjacent code, comments, or formatting opportunistically.
- Do not refactor code that is not broken.
- Match existing style, even if you would normally choose another style.
- Mention unrelated dead code or cleanup opportunities; do not delete them unless asked.
- Remove imports, variables, or functions only when your change made them unused.

Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

Define verifiable success criteria and loop until they are met.

- For validation work, write or identify invalid-input checks, then make them pass.
- For bug fixes, reproduce the bug with a test or focused check, then fix it.
- For refactors, verify behavior before and after the change when practical.

For multi-step tasks, state a short plan with checks:

```text
1. [Step] -> verify: [check]
2. [Step] -> verify: [check]
3. [Step] -> verify: [check]
```

## Project Structure & Module Organization

This is a Python/Tkinter desktop utility for finding and downloading DART termsheet and issuance-result PDFs. `dart_auto.py` is a backward-compatible entry point; application code lives in `dart_app/`. Keep business logic in `dart_app/domain/`, DART and OpenDART clients in `dart_app/integrations/`, GUI code in `dart_app/ui/`, reusable file/PDF/text helpers in `dart_app/utils/`, and settings/state helpers in `dart_app/state.py`, `config.py`, and `runtime.py`. Unit tests are in `tests/`, with the current suite in `tests/test_matching.py`. Real-network verification lives in `tools/e2e_check.py`. Root assets include `kap_logo.png` and `dart_icon.ico`. Runtime output such as `cache/`, `state/`, `settings.json`, `issuers.json`, and `e2e_output/` should stay untracked.

## Build, Test, and Development Commands

- `python -m pip install -r requirements.txt`: install runtime and packaging dependencies.
- `python dart_auto.py`: launch the local Tkinter app.
- `python -B -m unittest discover -s tests`: run unit tests without writing `.pyc` files.
- `python -B tools/e2e_check.py`: run the DART end-to-end check and write sample downloads to `e2e_output/`.
- `python -m PyInstaller --onefile --windowed --icon dart_icon.ico --add-data "kap_logo.png;." dart_auto.py`: build a Windows executable.

## Coding Style & Naming Conventions

Use Python 3, 4-space indentation, UTF-8 source files, and `snake_case` for functions, variables, and modules. Use `PascalCase` for classes such as `Dart`, `OpenDart`, and `App`. Prefer small pure helpers in `dart_app/domain/`; keep Tkinter event handling and layout inside `dart_app/ui/`. Preserve the `dart_auto` compatibility surface when moving functions, because tests and tools import and patch `dart_auto` globals. Keep Korean UI/report strings readable and do not replace them with escaped text.

## Testing Guidelines

The project uses `unittest`. Name test files `test_<area>.py` and test methods `test_<behavior>`. Add focused tests for parsing, matching, result analysis, path generation, cache behavior, and settings normalization. Mock HTTP and PDF inputs in unit tests; reserve live DART access for `tools/e2e_check.py`. Run `python -B -m unittest discover -s tests` before opening a PR.

## Commit & Pull Request Guidelines

Recent history uses concise Conventional Commit prefixes, for example `feat: improve DART download workflow` and `chore: initial commit`. Continue with `feat:`, `fix:`, `docs:`, `test:`, or `chore:`. Pull requests should describe user-visible behavior, list test or e2e commands run, link related issues when available, and include screenshots for GUI layout changes.

## Security & Configuration Tips

Do not commit API keys, downloaded PDFs, cache data, or local runtime settings. Treat DART HTML as unstable: avoid broad fallback matching unless the requested product type, round, or ISIN has been verified.

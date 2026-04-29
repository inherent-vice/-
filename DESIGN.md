# DESIGN.md

This document captures the provided Claude.com-inspired warm editorial design system and translates it into a concrete UI/UX implementation plan for the DART termsheet desktop app.

## Source Style Guide

### Overview

Claude.com is the warmest, most editorial interface in the AI-product category. The base atmosphere is a tinted cream canvas (`#faf9f5`) rather than cool gray-white. The visual voice comes from a serif display face paired with a restrained humanist sans body, making the product feel like a literary publication rather than a generic SaaS surface.

The brand voltage comes from the cream and coral pairing. Coral (`#cc785c`) is the signature accent for primary CTAs, brand marks, and full-bleed callout moments. It should stay warm and muted, never cyan, blue, or saturated.

The surface system alternates between three modes:

1. Cream canvas (`#faf9f5`) as the default body floor.
2. Light cream cards (`#efe9de`) for feature and content surfaces.
3. Dark navy product surfaces (`#181715`) for code, terminal, product chrome, model cards, and footer-like closure.

The key pacing rhythm is cream to dark. Dark surfaces should show product chrome at scale, not abstract decoration.

### Core Tokens

#### Brand and Accent

| Token | Value | Use |
|---|---:|---|
| `colors.primary` | `#cc785c` | Coral primary CTA, selected action, major callout |
| `colors.primary-active` | `#a9583e` | Pressed or active coral |
| `colors.primary-disabled` | `#e6dfd8` | Disabled coral-tinted state |
| `colors.accent-teal` | `#5db8a6` | Rare active connection or success-adjacent signal |
| `colors.accent-amber` | `#e8a55a` | Rare category or inline highlight |

#### Surfaces

| Token | Value | Use |
|---|---:|---|
| `colors.canvas` | `#faf9f5` | Main app floor |
| `colors.surface-soft` | `#f5f0e8` | Soft section bands |
| `colors.surface-card` | `#efe9de` | Light cream cards and grouped controls |
| `colors.surface-cream-strong` | `#e8e0d2` | Active tab or emphasized cream area |
| `colors.surface-dark` | `#181715` | Log, product chrome, terminal-like panels |
| `colors.surface-dark-elevated` | `#252320` | Dark inner cards and status strips |
| `colors.surface-dark-soft` | `#1f1e1b` | Code or log background inside dark cards |
| `colors.hairline` | `#e6dfd8` | 1px border on cream surfaces |
| `colors.hairline-soft` | `#ebe6df` | Internal dividers |

#### Text

| Token | Value | Use |
|---|---:|---|
| `colors.ink` | `#141413` | Headlines and primary text |
| `colors.body-strong` | `#252523` | Lead and emphasized text |
| `colors.body` | `#3d3d3a` | Default text |
| `colors.muted` | `#6c6a64` | Secondary labels |
| `colors.muted-soft` | `#8e8b82` | Captions and fine print |
| `colors.on-primary` | `#ffffff` | Text on coral |
| `colors.on-dark` | `#faf9f5` | Primary text on dark |
| `colors.on-dark-soft` | `#a09d96` | Secondary text on dark |

#### Semantic

| Token | Value | Use |
|---|---:|---|
| `colors.success` | `#5db872` | Available, completed, issued |
| `colors.warning` | `#d4a017` | Needs review |
| `colors.error` | `#c64545` | Failed or blocked |

### Typography

The reference system uses Copernicus or Tiempos Headline for display, StyreneB or Inter for body, and JetBrains Mono for code. For this Windows Tkinter app, use practical local fallbacks:

| Role | Reference | Desktop App Fallback |
|---|---|---|
| Display heading | Copernicus / Tiempos Headline | Georgia, Cambria, then Malgun Gothic |
| Korean body and UI | StyreneB / Inter | Malgun Gothic, Segoe UI |
| Logs and technical evidence | JetBrains Mono | Cascadia Mono, Consolas |

Display text should be regular weight, not bold-heavy. The reference style uses negative tracking, but Tkinter support is limited; compensate with restrained size, line height, and weight.

### Shape and Spacing

| Token | Value | Use |
|---|---:|---|
| `spacing.xxs` | 4px | Tiny internal gaps |
| `spacing.xs` | 8px | Compact controls |
| `spacing.sm` | 12px | Button gaps |
| `spacing.md` | 16px | Default region spacing |
| `spacing.lg` | 24px | Tool group padding |
| `spacing.xl` | 32px | Major panel padding |
| `spacing.section` | 96px | Web section rhythm; reduce for desktop app density |
| `rounded.md` | 8px | Buttons and inputs |
| `rounded.lg` | 12px | Content panels |
| `rounded.xl` | 16px | Marquee areas |
| `rounded.pill` | 9999px | Badges |

The elevation philosophy is color-block first and shadow rare. The app should rely on cream surface contrast, dark product panels, and hairline borders rather than heavy shadowing.

### Component Principles

Primary actions use coral. Secondary actions use cream with a hairline border. Text links use coral. Feature surfaces use light cream. Operational or technical evidence surfaces use dark navy.

Cards should not become a mosaic. The DART app is an operational workspace, so panels must be dense but readable. Use cards only where they frame a real interaction: input, result table, detail evidence, log, settings group.

The Anthropic-style spike mark can be adapted as a small 4-spoke glyph in the app title or section marker, but it should not overpower the KAP/DART utility identity.

### Do's

- Anchor every screen on cream canvas, not pure white or cool gray.
- Use coral only for the main action and selected states.
- Use dark navy for logs, DART evidence, and technical product chrome.
- Keep the table readable and operational before making it decorative.
- Use generous spacing where users orient themselves, and compact spacing where they repeatedly scan rows.
- Let status, freshness, and next action be clear at a glance.

### Don'ts

- Do not keep the current purple-first palette.
- Do not turn the app into a landing page or marketing layout.
- Do not make a dashboard-card mosaic.
- Do not use saturated cyan, blue, or purple as primary accent.
- Do not use heavy shadows, gradients, or decorative blobs.
- Do not use serif display type for dense Korean table content.

## DART UI/UX Implementation Plan

### Visual Thesis

A warm editorial operations desk: cream paper-like workspace, coral action points, and dark navy evidence panels that make DART search, matching, and PDF status feel calm, inspectable, and trustworthy.

### Content Plan

The app should open directly into the working surface:

1. Top app bar: product identity, DART health summary, save-root status, and primary run action.
2. Input and controls: target list entry, mode, save options, cache policy, and issuer mapping tools.
3. Result workspace: dense record table with status badges, source confidence, and output path.
4. Evidence inspector: candidate ranking, DART document evidence, result analysis, and technical log.
5. Maintenance surfaces: settings, issuer mapping, cache, and today-state views.

### Interaction Thesis

- Progress should feel like a controlled queue: rows move from waiting to searching to matched or review-needed with stable badge colors.
- Evidence should reveal progressively: default table scan first, selected-record inspector second, raw log last.
- Destructive or expensive operations should be visibly distinct: force-refresh, cache clear, and stop should use warning/error treatment rather than coral primary treatment.

## Current UI Gap Analysis

### Palette Mismatch

Current `dart_app/config.py` uses a purple-tinted palette:

- `BG = #F5F0FA`
- `PANEL = #FFFFFF`
- `ACCENT = #B5A7E6`
- `ACCENT_DK = #8573C9`

This conflicts with the target style. The first implementation step should replace these with warm cream, coral, warm ink, and dark navy tokens while preserving old variable names where needed for compatibility.

### Typography Mismatch

The current app uses mostly default ttk fonts plus `Malgun Gothic` bold for the title. The target style needs a clearer hierarchy:

- App title: serif-like display fallback for Latin/DART part where practical, Korean-compatible regular weight for Korean.
- Operational labels: Malgun Gothic or Segoe UI, weight 500.
- Table and body: Malgun Gothic, 10-11pt.
- Log and DART evidence: Cascadia Mono or Consolas, 10pt.

### Layout Mismatch

The app already has the right operating model: left input/control rail, right table and details. The issue is visual rhythm:

- Too many controls are visually equal.
- Primary and secondary actions are not clearly separated.
- Logs and evidence are visually similar to inputs, although they represent product chrome.
- Table status is text-heavy instead of badge-like.

### Component Mismatch

The current UI relies on default ttk styling. To reach the target design, add a local theme layer rather than styling each widget ad hoc.

## Architecture Plan

### Phase 1: Token Foundation

Files:

- `dart_app/config.py`
- New optional module: `dart_app/ui/theme.py`

Work:

1. Add target design tokens:
   - `CANVAS`, `SURFACE_SOFT`, `SURFACE_CARD`, `SURFACE_DARK`, `SURFACE_DARK_ELEVATED`
   - `PRIMARY`, `PRIMARY_ACTIVE`
   - `INK`, `BODY`, `MUTED`, `ON_DARK`
   - `SUCCESS`, `WARNING`, `ERROR`
2. Keep old aliases (`BG`, `PANEL`, `INPUT_BG`, `ACCENT`, `ACCENT_DK`, `TEXT`, `MUTED`, `LOG_BG`) mapped to the new system for low-risk migration.
3. Create `apply_theme(root)` in `dart_app/ui/theme.py`.
4. Centralize ttk style names:
   - `Primary.TButton`
   - `Secondary.TButton`
   - `Danger.TButton`
   - `Cream.TFrame`
   - `Card.TLabelframe`
   - `Dark.TFrame`
   - `Muted.TLabel`
   - `Status.Treeview`

Verification:

- `python -B -m py_compile dart_auto.py dart_app\ui\theme.py`
- Launch app and check no Tcl style errors.

### Phase 2: App Shell and Hierarchy

Files:

- `dart_app/ui/app.py`
- `dart_app/ui/theme.py`

Work:

1. Replace the current title strip with a 64px warm cream app bar.
2. Use a compact mark at the far left: `✣ DART` or a small drawn spike-like glyph if Tkinter rendering is stable.
3. Put status and summary on the right as muted labels.
4. Move the strongest action into one coral button:
   - Primary: `대상 다운로드`
   - Secondary: `대상 확인`, `발행실적 갱신`
   - Tertiary/tool: `설정`, `발행사 매핑`, `오늘 작업`
5. Keep force-refresh visible but not primary. It should feel like a mode toggle with warning implications.

Verification:

- App opens at current `1420x920`.
- Top bar does not wrap at 1200px width.
- Primary action is the only coral button in the first view.

### Phase 3: Input Rail

Files:

- `dart_app/ui/app.py`

Work:

1. Convert the left rail into a warm card-like surface using `surface-card`.
2. Group controls by job:
   - Input
   - Run
   - Review
   - Tools
   - Log
3. Keep input textarea cream, not white.
4. Add a small muted helper line only where it improves operation, such as input format or active save root.
5. Make the log a dark navy product surface:
   - Background `surface-dark-soft`
   - Text `on-dark`
   - Timestamp `on-dark-soft`
   - Monospace font

Verification:

- Korean text remains readable.
- Input and log are clearly different surfaces.
- No nested-card appearance.

### Phase 4: Results Table

Files:

- `dart_app/ui/app.py`
- `dart_app/ui/theme.py`

Work:

1. Style `Treeview` as a calm operating table:
   - Cream background
   - Warm ink text
   - Soft hairline row separators if ttk supports it cleanly
   - Selected row in `surface-cream-strong`
2. Convert status wording into short badge-like values:
   - `대기`
   - `검색`
   - `저장`
   - `미발견`
   - `검토`
   - `실패`
3. Use row tags for status coloring:
   - Complete: subtle success tint
   - Review: amber tint
   - Failed: error tint
   - Running: coral text or cream-strong fill
4. Keep columns stable and scannable:
   - Target checkbox
   - Code
   - Name
   - Issuer
   - Round
   - Product
   - Status
   - Termsheet
   - Result
   - Folder

Verification:

- Row height remains dense enough for daily work.
- Long Korean names truncate cleanly without breaking layout.
- Status is readable without opening detail tabs.

### Phase 5: Evidence Inspector

Files:

- `dart_app/ui/app.py`

Work:

1. Keep the right-side notebook but make it feel like an inspector, not a generic tab stack.
2. `검증 상세`:
   - Candidate table on cream surface.
   - Evidence/reject reason visible and concise.
   - DART open action as secondary button, not primary.
3. `발행실적`:
   - Use dark navy header strip for result status.
   - Show label/confidence/reason first.
   - Raw evidence and amounts below.
4. `캐시`:
   - Keep utility layout.
   - Cache clear actions should not use coral.
   - `전체 캐시 삭제` should use warning/error styling.

Verification:

- A selected row gives enough evidence to explain why it matched or skipped.
- Result status is distinguishable from termsheet status.

### Phase 6: Dialogs

Files:

- `dart_app/ui/dialogs.py`
- `dart_app/ui/theme.py`

Work:

1. Apply the same cream canvas to settings and issuer editor.
2. Use `surface-card` for grouped settings sections.
3. Use coral only for final save/apply actions.
4. Preset buttons should become category tabs:
   - Active preset: `surface-card`
   - Inactive preset: transparent or canvas
5. Inputs should use cream background and coral focus ring where ttk allows it.

Verification:

- Dialogs feel related to the main app.
- Presets are visually understandable.
- Save/apply hierarchy is clear.

### Phase 7: Product Chrome Details

Files:

- `dart_app/ui/app.py`
- `dart_app/ui/theme.py`

Work:

1. Make DART status check output render as terminal-like log lines.
2. Consider a compact status strip:
   - OpenDART: enabled/disabled
   - Cache: file count and MB
   - Save root: short path
   - Worker mode: fast/balanced/precise/safe
3. Use teal sparingly for online/connected status.
4. Use amber for review-needed, not for generic highlights.

Verification:

- The app does not become colorful. Coral remains scarce.
- Technical evidence is easier to trust because it lives on dark product surfaces.

## Implementation Order

### Step 1: Theme Module

Create the theme layer first. This has the best leverage because later UI work can use named styles instead of inline color changes.

Success criteria:

- Existing UI opens with new cream/coral/dark tokens.
- No workflow behavior changes.
- Unit tests still pass.

### Step 2: Main App Shell

Refactor only the top bar and button hierarchy. Keep layout geometry and command wiring unchanged.

Success criteria:

- Primary/secondary/destructive actions are visually distinct.
- No user flow is removed.

### Step 3: Results Table Status System

Add row tags and status coloring. Avoid changing the data model unless necessary.

Success criteria:

- Complete/review/failed states are scannable.
- Table remains dense and stable.

### Step 4: Log and Evidence Dark Surface

Move logs and evidence detail toward `surface-dark`.

Success criteria:

- Log reads like technical product chrome.
- Candidate evidence remains copyable/readable.

### Step 5: Dialog Consistency

Apply the same visual system to settings and issuer mapping.

Success criteria:

- Settings feel like part of the app, not default Tkinter windows.
- Presets read as mode tabs.

### Step 6: Polish and Regression Pass

Run visual and behavior checks after each UI slice.

Checks:

- `python -B -m unittest discover -s tests`
- `python -B -m py_compile dart_auto.py dart_app\ui\app.py dart_app\ui\dialogs.py`
- Manual launch with `python dart_auto.py`
- Resize at roughly 1200px, 1420px, and wide desktop widths.
- Verify Korean copy, long paths, and long stock names do not overlap.

## Risk Notes

### Tkinter Styling Limits

Tkinter/ttk does not support all web-like features: letter-spacing, CSS-level focus rings, rounded rectangles on every native control, and detailed hover states are limited. The plan should prioritize color, typography, spacing, row tags, and surface hierarchy over impossible CSS fidelity.

### Korean Typography

The reference serif display system is not safe for dense Korean UI. Use serif styling only for small brand/title moments. Operational Korean labels, tables, and logs should stay in Malgun Gothic or Segoe UI-compatible fonts.

### Operational Density

This app is not a marketing page. The Claude-like style should warm and clarify the workspace, not reduce the amount of useful information. Dense table scanning, evidence inspection, and batch execution remain the primary UX.

### Coral Scarcity

Only one primary action should be coral in a given area. If every button becomes coral, the style loses its signal and the app becomes harder to operate.

## Target File Map

| File | Planned Role |
|---|---|
| `dart_app/config.py` | Design tokens and backward-compatible aliases |
| `dart_app/ui/theme.py` | Ttk style registration and font setup |
| `dart_app/ui/app.py` | Main shell, action hierarchy, result table, inspector, log |
| `dart_app/ui/dialogs.py` | Settings and issuer editor styling |
| `tests/` | Keep behavior tests stable; add theme smoke tests only if useful |

## PySide6 Prototype Direction

After reviewing Tkinter's styling limits, the more appropriate implementation path is a parallel PySide6 UI that reuses the existing workflow Modules instead of continuing to push visual polish through `ttk`.

### Why PySide6

- It keeps the Python DART, PDF, cache, and UNC-path logic in-process.
- It gives the app a stronger desktop UI model: `QMainWindow`, `QTableView`, worker signals, and stylesheet-driven visual hierarchy.
- It lets the Tkinter app remain as the stable fallback while the Qt surface reaches parity.
- It fits this app's real shape: dense table, selected-record inspector, technical log, batch worker, settings, and local file actions.

### Added Qt File Map

| File | Role |
|---|---|
| `dart_qt.py` | Root Qt launcher |
| `dart_app/qt_app/app.py` | PySide6 main window, worker wiring, app shell |
| `dart_app/qt_app/models.py` | `QAbstractTableModel` for DART records |
| `dart_app/qt_app/theme.py` | Cream/coral/dark QSS tokens |
| `dart_app/qt_app/__main__.py` | `python -m dart_app.qt_app` launcher |
| `tests/test_qt_app.py` | Offscreen Qt smoke tests |

### Qt Launch Commands

```powershell
python dart_qt.py
python -m dart_app.qt_app
```

### Qt Validation Commands

```powershell
python -B -m py_compile dart_qt.py dart_app\qt_app\app.py dart_app\qt_app\models.py dart_app\qt_app\theme.py
python -B -m unittest discover -s tests -p test_qt_app.py
python -B -m unittest discover -s tests
python -B tools\qt_live_check.py --status-only
python -B tools\qt_live_check.py --limit 1 --output-dir .\e2e_output\qt_live_opendart
```

## Definition of Done

- The app opens on a cream canvas, not purple or white.
- Coral is reserved for the main run/save action and selected emphasis.
- Logs and technical evidence use a dark product surface.
- Results table status is scannable through color and concise labels.
- Dialogs share the same surface and button hierarchy.
- Existing DART workflow behavior is unchanged.
- Existing unit tests pass after each implementation slice.

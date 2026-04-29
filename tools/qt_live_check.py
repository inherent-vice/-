from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QCoreApplication

from dart_app import config, state
from dart_app.domain.input_parser import parse_input_lines
from dart_app.qt_app.app import StatusRunnable, WorkflowRunnable, apply_runtime_settings, configure_qt_environment
from dart_app.services.record_workflow import RecordWorkflowOptions


DEFAULT_INPUT = """\
KR6MZ0005MV0
메리츠증권(DLB)3667
"""


class StopFlag:
    def is_set(self):
        return False


def capture_status(use_opendart=True, opendart_api_key=""):
    worker = StatusRunnable(use_opendart, opendart_api_key)
    logs = []
    finished = []
    worker.signals.log.connect(logs.append)
    worker.signals.finished.connect(lambda: finished.append(True))
    worker.run()
    return logs, bool(finished)


def capture_workflow(records, output_dir, use_opendart=True, opendart_api_key="", force_refresh=False, auto_result=True):
    settings = state.load_settings()
    runtime = apply_runtime_settings(settings)
    options = RecordWorkflowOptions(
        save_root=Path(output_dir),
        search_days=config.SEARCH_DAYS,
        result_search_days=config.RESULT_SEARCH_DAYS,
        save_termsheet_pdf=True,
        save_result_pdf=True,
        auto_result=auto_result,
        force_refresh=force_refresh,
    )
    worker = WorkflowRunnable(
        records,
        state.load_issuers(),
        options,
        use_opendart,
        opendart_api_key,
        StopFlag(),
        mode="termsheet",
    )
    updates = []
    logs = []
    progress = []
    finished = []
    worker.signals.record_update.connect(lambda code, name, data: updates.append((code, name, data)))
    worker.signals.log.connect(logs.append)
    worker.signals.progress.connect(progress.append)
    worker.signals.finished.connect(lambda completed, failed: finished.append((completed, failed)))
    worker.run()
    return {
        "runtime": runtime,
        "updates": updates,
        "logs": logs,
        "progress": progress,
        "finished": finished[0] if finished else None,
    }


def main():
    parser = argparse.ArgumentParser(description="Run the PySide6 worker path against live DART.")
    parser.add_argument("--input-file", type=Path)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "e2e_output" / "qt_live")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--force-refresh", action="store_true")
    parser.add_argument("--no-opendart", action="store_true")
    parser.add_argument("--no-auto-result", action="store_true")
    parser.add_argument("--status-only", action="store_true")
    args = parser.parse_args()

    configure_qt_environment()
    app = QCoreApplication.instance() or QCoreApplication([])

    settings = state.load_settings()
    use_opendart = not args.no_opendart and bool(settings.get("use_opendart", True))
    opendart_api_key = state.normalize_api_key(settings.get("opendart_api_key")) or state.discover_opendart_api_key()

    status_logs, status_finished = capture_status(use_opendart=use_opendart, opendart_api_key=opendart_api_key)
    print(f"mode use_opendart={use_opendart} force_refresh={args.force_refresh} auto_result={not args.no_auto_result}")
    for line in status_logs:
        print(line)
    if not status_finished:
        print("FAIL status worker did not finish")
        return 1
    if args.status_only:
        return 0 if any("DART 상태:" in line for line in status_logs) else 1

    input_text = args.input_file.read_text(encoding="utf-8") if args.input_file else DEFAULT_INPUT
    records = parse_input_lines(input_text.splitlines())[: max(1, args.limit)]
    args.output_dir.mkdir(parents=True, exist_ok=True)
    print(f"records={len(records)} output={args.output_dir}")

    result = capture_workflow(
        records,
        args.output_dir,
        use_opendart=use_opendart,
        opendart_api_key=opendart_api_key,
        force_refresh=args.force_refresh,
        auto_result=not args.no_auto_result,
    )
    for line in result["logs"]:
        print(line)
    completed, failed = result["finished"] or (0, len(records))
    print(f"finished completed={completed} failed={failed} progress={result['progress']}")
    for code, name, data in result["updates"]:
        status = data.get("status", "")
        termsheet = data.get("termsheet_status", "")
        result_status = data.get("result_status", "")
        file_path = data.get("file") or data.get("result_file") or ""
        print(f"update {code} {name} status={status} termsheet={termsheet} result={result_status} file={file_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())

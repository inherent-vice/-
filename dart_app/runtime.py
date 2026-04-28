from __future__ import annotations

import datetime as dt
import json
import re
import shutil
from pathlib import Path


def load_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def normalize_save_root(value=None, default_root=None):
    text = str(value or "").strip().strip('"')
    if text:
        return Path(text)
    return Path(default_root) if default_root is not None else Path(".")


def _coerce_bool(value, default=False):
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip().lower()
        if text in ("1", "true", "yes", "y", "on"):
            return True
        if text in ("0", "false", "no", "n", "off"):
            return False
    return bool(value)


def _coerce_int(value, default, min_value=1, max_value=None):
    try:
        out = int(value)
    except (TypeError, ValueError):
        out = int(default)
    out = max(min_value, out)
    if max_value is not None:
        out = min(max_value, out)
    return out


def _coerce_float(value, default, min_value=0.0, max_value=None):
    try:
        out = float(value)
    except (TypeError, ValueError):
        out = float(default)
    out = max(min_value, out)
    if max_value is not None:
        out = min(max_value, out)
    return out


def normalize_runtime_settings(data=None, defaults=None):
    data = dict(data or {})
    defaults = dict(defaults or {})
    merged = {**defaults, **data}

    normalized = {
        "search_days": _coerce_int(merged.get("search_days"), defaults.get("search_days", 90), 7),
        "result_search_days": _coerce_int(
            merged.get("result_search_days"), defaults.get("result_search_days", 180), 7
        ),
        "index_scan_limit": _coerce_int(
            merged.get("index_scan_limit"), defaults.get("index_scan_limit", 80), 1
        ),
        "pdf_scan_limit": _coerce_int(merged.get("pdf_scan_limit"), defaults.get("pdf_scan_limit", 80), 1),
        "result_scan_limit": _coerce_int(
            merged.get("result_scan_limit"), defaults.get("result_scan_limit", 50), 1
        ),
        "request_retries": _coerce_int(
            merged.get("request_retries"), defaults.get("request_retries", 3), 1
        ),
        "retry_backoff": _coerce_float(
            merged.get("retry_backoff"), defaults.get("retry_backoff", 0.8), 0.0
        ),
        "download_workers": _coerce_int(
            merged.get("download_workers"), defaults.get("download_workers", 3), 1
        ),
        "http_min_interval": _coerce_float(
            merged.get("http_min_interval"), defaults.get("http_min_interval", 0.4), 0.0
        ),
        "circuit_fail_limit": _coerce_int(
            merged.get("circuit_fail_limit"), defaults.get("circuit_fail_limit", 3), 1
        ),
        "circuit_cooldown": _coerce_float(
            merged.get("circuit_cooldown"), defaults.get("circuit_cooldown", 60), 0.0
        ),
        "search_cache_hours": _coerce_float(
            merged.get("search_cache_hours"), defaults.get("search_cache_hours", 6), 0.0
        ),
        "auto_result": _coerce_bool(merged.get("auto_result"), defaults.get("auto_result", True)),
        "force_refresh": _coerce_bool(merged.get("force_refresh"), defaults.get("force_refresh", False)),
        "save_termsheet_pdf": _coerce_bool(
            merged.get("save_termsheet_pdf"), defaults.get("save_termsheet_pdf", True)
        ),
        "save_result_pdf": _coerce_bool(
            merged.get("save_result_pdf"), defaults.get("save_result_pdf", True)
        ),
        "use_opendart": _coerce_bool(merged.get("use_opendart"), defaults.get("use_opendart", True)),
    }

    if "save_root" in merged:
        normalized["save_root"] = str(merged.get("save_root") or "")
    if "opendart_api_key" in merged:
        normalized["opendart_api_key"] = str(merged.get("opendart_api_key") or "").strip()
    return normalized


def today_str():
    return dt.date.today().strftime("%Y%m%d")


def safe_cache_name(value):
    return re.sub(r"[^A-Za-z0-9가-힣_.-]+", "_", str(value or "")).strip("_") or "empty"


def read_cache_text(path):
    path = Path(path)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="ignore")


def write_cache_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text or "", encoding="utf-8")


def read_cache_bytes(path):
    path = Path(path)
    if not path.exists():
        return None
    return path.read_bytes()


def write_cache_bytes(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data or b"")


def load_json_cache(path, max_age_seconds):
    path = Path(path)
    if not path.exists():
        return None
    if max_age_seconds is not None and max_age_seconds >= 0:
        age = dt.datetime.now().timestamp() - path.stat().st_mtime
        if age > max_age_seconds:
            return None
    return load_json(path, None)


def _count_files(path):
    if path.is_file():
        return 1
    if not path.exists():
        return 0
    return sum(1 for child in path.rglob("*") if child.is_file())


def _safe_rmtree(root, target):
    root = Path(root).resolve()
    target = Path(target).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        raise RuntimeError(f"Refusing to delete cache outside root: {target}")
    count = _count_files(target)
    if target.exists():
        if target.is_dir():
            shutil.rmtree(target)
        else:
            target.unlink()
    return count


def clear_cache(cache_dir, kind="all"):
    root = Path(cache_dir)
    if not root.exists():
        return 0

    groups = {
        "search": ["dart_search", "opendart/search"],
        "pdf": ["dart_pdf", "opendart/document"],
        "document": ["opendart/document"],
        "all": None,
    }
    targets = groups.get(kind, groups["all"])
    if targets is None:
        paths = [child for child in root.iterdir()]
    else:
        paths = [root / target for target in targets]
    return sum(_safe_rmtree(root, path) for path in paths if path.exists())


def cache_stats(cache_dir):
    root = Path(cache_dir)
    if not root.exists():
        return {"files": 0, "bytes": 0}
    files = [path for path in root.rglob("*") if path.is_file()]
    return {"files": len(files), "bytes": sum(path.stat().st_size for path in files)}

from __future__ import annotations

import os
from pathlib import Path

from dart_app import config
from dart_app.runtime import (
    load_json as _load_json,
    normalize_runtime_settings as _normalize_runtime_settings,
    normalize_save_root as _normalize_save_root,
    save_json as _save_json,
    today_str,
)

JSON_LOAD_ERRORS: list[str] = []


def load_json(path, default=None):
    try:
        return _load_json(path, default)
    except Exception as exc:
        JSON_LOAD_ERRORS.append(f"{path}: {exc}")
        return default


def save_json(path, data):
    return _save_json(path, data)


def load_issuers():
    merged = dict(config.DEFAULT_ISSUERS)
    user = load_json(config.ISSUERS_PATH, {}) or {}
    for key, value in user.items():
        if key.startswith("_") or not isinstance(value, str) or not value.strip():
            continue
        merged[key.strip()] = value.strip()
    return merged


def save_user_issuers(user_dict):
    cleaned = {"_comment": "사용자 추가 매핑. 기본값은 코드에 내장."}
    for key, value in (user_dict or {}).items():
        if key.startswith("_") or not value:
            continue
        key = str(key).strip()
        value = str(value).strip()
        if not key or not value:
            continue
        if config.DEFAULT_ISSUERS.get(key) == value:
            continue
        cleaned[key] = value
    save_json(config.ISSUERS_PATH, cleaned)


def normalize_save_root(value=None):
    return _normalize_save_root(value, config.DEFAULT_SAVE_ROOT)


def normalize_api_key(value=None):
    return str(value or "").strip()


def _read_env_api_key(path):
    path = Path(path)
    if not path.exists():
        return ""
    try:
        for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() in ("OPENDART_API_KEY", "OPEN_DART_API_KEY", "DART_API_KEY"):
                return normalize_api_key(value.strip().strip('"').strip("'"))
    except OSError:
        return ""
    return ""


def discover_opendart_api_key():
    for key in ("OPENDART_API_KEY", "OPEN_DART_API_KEY", "DART_API_KEY"):
        value = normalize_api_key(os.environ.get(key))
        if value:
            return value

    candidates = [
        config.APP_DIR / ".env",
        config.APP_DIR.parent / ".env",
        Path.cwd() / ".env",
        Path(r"E:\Devs\Dart\.env"),
    ]
    seen = set()
    for path in candidates:
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        value = _read_env_api_key(path)
        if value:
            return value
    return ""


def runtime_defaults():
    return config.RUNTIME_PRESETS.get("균형 모드", config.DEFAULT_RUNTIME_SETTINGS)


def normalize_runtime_settings(data=None):
    return _normalize_runtime_settings(data, runtime_defaults())


def load_settings():
    data = load_json(config.SETTINGS_PATH, {}) or {}
    settings = normalize_runtime_settings(data)
    if data.get("result_search_days") == 180:
        settings["result_search_days"] = config.RESULT_SEARCH_DAYS
    if data.get("result_scan_limit") == 50:
        settings["result_scan_limit"] = config.RESULT_SCAN_LIMIT
    settings["save_root"] = str(normalize_save_root(data.get("save_root")))
    if data.get("opendart_api_key"):
        settings["opendart_api_key"] = normalize_api_key(data.get("opendart_api_key"))
    return settings


def save_settings(settings):
    settings = dict(settings or {})
    root = normalize_save_root(settings.get("save_root"))
    normalized = normalize_runtime_settings(settings)
    normalized["save_root"] = str(root)
    if settings.get("opendart_api_key") is not None:
        normalized["opendart_api_key"] = normalize_api_key(settings.get("opendart_api_key"))
    save_json(config.SETTINGS_PATH, normalized)
    return root


def get_save_root():
    return normalize_save_root(load_settings().get("save_root"))


def get_opendart_api_key():
    settings_key = normalize_api_key(load_settings().get("opendart_api_key"))
    return settings_key or discover_opendart_api_key()


def get_state():
    config.STATE_DIR.mkdir(exist_ok=True)
    path = config.STATE_DIR / f"{today_str()}.json"
    return path, load_json(path, {"searched": []})

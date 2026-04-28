from __future__ import annotations

import re
from pathlib import Path


def normalize_save_root(save_root):
    value = str(save_root or "").strip().strip('"')
    return Path(value) if value else Path(".")


def safe_filename(s):
    return re.sub(r'[\\/:*?"<>|]', "_", s).strip()

def unique_path(path):
    """Avoid silently overwriting an existing downloaded PDF."""
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for i in range(1, 1000):
        candidate = parent / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"저장 파일명을 만들 수 없습니다: {path}")

def stock_output_dir(save_root, stock_code):
    root = normalize_save_root(save_root)
    safe_code = safe_filename(stock_code).upper()
    return root / safe_code if safe_code else root

def output_pdf_path(save_root, stock_code, stock_name, suffix=""):
    folder = stock_output_dir(save_root, stock_code)
    folder.mkdir(parents=True, exist_ok=True)
    safe_code = safe_filename(stock_code).upper()
    safe_name = safe_filename(stock_name)
    if safe_code:
        fname = f"{safe_code}_{safe_name}{suffix}.pdf"
    else:
        fname = f"{safe_name}{suffix}.pdf"
    return unique_path(folder / fname)

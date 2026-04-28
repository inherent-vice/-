from __future__ import annotations

from dart_app.utils.text import clean_text


def normalize_structured_bond_row(row):
    row = dict(row or {})
    normalized = {}
    for key, value in row.items():
        normalized[str(key)] = clean_text(str(value)) if value is not None else ""
    return normalized


def _first(row, *keys):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return ""


def structured_bond_db_evidence(row):
    row = normalize_structured_bond_row(row)
    parts = []
    public_flag = _first(row, "public_flag", "PublicFlag", "PUBLIC_FLAG")
    bond_type = _first(row, "bond_type", "BondType", "BOND_TYPE")
    issue_date = _first(row, "issue_date", "IssueDate", "ISSUE_DATE")
    due_date = _first(row, "due_date", "DueDate", "DUE_DATE")
    underlying = _first(row, "underlying_memo", "UnderlyingMemo", "UNDERLYING_MEMO")
    if public_flag:
        parts.append(f"PublicFlag={public_flag}")
    if bond_type:
        parts.append(f"BondType={bond_type}")
    if issue_date:
        parts.append(f"IssueDate={issue_date}")
    if due_date:
        parts.append(f"DueDate={due_date}")
    if underlying:
        parts.append(f"Underlying={underlying}")
    return ", ".join(parts)

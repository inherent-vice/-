from __future__ import annotations

import os
import sys
from pathlib import Path

from dart_app.domain.structured_bond import normalize_structured_bond_row


def couponcheck_root_candidates():
    env = os.environ.get("COUPONCHECK_ROOT")
    candidates = []
    if env:
        candidates.append(Path(env))
    here = Path(__file__).resolve()
    candidates.extend([
        here.parents[3] / "CouponCheck",
        here.parents[3] / "couponcheck",
        Path(r"E:\Devs\CouponCheck"),
        Path(r"C:\Devs\CouponCheck"),
    ])
    return candidates


def find_couponcheck_root():
    for path in couponcheck_root_candidates():
        if (path / "CouponCheck").exists() or (path / "rule_engine").exists():
            return path
    return None


def _default_sql_driver():
    for name in ("ODBC Driver 18 for SQL Server", "ODBC Driver 17 for SQL Server", "SQL Server"):
        return name
    return "SQL Server"


class StructuredBondDbLookup:
    """Optional read-only lookup against CouponCheck's structured-bond DB layer."""

    def __init__(self, client=None, error=""):
        self.client = client
        self.error = error

    @property
    def enabled(self):
        return self.client is not None

    @classmethod
    def open(cls):
        root = find_couponcheck_root()
        if root:
            root_text = str(root)
            if root_text not in sys.path:
                sys.path.insert(0, root_text)
        os.environ.setdefault("SQL_DRIVER", _default_sql_driver())
        try:
            from CouponCheck.rule_engine.db import SqlServerClient

            return cls(SqlServerClient.from_env())
        except Exception as exc:
            return cls(None, f"{type(exc).__name__}: {exc}")

    def close(self):
        try:
            if self.client:
                self.client.close()
        except Exception:
            pass

    def get(self, bond_id):
        bond_id = str(bond_id or "").strip().upper()
        if not bond_id or not self.client:
            return None
        queries = [
            (
                "SELECT TOP 1 * FROM IRDRV_STOCK_BOND "
                "WHERE UPPER(BondID)=UPPER(?) OR UPPER(BOND_ID)=UPPER(?)"
            ),
            (
                "SELECT TOP 1 * FROM StructuredBond "
                "WHERE UPPER(BondID)=UPPER(?) OR UPPER(BOND_ID)=UPPER(?)"
            ),
        ]
        for query in queries:
            try:
                row = self.client.query_one(query, [bond_id, bond_id])
            except TypeError:
                try:
                    row = self.client.query_one(query, bond_id, bond_id)
                except Exception as exc:
                    self.error = f"{type(exc).__name__}: {exc}"
                    continue
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
                continue
            if row:
                return normalize_structured_bond_row(row)
        return None

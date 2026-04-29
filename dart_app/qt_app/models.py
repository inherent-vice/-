from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor

from dart_app.qt_app.theme import COLORS


class RecordsTableModel(QAbstractTableModel):
    COLUMNS = [
        ("target", "대상"),
        ("stock_code", "종목코드"),
        ("stock_name", "종목명"),
        ("issuer", "발행사"),
        ("round_full", "회차"),
        ("product", "상품"),
        ("status", "상태"),
        ("termsheet_status", "텀싯"),
        ("result_status", "발행실적"),
        ("folder", "저장 위치"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[dict] = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        if not (0 <= index.row() < len(self._rows)) or not (0 <= index.column() < len(self.COLUMNS)):
            return None
        row = self._rows[index.row()]
        key = self.COLUMNS[index.column()][0]

        if role == Qt.CheckStateRole and key == "target":
            return Qt.Checked if row.get("target", True) else Qt.Unchecked
        if role == Qt.DisplayRole:
            if key == "target":
                return ""
            return str(row.get(key, "") or "")
        if role == Qt.ToolTipRole:
            return str(row.get(key, "") or "")
        if role == Qt.BackgroundRole:
            return self._status_background(row)
        if role == Qt.ForegroundRole:
            return self._status_foreground(row)
        if role == Qt.UserRole:
            return row
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            if not 0 <= section < len(self.COLUMNS):
                return None
            return self.COLUMNS[section][1]
        return section + 1

    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.COLUMNS[index.column()][0] == "target":
            flags |= Qt.ItemIsUserCheckable
        return flags

    def setData(self, index, value, role=Qt.EditRole):
        if not index.isValid() or self.COLUMNS[index.column()][0] != "target":
            return False
        if role != Qt.CheckStateRole:
            return False
        row = self._rows[index.row()]
        row["target"] = value in (Qt.Checked, Qt.CheckState.Checked)
        self.dataChanged.emit(index, index, [Qt.CheckStateRole, Qt.DisplayRole])
        return True

    def records(self):
        return list(self._rows)

    def record_at(self, row):
        if 0 <= row < len(self._rows):
            return self._rows[row]
        return None

    def set_records(self, records):
        self.beginResetModel()
        self._rows = [dict(record) for record in records]
        self.endResetModel()

    def upsert(self, stock_code, stock_name, updates):
        key = self._record_key(stock_code, stock_name)
        for row_index, row in enumerate(self._rows):
            if self._record_key(row.get("stock_code"), row.get("stock_name")) == key:
                row.update(updates)
                top_left = self.index(row_index, 0)
                bottom_right = self.index(row_index, len(self.COLUMNS) - 1)
                self.dataChanged.emit(top_left, bottom_right, [Qt.DisplayRole, Qt.BackgroundRole, Qt.ForegroundRole])
                return

        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        row = {"stock_code": stock_code, "stock_name": stock_name}
        row.update(updates)
        self._rows.append(row)
        self.endInsertRows()

    def _record_key(self, stock_code, stock_name):
        return f"{str(stock_code or '').strip().upper()}|{str(stock_name or '').strip()}"

    def _status_background(self, row):
        status_text = " ".join(str(row.get(key, "") or "") for key in ("status", "termsheet_status", "result_status"))
        if "실패" in status_text:
            return QColor("#f7e4df")
        if "미발견" in status_text or "검토" in status_text:
            return QColor("#f5ecd5")
        if "검색" in status_text or "중" in status_text or "확인" in status_text:
            return QColor("#f3e2da")
        if "완료" in status_text or "저장" in status_text or "발행됨" in status_text:
            return QColor("#edf3e5")
        return None

    def _status_foreground(self, row):
        status_text = " ".join(str(row.get(key, "") or "") for key in ("status", "termsheet_status", "result_status"))
        if "실패" in status_text:
            return QColor(COLORS["error"])
        if "미발견" in status_text or "검토" in status_text:
            return QColor("#7a5a00")
        return QColor(COLORS["body"])

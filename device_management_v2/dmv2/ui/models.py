from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt


ASSET_COLUMNS = [
    ("id", "ID"),
    ("device_type", "Typ"),
    ("asset_tag", "SN / IMEI"),
    ("model_name", "Modell"),
    ("manufacturer", "Hersteller"),
    ("inventory_status", "Status"),
    ("assigned_to", "User"),
    ("hostname", "Hostname"),
]


class AssetTableModel(QAbstractTableModel):
    def __init__(self, rows=None, parent=None):
        super().__init__(parent)
        self._rows = list(rows or [])

    def rowCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        if parent.isValid():
            return 0
        return len(ASSET_COLUMNS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self.row_at(index.row())
        if row is None:
            return None
        key, _label = ASSET_COLUMNS[index.column()]
        if role == Qt.DisplayRole:
            return _cell(row.get(key))
        if role == Qt.TextAlignmentRole and key == "id":
            return Qt.AlignRight | Qt.AlignVCenter
        if role == Qt.UserRole:
            return row
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal and 0 <= section < len(ASSET_COLUMNS):
            return ASSET_COLUMNS[section][1]
        return str(section + 1)

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = list(rows or [])
        self.endResetModel()

    def row_at(self, row_index):
        if 0 <= row_index < len(self._rows):
            return self._rows[row_index]
        return None


class AssetFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._query = ""
        self._status = "Alle Status"
        self.setSortCaseSensitivity(Qt.CaseInsensitive)

    def set_query(self, query):
        self.beginFilterChange()
        self._query = str(query or "").casefold().strip()
        self.endFilterChange()

    def set_status(self, status):
        self.beginFilterChange()
        self._status = str(status or "Alle Status")
        self.endFilterChange()

    def filterAcceptsRow(self, source_row, source_parent):
        model = self.sourceModel()
        row = model.row_at(source_row) if model else None
        if not row:
            return False
        if self._status != "Alle Status" and row.get("inventory_status") != self._status:
            return False
        if not self._query:
            return True
        haystack = " ".join(
            _cell(row.get(key))
            for key in (
                "device_type",
                "asset_tag",
                "model_name",
                "manufacturer",
                "inventory_status",
                "assigned_to",
                "hostname",
            )
        ).casefold()
        return self._query in haystack

    def lessThan(self, left, right):
        left_row = self.sourceModel().row_at(left.row())
        right_row = self.sourceModel().row_at(right.row())
        left_key = ASSET_COLUMNS[left.column()][0]
        right_key = ASSET_COLUMNS[right.column()][0]
        return _sort_value(left_row.get(left_key)) < _sort_value(right_row.get(right_key))

    def visible_rows(self):
        rows = []
        source_model = self.sourceModel()
        if source_model is None:
            return rows
        for proxy_row in range(self.rowCount()):
            source_index = self.mapToSource(self.index(proxy_row, 0))
            row = source_model.row_at(source_index.row())
            if row is not None:
                rows.append(row)
        return rows


def _cell(value):
    if value is None:
        return ""
    return str(value).strip()


def _sort_value(value):
    if value is None:
        return ""
    if isinstance(value, int):
        return value
    return str(value).casefold().strip()

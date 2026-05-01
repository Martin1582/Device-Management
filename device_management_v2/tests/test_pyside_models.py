import unittest

from PySide6.QtCore import Qt

from dmv2.ui.models import AssetFilterProxyModel, AssetTableModel


class AssetTableModelTest(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {
                "id": 1,
                "device_type": "Notebook",
                "asset_tag": "NB-001",
                "model_name": "ThinkPad",
                "manufacturer": "Lenovo",
                "inventory_status": "active",
                "assigned_to": "Max Mustermann",
                "hostname": "LT-MAX",
            },
            {
                "id": 2,
                "device_type": "Smartphone",
                "asset_tag": "PH-010",
                "model_name": "iPhone",
                "manufacturer": "Apple",
                "inventory_status": "inactive",
                "assigned_to": "",
                "hostname": "",
            },
        ]

    def test_asset_table_model_exposes_display_values(self):
        model = AssetTableModel(self.rows)

        self.assertEqual(model.rowCount(), 2)
        self.assertEqual(model.columnCount(), 8)
        self.assertEqual(model.headerData(2, Qt.Horizontal), "SN / IMEI")
        self.assertEqual(model.data(model.index(0, 2), Qt.DisplayRole), "NB-001")
        self.assertEqual(model.data(model.index(0, 0), Qt.UserRole)["id"], 1)

    def test_asset_filter_proxy_filters_by_query_and_status(self):
        model = AssetTableModel(self.rows)
        proxy = AssetFilterProxyModel()
        proxy.setSourceModel(model)

        proxy.set_query("iphone")
        self.assertEqual(proxy.rowCount(), 1)
        self.assertEqual(proxy.visible_rows()[0]["asset_tag"], "PH-010")

        proxy.set_status("active")
        self.assertEqual(proxy.rowCount(), 0)

    def test_asset_filter_proxy_returns_visible_rows_in_proxy_order(self):
        model = AssetTableModel(self.rows)
        proxy = AssetFilterProxyModel()
        proxy.setSourceModel(model)
        proxy.sort(2, Qt.DescendingOrder)

        rows = proxy.visible_rows()

        self.assertEqual([row["asset_tag"] for row in rows], ["PH-010", "NB-001"])


if __name__ == "__main__":
    unittest.main()

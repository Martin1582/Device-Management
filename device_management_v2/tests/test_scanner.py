import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dmv2.services.scanner import decode_identifier_from_file, decode_identifier_from_image


class ScannerServiceTest(unittest.TestCase):
    def test_decode_identifier_from_qr_image(self):
        import zxingcpp

        image = zxingcpp.write_barcode_to_image(
            zxingcpp.create_barcode("NB-QR-001", zxingcpp.BarcodeFormat.QRCode),
            scale=4,
        )

        value = decode_identifier_from_image(image)

        self.assertEqual(value, "NB-QR-001")

    def test_decode_identifier_from_code128_image(self):
        import zxingcpp

        image = zxingcpp.write_barcode_to_image(
            zxingcpp.create_barcode("SN-128-009", zxingcpp.BarcodeFormat.Code128),
            scale=4,
        )

        value = decode_identifier_from_image(image)

        self.assertEqual(value, "SN-128-009")

    def test_decode_identifier_from_file_uses_pil_image(self):
        import zxingcpp

        image = zxingcpp.write_barcode_to_image(
            zxingcpp.create_barcode("PH-IMEI-123", zxingcpp.BarcodeFormat.QRCode),
            scale=4,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "code.png"
            file_path.write_bytes(b"placeholder")

            with patch("PIL.Image.open") as image_open:
                image_open.return_value.__enter__.return_value = image

                value = decode_identifier_from_file(file_path)

        self.assertEqual(value, "PH-IMEI-123")

    def test_decode_identifier_raises_when_nothing_is_found(self):
        with self.assertRaises(ValueError):
            decode_identifier_from_image(object())


if __name__ == "__main__":
    unittest.main()

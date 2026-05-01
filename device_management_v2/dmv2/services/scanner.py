from pathlib import Path

SUPPORTED_IMAGE_TYPES = [
    ("Bilddateien", "*.png;*.jpg;*.jpeg;*.bmp;*.webp;*.tif;*.tiff"),
    ("PNG", "*.png"),
    ("JPEG", "*.jpg;*.jpeg"),
    ("Bitmap", "*.bmp"),
    ("Alle Dateien", "*.*"),
]


def scanner_runtime_available():
    try:
        import PIL  # noqa: F401
        import zxingcpp  # noqa: F401
    except Exception:
        return False
    return True


def decode_identifier_from_image(image):
    try:
        import zxingcpp
    except Exception as exc:
        raise ValueError("Scanner-Funktion ist nicht verfuegbar. Bitte pillow und zxing-cpp installieren.") from exc
    try:
        result = zxingcpp.read_barcode(image)
    except Exception as exc:
        raise ValueError("Bild konnte nicht als Barcode- oder QR-Code-Quelle gelesen werden.") from exc
    if result is None or not str(result.text or "").strip():
        raise ValueError("Kein Barcode oder QR-Code erkannt.")
    return str(result.text).strip()


def decode_identifier_from_file(file_path):
    try:
        from PIL import Image
    except Exception as exc:
        raise ValueError("Bildverarbeitung ist nicht verfuegbar. Bitte pillow installieren.") from exc

    path = Path(file_path)
    if not path.exists():
        raise ValueError(f"Datei nicht gefunden: {path}")

    with Image.open(path) as image:
        return decode_identifier_from_image(image)

import csv
import html
from datetime import datetime
from pathlib import Path


CSV_COLUMNS = [
    ("device_type", "Typ"),
    ("asset_tag", "SN / IMEI"),
    ("model_name", "Modell"),
    ("manufacturer", "Hersteller"),
    ("inventory_status", "Inventarstatus"),
    ("assigned_to", "User"),
    ("hostname", "Hostname"),
    ("assignment_status", "Zuweisungsstatus"),
    ("updated_at", "Zuletzt geaendert"),
    ("notes", "Notizen"),
]


def export_asset_snapshots_to_csv(rows, file_path):
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file_handle:
        writer = csv.writer(file_handle, delimiter=";")
        writer.writerow([label for _key, label in CSV_COLUMNS])
        for row in rows:
            writer.writerow([_cell(row.get(key)) for key, _label in CSV_COLUMNS])


def export_asset_snapshots_to_html(rows, file_path, title="Device Management v2 - Inventarliste"):
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
    header_cells = "".join(f"<th>{html.escape(label)}</th>" for _key, label in CSV_COLUMNS)
    body_rows = []
    for row in rows:
        cells = "".join(f"<td>{html.escape(_cell(row.get(key)))}</td>" for key, _label in CSV_COLUMNS)
        body_rows.append(f"<tr>{cells}</tr>")
    if not body_rows:
        body_rows.append(f"<tr><td colspan=\"{len(CSV_COLUMNS)}\">Keine Assets in der aktuellen Ansicht.</td></tr>")

    document = f"""<!doctype html>
<html lang="de">
<head>
  <meta charset="utf-8">
  <title>{html.escape(title)}</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 32px; color: #172033; }}
    h1 {{ color: #14365d; margin-bottom: 4px; }}
    .meta {{ color: #5a6f86; margin-bottom: 18px; }}
    table {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
    th, td {{ border: 1px solid #c9d2dc; padding: 7px 8px; text-align: left; vertical-align: top; }}
    th {{ background: #eef3f8; color: #243247; }}
    tr:nth-child(even) {{ background: #f8fafc; }}
  </style>
</head>
<body>
  <h1>{html.escape(title)}</h1>
  <div class="meta">Stand: {generated_at} | Eintraege: {len(rows)}</div>
  <table>
    <thead><tr>{header_cells}</tr></thead>
    <tbody>
      {''.join(body_rows)}
    </tbody>
  </table>
</body>
</html>
"""
    path.write_text(document, encoding="utf-8")


def build_export_filename(extension, prefix="DeviceManagementV2_Assets"):
    suffix = str(extension).lstrip(".")
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return f"{prefix}_{timestamp}.{suffix}"


def _cell(value):
    if value is None:
        return ""
    return str(value).strip()

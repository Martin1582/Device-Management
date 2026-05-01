Device Management - Admin-Handbuch

Technik
- Sprache: Python 3
- GUI: customtkinter
- Datenbank: SQLite
- Excel-Import: openpyxl
- Konfiguration: config.json
- Einstiegspunkt: v0.2.py
- Anwendungscode: asset_manager/

Projektstruktur
- asset_manager/app.py: GUI, Detailansicht, Historie, Filter, Backup/Restore, Vorschau-Import
- asset_manager/db.py: Datenzugriff, Historie, Integritätsregeln, Mehrbenutzer-Stufe 1
- asset_manager/services.py: Import, Export, Backup/Restore, Berichte, Druckansicht
- asset_manager/config.py: Laden und Auflösen der Konfiguration
- assets/app_icon.*: neutrales projektspezifisches App-Icon
- test_db_manager.py: Datenbanktests
- test_services.py: Service- und Importtests

Mehrbenutzer-Stufe 1
- Gemeinsame Nutzung über eine zentrale SQLite-Datei, z. B. auf einem Netzlaufwerk
- Datenbankpfad wird über config.json gesteuert
- SQLite nutzt busy_timeout für parallelen Zugriff
- Die App prüft periodisch auf Änderungen und aktualisiert die Oberfläche automatisch

Datenmodell
- Tabelle assets enthält die aktiven Stammdaten
- Tabelle asset_history protokolliert Änderungen
- updated_at und updated_by unterstützen Nachvollziehbarkeit

Komfortfunktionen
- Backup und Restore
- Änderungshistorie
- Zuletzt geändert von
- Globale Suche
- Filter nach Status, Modell und unvollständigen Einträgen
- Sortierung
- Detailansicht
- Import-Vorschau
- Duplikat- und Qualitätsbericht
- CSV-Export der aktuellen Ansicht
- Druckansicht als HTML
- Dark/Light Umschalter
- Statusleiste mit Datenquelle und letzter Synchronisierung

Integritätsregeln
- Asset-Tag ist eindeutig und wird normalisiert geprüft
- extra_info wird nur für Notebooks als Hostname genutzt
- Hostnamen sind für Notebooks eindeutig, sofern gesetzt
- Status ist auf Aktiv oder Inaktiv begrenzt

Build und Tests
- Tests: python -m unittest test_db_manager.py test_services.py
- Syntaxcheck: python -m py_compile v0.2.py test_db_manager.py test_services.py asset_manager\*.py
- EXE-Build: python -m PyInstaller --noconfirm --clean --onefile --windowed --icon assets/app_icon.ico --add-data "assets/app_icon.ico;assets" --add-data "assets/app_icon.png;assets" --name DeviceManagement v0.2.py

Release-Inhalt
- DeviceManagement.exe
- it_assets.db
- config.json
- Beispiel_Import.xlsx
- README_User.md
- README_Admin.md
- README_Start.txt
- RELEASE_NOTES.txt

Betriebshinweise
- Importprotokolle werden beim Excel-Import automatisch neben der Quelldatei erzeugt
- Für gemeinsame Nutzung sollten alle Clients auf dieselbe zentrale Datenbankdatei zeigen
- Für produktiven Einsatz sollten regelmäßige Backups geplant werden

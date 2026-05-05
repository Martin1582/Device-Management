# Device Management v2

Dieses Verzeichnis ist der unabhängige Neubau von `Device Management`.

## Ziel

`v2` wird getrennt vom aktuellen Produktivstand entwickelt, damit Architektur, UI, Datenmodell und Mehrbenutzerlogik sauber neu aufgebaut werden koennen.

## Start

Empfohlener Start:

```powershell
Start_V2.bat
```

Alternativ:

```powershell
..\.venv\Scripts\python.exe main.py
```

Hinweis:
Die App startet auch ueber `python main.py`, selbst wenn die Scanner-Abhaengigkeiten auf diesem Python-Pfad fehlen. In diesem Fall bleiben Barcode- und QR-Funktionen deaktiviert.

## Aktueller Stand

Der aktuelle `v2`-Stand ist lauffaehig und umfasst:

- neues Datenmodell mit `managed_assets`, `people`, `asset_assignments`, `audit_events`
- Schema-Versionierung bis `Version 3`
- Legacy-Migration aus der bisherigen `assets`-Tabelle
- Repository-Schicht fuer Assets, Personen, Zuweisungen und Audit-Timeline
- erste echte `v2`-Oberflaeche mit Asset-Liste, Suche, Detailansicht und Timeline
- Dialoge fuer:
  - Asset anlegen
  - Asset bearbeiten
  - Asset loeschen
  - Person anlegen
  - Personenverwaltung
  - Zuweisung erstellen
  - Zuweisung bearbeiten
  - Rueckgabe eines Geraets
- Scan-Unterstuetzung fuer `SN` bzw. `SN / IMEI` ueber Barcode- oder QR-Code-Bild
- Scan-Suche, um Geraete ueber Barcode/QR direkt zu finden
- CSV-/XLSX-Import mit Vorschau, Validierung und Duplikatpruefung vor dem Schreiben in die Datenbank
- CSV-Export und HTML-Druckansicht fuer die aktuelle Asset-Liste
- Datenbank-Backup und Restore mit automatischem Sicherheitsbackup

## Fachliche Regeln

- `Notebook = SN`
- `Smartphone = SN / IMEI`
- Smartphones ignorieren Hostnamen in Zuweisungen
- pro Asset gibt es immer nur eine aktuelle aktive Zuweisung
- Personen koennen nicht geloescht werden, solange aktive Zuweisungen bestehen
- beim Wechsel eines Assets zu `Smartphone` wird ein aktiver Hostname geleert

## Projektstruktur

- `main.py`
  Startpunkt fuer die lokale Entwicklung
- `Start_V2.bat`
  empfohlener Windows-Start ueber die vorhandene `.venv`
- `config.json`
  lokale Entwicklungs-Konfiguration
- `requirements.txt`
  Python-Abhaengigkeiten fuer `v2`
- `dmv2/bootstrap.py`
  App-Start
- `dmv2/config.py`
  Laden und Aufloesen der Konfiguration
- `dmv2/constants.py`
  zentrale UI-Konstanten
- `dmv2/db/migrations.py`
  Schema-Versionierung und Legacy-Migration
- `dmv2/db/repository.py`
  Datenzugriff und fachliche Workflows
- `dmv2/services/scanner.py`
  Barcode-/QR-Code-Dekodierung aus Bilddateien
- `dmv2/services/importer.py`
  CSV-/XLSX-Import mit Vorschau, Validierung und kontrolliertem Schreiben
- `dmv2/services/exporter.py`
  CSV-Export und HTML-Druckansicht
- `dmv2/services/backup.py`
  Backup und Restore der SQLite-Datenbank
- `dmv2/ui/main_window.py`
  bisherige `v2`-Oberflaeche
- `dmv2/ui/pyside_main_window.py`
  aktuelle PySide6-Oberflaeche
- `tests/`
  Tests fuer Konfiguration, Migrationen, Repository, Import, Export, Backup, UI-Modelle und Scanner

## Datenmodell

### `people`

- Personenstammdaten
- Name, E-Mail, Abteilung
- normalisierter Name zur Dublettenvermeidung

### `managed_assets`

- Geraetestammdaten
- Geraetetyp, Kennung, Modell, Hersteller, Status, Quelle, Notizen
- `record_version` fuer spaetere Konfliktbehandlung

### `asset_assignments`

- aktuelle und historische Geraetezuweisungen
- Person, Hostname, Status, Notizen
- `is_current` markiert die aktive Zuweisung

### `audit_events`

- technische und fachliche Historie
- erfasst Aenderungen an Assets, Personen und Zuweisungen

## Bedienung

### Asset-Uebersicht

- globale Suche nach `SN`, `IMEI`, Modell, User oder Hostname
- Code-Suche ueber Barcode-/QR-Bild
- Auswahl eines Assets aktualisiert rechts die Detailansicht

### Asset-Dialoge

- neues Asset anlegen
- Kennung manuell oder per Barcode/QR erfassen
- bestehendes Asset bearbeiten
- Asset loeschen mit Sicherheitsabfrage

### Personenverwaltung

- durchsuchbare Personenliste
- Stammdaten bearbeiten
- aktuell zugewiesene Geraete sehen
- Personenhistorie einsehen
- Loeschen nur ohne aktive Zuweisung

### Zuweisungen

- neue Zuweisung auf ausgewaehltes Asset setzen
- bestehende aktive Zuweisung bearbeiten
- Geraet rueckgeben

### Import

- unterstuetzt CSV- und XLSX-Dateien
- erwartet mindestens `SN / IMEI` und `Modell`
- erkennt u. a. `Typ`, `Hersteller`, `Status`, `User`, `Hostname`, `Notizen` und `Quelle`
- zeigt vor dem Import alle Zeilen mit Status `OK`, `Duplikat` oder `Fehler`
- schreibt erst nach ausdruecklicher Bestaetigung in die Datenbank
- ueberspringt Duplikate und fehlerhafte Zeilen
- legt bei gueltigem `User` und/oder `Hostname` direkt eine aktive Zuweisung an

## Scanner-Funktion

Die Scan-Funktion nutzt:

- `pillow`
- `zxing-cpp`

Aktuell unterstuetzt:

- Barcode- oder QR-Code-Bilder aus Datei
- Uebernahme der erkannten Kennung in den Asset-Dialog
- Suche nach Asset ueber gescannten Code

Noch nicht enthalten:

- Webcam-Live-Scan

## Tests und Qualitaet

Aktueller Teststand:

- `57` automatisierte Tests

Abgedeckte Bereiche:

- Konfiguration
- Datenbank-Migrationen
- Legacy-Import
- Repository-Workflows
- Personenregeln
- Asset-Regeln
- Zuweisungen
- Import-Vorschau und Importausfuehrung
- Export
- Backup und Restore
- PySide6-Dialoge und Tabellenmodelle
- Scanner-Service

Tests starten:

```powershell
..\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_*.py" -v
```

Syntaxcheck:

```powershell
..\.venv\Scripts\python.exe -m py_compile main.py dmv2\bootstrap.py dmv2\config.py dmv2\constants.py dmv2\db\migrations.py dmv2\db\repository.py dmv2\services\scanner.py dmv2\ui\main_window.py tests\test_config.py tests\test_repository.py tests\test_scanner.py
```

## Entwicklungsprotokoll

### Schritt 1: v2-Grundgeruest

- eigenstaendiger `v2`-Ordner angelegt
- eigener Startpunkt und eigene Konfiguration
- erste Tests fuer Konfiguration und Repository-Status

### Schritt 2: neues Datenmodell und Migrationen

- Schema-Versionierung eingefuehrt
- `managed_assets`, `people`, `asset_assignments`, `audit_events` aufgebaut
- Legacy-Uebernahme aus `v1`-Struktur umgesetzt

### Schritt 3: Repository-Kern

- Personen anlegen/aktualisieren
- Assets anlegen, lesen, listen, bearbeiten, loeschen
- Zuweisungen anlegen, aendern, rueckgeben
- Audit-Timeline je Asset

### Schritt 4: erste echte v2-UI

- Asset-Liste
- Suchfunktion
- Detailansicht
- Audit-Timeline
- Theme-Umschalter

### Schritt 5: Dialoge fuer Kernprozesse

- Asset anlegen
- Asset bearbeiten
- Asset loeschen
- Person anlegen
- Zuweisung erstellen
- Zuweisung bearbeiten
- Rueckgabe

### Schritt 6: Personenverwaltung

- eigener Verwaltungsdialog
- Listenansicht
- Stammdatenpflege
- Sicht auf aktuell zugewiesene Geraete
- Personen-Historie
- Schutzlogik beim Loeschen

### Schritt 7: Barcode- und QR-Unterstuetzung

- Scan von Kennungen aus Bilddateien
- Uebernahme in den Asset-Dialog
- Scan-Suche ueber die Hauptsuche
- Fallback-Verhalten, wenn Scanner-Abhaengigkeiten fehlen

## Naechste sinnvolle Schritte

- Webcam-Scan
- Konflikterkennung fuer parallele Bearbeitung
- noch sauberere Modultrennung der UI
- Export- und Reporting-Funktionen in `v2`
- Release-/Build-Pfad fuer `v2`

Device Management - Anwenderhandbuch

Zweck
Diese App verwaltet Smartphones und Notebooks in einer gemeinsamen oder lokalen SQLite-Datenbank.

Start
1. Öffne den Release-Ordner.
2. Prüfe bei Bedarf die Datei config.json.
3. Starte DeviceManagement.exe.

Wichtige Bedienung
- Onboarding legt ein neues Gerät an.
- Change aktualisiert ein ausgewähltes Gerät.
- Offboarding setzt den Status auf Inaktiv.
- Löschen entfernt ein ausgewähltes Gerät dauerhaft.
- Import-Vorschau zeigt vor dem Excel-Import die geplanten Änderungen.
- Export speichert die aktuelle gefilterte Ansicht als CSV.
- Backup erstellt eine Sicherheitskopie der Datenbank.
- Restore spielt eine Backup-Datei zurück.
- Aktualisieren lädt den aktuellen Datenstand manuell nach.

Suche, Filter und Sortierung
- Die globale Suche durchsucht Smartphones und Notebooks gleichzeitig.
- Pro Tab gibt es Filter für Status, Modell und unvollständige Einträge.
- Die Sortierung kann nach Status, User, Modell, Asset-Tag oder zuletzt geändert erfolgen.

Detailansicht
- Nach Klick auf eine Gerätekarte werden rechts alle Details angezeigt.
- Dort siehst du auch "Zuletzt geändert", "Geändert von" und die Änderungshistorie.

Excel-Import
- Unterstützte Datei: .xlsx
- Empfohlene Spalten: Typ, User, Modell, S/N / IMEI, Hostname, Status
- Bestehende Asset-Tags werden aktualisiert.
- Neue Asset-Tags werden neu angelegt.
- Zu jedem Import wird automatisch ein Importprotokoll als Textdatei neben der Excel-Datei gespeichert.

Berichte
- "Duplikat-Check" zeigt Dubletten oder Qualitätsprobleme.
- "Hinweise" zeigt Notebooks ohne Hostname.
- Über die Druckansicht kann eine Inventarliste als HTML-Datei erzeugt werden.

Wichtige Regeln
- Asset-Tags sind eindeutig, auch unabhängig von Groß-/Kleinschreibung.
- Hostnamen dürfen bei Notebooks nicht doppelt vergeben sein.
- Rufnummern werden bei Smartphones nicht gepflegt.

Gemeinsame Nutzung
- Mehrere Personen können dieselbe Datenbankdatei nutzen, wenn in config.json ein gemeinsamer Pfad gesetzt ist.
- Änderungen anderer Benutzer werden automatisch nachgeladen.

Sicherung
- Lege regelmäßig Backups der Datenbank an.

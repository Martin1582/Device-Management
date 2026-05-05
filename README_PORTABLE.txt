Device Management v2 - portable Startanleitung

So gibst du die App an ein anderes Windows-Geraet weiter:

1. Kopiere den kompletten Ordner "Device Management" auf das Zielgeraet.
2. Stelle sicher, dass Python 3.13 oder neuer installiert ist.
3. Starte im Hauptordner die Datei "Start.bat".

Was beim ersten Start passiert:

- Die App erstellt automatisch eine lokale Python-Umgebung unter
  "device_management_v2\.venv".
- Danach werden die benoetigten Pakete aus "device_management_v2\requirements-runtime.txt"
  installiert.
- Die Datenbank liegt standardmaessig relativ im Projektordner unter
  "device_management_v2\data\device_management_v2.db".

Wichtig:

- Beim ersten Start wird Internetzugang benoetigt, wenn die Python-Pakete noch
  nicht vorhanden sind.
- Den Ordner "device_management_v2\data" immer mitkopieren, wenn vorhandene
  Daten uebernommen werden sollen.
- Keine bestehende ".venv" von einem anderen Geraet mitkopieren. Sie wird bei
  Bedarf automatisch neu erstellt.

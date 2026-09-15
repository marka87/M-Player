# Offline Music Manager

Lokaler Windows-11-Musik-Manager mit PySide6-Oberfläche für YouTube- und Spotify-Links. Spotify liefert dabei nur Metadaten; die Audiodatei wird über eine YouTube-Suche mit `yt-dlp` bezogen.

## Installation

1. Installiere Python 3.11 oder neuer und aktiviere beim Setup **Add Python to PATH**.
2. Lege neben diesen Dateien eine virtuelle Umgebung an und installiere die Pakete:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```

3. Installiere FFmpeg. Mit winget:

   ```powershell
   winget install Gyan.FFmpeg
   ```

   Starte danach ein neues Terminal und prüfe `ffmpeg -version`. Alternativ FFmpeg von [gyan.dev](https://www.gyan.dev/ffmpeg/builds/) laden und dessen `bin`-Ordner zur Windows-Umgebungsvariable `Path` hinzufügen.
4. Installiere Deno als JavaScript-Laufzeit für die aktuellen YouTube-Prüfungen:

   ```powershell
   winget install DenoLand.Deno
   ```

   Öffne danach ein neues Terminal und prüfe `deno --version`.
5. Für Spotify lege eine Datei `.env`-ähnlich ist nicht erforderlich: setze die Variablen vor dem Start (oder dauerhaft in Windows):

   ```powershell
   $env:SPOTIPY_CLIENT_ID = "..."
   $env:SPOTIPY_CLIENT_SECRET = "..."
   ```

   Die Zugangsdaten stammen aus einer App im [Spotify Developer Dashboard](https://developer.spotify.com/dashboard). YouTube funktioniert ohne diese Variablen.
6. Nach einem Update die Pakete aktualisieren und starten:

   ```powershell
   pip install -r requirements.txt
   .\.venv\Scripts\python.exe main.py
   ```

Nur Inhalte herunterladen, für die du die nötigen Rechte hast.

## Ablage

Downloads landen in `Music\\Künstler\\Album\\01 - Titel.mp3`; unbekannte Alben in `Music\\Künstler\\Singles\\Titel.mp3`. Das eingebettete JPEG-Cover wird zusätzlich als `cover.jpg` im Albumordner abgelegt. Erst nach erfolgreicher FFmpeg-MP3-Konvertierung und ID3-Prüfung wird die Datei dorthin verschoben. `music_library.db` wird beim Start automatisch migriert.

FFmpeg muss `libmp3lame` enthalten (der Gyan-Build aus Schritt 3 tut das). `mutagen` schreibt ID3v2.3-Tags und eingebettete JPEG-/PNG-Cover; beide Pakete werden über `requirements.txt` installiert.

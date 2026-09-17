# 🎵 M-Player — Offline Music Manager & YouTube Downloader

Ein moderner, lokaler Musik-Manager für **Windows & Linux** mit eleganter PySide6-Oberfläche (Spotify-Dark-Theme), SQLite-Datenbank, integriertem YouTube-Downloader (`yt-dlp`), intelligenter Tag-Bereinigung und Duplicate-Finder.

<p align="center">
  <img src="assets/screenshot.png" alt="M-Player Vorschau" width="850">
</p>

---

## ✨ Was M-Player kann (Features)

### 🎧 1. Lokale Musikverwaltung & Bibliothek
* **Listen- & Rasteransicht:** Schnelles Umschalten zwischen einer kompakten Tabellenansicht und visuellem Cover-Grid.
* **Filter-Chips & Schnellsuche:** Direktes Filtern nach *Favoriten*, *Zuletzt hinzugefügt*, *Nicht gehört*, sowie dynamische Dropdowns nach **Künstler**, **Jahr** und **Genre**.
* **Song-Details & Empfehlungen:** Klappbare Seitenleiste mit Cover, Bitrate, Spieldauer, Abspielzähler und ähnlichen Song-Empfehlungen (Radio).
* **Playlists:** Eigene Playlists erstellen, verwalten und Tracks per Klick oder Drag-and-Drop organisieren.

### 📥 2. YouTube- & Spotify-Import
* **Direkte In-App-Suche (Entdecken):** Songs, Alben oder Playlists direkt in der App auf YouTube suchen – ganz ohne Browser.
* **Direct Stream / Vorhören:** Songs vor dem Download direkt per Audio-Stream in der App anhören.
* **Batch-Downloader:** YouTube-, YouTube-Music- und Spotify-Links einfügen und als hochwertige MP3 (320 kbps) mit eingebetteten Covern herunterladen.
* **Fortschritt & Warteschlange:** Visuelle Download-Queue mit Pause-, Fortsetzen- und Abbrechen-Funktion.

### 🧠 3. Intelligente Metadaten & Organisation
* **Auto-Tag-Cleaning:** Entfernt automatisch störenden YouTube-Müll wie `[Official Video]`, `(HD)`, `Topic`, `VEVO`, `Lyrics` usw. aus Künstler- und Titelfeldern.
* **Automatische Album-Erkennung:** Erkennt beim Scannen oder Laden fehlende Albumnamen und Release-Jahre online über die **iTunes Search API** und **MusicBrainz**.
* **Duplikat-Finder:** Findet doppelt vorhandene Songs (z. B. Video vs. Audio-Upload) anhand von **Fuzzy-Matching** und Spieldauer-Toleranz (±2s) mit interaktivem Bereinigungs-Dialog.
* **Automatische Cover-Suche:** Sucht und bettet hochauflösende Album-Cover automatisch in die ID3v2.3-Tags ein.

### 🎛️ 4. Player & Mini-Player
* **Vollwertige Wiedergabe:** Play/Pause, Skip, Shuffle (Zufall), Repeat (Wiederholen), Lautstärkeregler und stufenloser Timeline-Direct-Seek.
* **Mini-Player (`Ctrl+M`):** Kompaktes Schwebefenster für die Bildschirmecke, ideal beim Arbeiten oder Zocken.
* **Mehrsprachig (Multi-Language):** Vollständige Unterstützung für **Deutsch 🇩🇪**, **English 🇬🇧** und **Magyar 🇭🇺** (direkt in der oberen Leiste per `[ DE | EN | HU ]` umschaltbar).

---

## 🚀 Installation & Start

Es gibt zwei Möglichkeiten, M-Player zu nutzen:

### Option A: Fertige Downloads (Empfohlen — Keine Installation nötig)

Die neuesten Pakete findest du unter [Releases](https://github.com/marka87/M-Player/releases):

#### 🪟 Windows (Portable ZIP)
1. `M-Player-Portable-vX.X.X.zip` herunterladen und entpacken.
2. Doppelklick auf **`M-Player.exe`** – fertig!
> *Hinweis:* FFmpeg, ffprobe und alle Tools sind im `bin/`-Ordner bereits enthalten. Vollständig vom **USB-Stick** startbar.

#### 🐧 Linux (AppImage oder Portable Tarball)
* **AppImage (Universell für Ubuntu, Debian, Fedora, Arch etc.):**
  ```bash
  chmod +x M-Player-v*.AppImage
  ./M-Player-v*.AppImage
  ```
* **Portable Tarball (.tar.gz):**
  ```bash
  tar -xzf M-Player-Linux-v*.tar.gz
  cd M-Player-Linux
  ./run.sh
  ```

---

### Option B: Aus dem Quellcode ausführen (Entwickler)

#### 1. Voraussetzungen

* **Python 3.11** oder neuer
* **FFmpeg**:
  * **Windows:** `winget install Gyan.FFmpeg`
  * **Linux (Debian/Ubuntu):** `sudo apt install ffmpeg`
  * **Linux (Arch):** `sudo pacman -S ffmpeg`
* **Deno** (optional, für schnellere YouTube-Signaturauflösung):
  * **Windows:** `winget install DenoLand.Deno`
  * **Linux:** `curl -fsSL https://deno.land/install.sh | sh`

#### 2. Setup

Repository klonen und virtuelle Umgebung anlegen:

**Windows (PowerShell):**
```powershell
git clone https://github.com/marka87/M-Player.git
cd M-Player

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

**Linux (Bash):**
```bash
git clone https://github.com/marka87/M-Player.git
cd M-Player

# Notwendige Qt-Bibliotheken (falls minimales Linux)
sudo apt update && sudo apt install -y libgl1 libegl1 libxkbcommon-x11-0 ffmpeg

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

*(Optional)* Für den Import von Spotify-Playlists können eigene Spotify-API-Keys in der Umgebung hinterlegt werden (`SPOTIPY_CLIENT_ID` und `SPOTIPY_CLIENT_SECRET`). YouTube funktioniert komplett ohne API-Keys.

---

## 📦 Eigene Version bauen

### Auf Windows
```powershell
.\.venv\Scripts\python.exe scripts/build_portable.py
```
Erstellt das fertige Standalone-Paket `dist/M-Player-Portable-vX.X.X.zip`.

### Auf Linux
```bash
chmod +x scripts/build_linux.sh
./scripts/build_linux.sh
```
Erstellt sowohl das `dist/M-Player-Linux-vX.X.X.tar.gz` als auch die `dist/M-Player-vX.X.X-x86_64.AppImage`.

### 🤖 Automatisierte Builds (GitHub Actions CI/CD)
Das Repository verfügt über eine automatisierte GitHub Actions Pipeline (`.github/workflows/build-release.yml`):
* Sobald ein Versions-Tag gepusht wird (z. B. `git tag v1.0.1 && git push origin v1.0.1`), bauen parallele Runner automatisch die Windows- und Linux-Pakete.
* Die fertigen Binaries werden automatisch an ein offizielles GitHub-Release angehängt.

---

## ⌨️ Tastatur-Shortcuts

| Taste | Funktion |
| :--- | :--- |
| **Leertaste** | Play / Pause |
| **Enter** | Ausgewählten Song abspielen / Suche im Downloader & Entdecken starten |
| **Pfeil links / rechts** | 5 Sekunden vor- / zurückspulen |
| **Entf (Delete)** | Ausgewählten Song aus der Bibliothek löschen |
| **Ctrl + M** | Mini-Player umschalten |
| **Esc** | Song-Details-Seitenleiste schließen |

---

## 📁 Datenablage & Dateistruktur

* **Musikdateien:** Werden nach dem Schema `Music/<Playlist oder Einzeltitel>/<Künstler> - <Titel>.mp3` abgelegt.
* **Datenbank:** `music_library.db` (SQLite) speichert Metadaten, Playlists, Play-Counts und Favoriten lokal im Anwendungsverzeichnis.

---


## ⚖️ Rechtlicher Hinweis

M-Player stellt Funktionen zum Herunterladen und Verwalten von Audiodateien bereit. Die Nutzung dieser Funktionen muss den in deinem Land geltenden Urheberrechtsgesetzen entsprechen.

Der Download oder die Speicherung von urheberrechtlich geschützten Inhalten ist nur zulässig, wenn du dazu berechtigt bist, beispielsweise durch eine Lizenz, die Zustimmung des Rechteinhabers oder eine gesetzliche Ausnahme, soweit diese an deinem Wohnort gilt.

Der Entwickler von M-Player stellt lediglich die Software zur Verfügung und übernimmt keine Verantwortung für eine rechtswidrige Nutzung oder Urheberrechtsverletzungen durch die Anwender.

Nutze M-Player ausschließlich für Inhalte, deren Nutzung und Speicherung dir rechtlich erlaubt ist.

---

## 📄 Lizenz

Dieses Projekt steht unter der MIT License. Details siehe `LICENSE`.



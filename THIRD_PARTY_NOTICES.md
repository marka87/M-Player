# Third-Party Notices & Licenses

Dieses Dokument führt die wichtigsten Drittanbieter-Bibliotheken, externen Werkzeuge und Webservices auf, die in **M-Player** verwendet oder eingebunden werden.

---

## Übersicht der Komponenten

| Komponente | Zweck | Lizenz |
| :--- | :--- | :--- |
| **yt-dlp** | Audio-Extraktion, Stream-Auflösung und Metadaten-Abfrage von YouTube | The Unlicense |
| **FFmpeg** | Audio-Transkodierung, Konvertierung nach MP3 (320 kbps) und Stream-Verarbeitung | LGPL v2.1+ / GPL v2+ |
| **PySide6 (Qt for Python)** | Grafische Benutzeroberfläche (GUI), Styling und Audio-Playback (`QMediaPlayer`) | LGPLv3 / Commercial |
| **Mutagen** | Lesen und Schreiben von Audiodaten und ID3v2.3-Metadatentags (Cover, Artist, Album) | GNU GPL v2+ |
| **spotipy** | Python-Client für die Spotify Web API zum Auslesen öffentlicher Spotify-Playlists | MIT License |
| **SQLite** | Lokale, relationale Datenbank zur Speicherung von Songs, Playlists und Statistiken | Public Domain |
| **Deno** *(optional)* | Schnelle JavaScript-Laufzeitumgebung für yt-dlp zur Entschlüsselung von Signaturen | MIT License |
| **Apple iTunes Search API** | Webservices zur automatischen Auflösung von Alben, Release-Jahren und High-Res-Covern | Proprietär (Kostenlose Nutzung gemäß Apple API Terms) |
| **MusicBrainz API** | Freie Musikdatenbank zur Bereicherung von Titel- und Albuminformationen | CC0 / Open Data |
| **Deezer API** | Ergänzende Webservices zur Cover- und Metadaten-Recherche | Proprietär (Deezer API Terms of Use) |

---

## Hinweise zu Rechten & Marken

* **Qt & PySide6** sind eingetragene Marken der *The Qt Company Ltd.* und ihren Tochtergesellschaften.
* **Apple** und **iTunes** sind Marken der *Apple Inc.*, eingetragen in den USA und anderen Ländern.
* **Spotify** ist eine eingetragene Marke der *Spotify AB*.
* **YouTube** ist eine eingetragene Marke der *Google LLC*.
* Alle genannten Marken und Warenzeichen sind Eigentum der jeweiligen Rechteinhaber.

---

*Für die vollständigen Lizenzbestimmungen der jeweiligen Komponenten verweisen wir auf die offiziellen Webseiten und Repositories der Entwickler.*

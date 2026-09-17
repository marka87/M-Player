# Changelog

Alle nennenswerten Änderungen an diesem Projekt werden in dieser Datei dokumentiert.

Das Format basiert auf [Keep a Changelog](https://keepachangelog.com/de/1.0.0/)
und dieses Projekt hält sich an [Semantic Versioning](https://semver.org/lang/de/).

## [1.0.3] - 2026-09-17

### Added
- **High-Speed Mini-Thumbnails & Disk Caching**: Extrem schnelles Rendern und Scrollen in der Bibliothek durch vorberechnete 48x48 und 130x130 JPEG-Thumbnails auf der Festplatte. Kein zeitaufwendiges MP3-ID3-APIC-Parsing mehr im UI-Thread.
- **Background Preload Task**: Neuer Hintergrund-Worker (`ThumbnailPreloadTask`), der nach Datei-Imports und Library-Syncs Thumbnails im Leerlauf vorberechnet.
- **Schnellere YouTube-Suche**: Antwortzeiten mehr als halbiert durch 15-Treffer-Start-Batch, leichtgewichtigen Android-Client und kompakte 120x90 Thumbnails (~4 KB) statt schwerer HD-Bilder.
- **Automatische Versionierung**: `bump.bat` und `scripts/bump_version.py` für automatisierte SemVer-Releases und Changelog-Generierung.

### Fixed
- **CI/CD AppImage Build**: Korrektur der Download-URL für `appimagetool` auf das offizielle Continuous-Release.

## [1.0.2] - 2026-09-17

### Added
- **Kontextueller Download-Button**: Direkter Download-Knopf in der Player-Leiste während des Vorhörens eines Streams.
- **Rechtlicher Hinweis (Disclaimer-Dialog)**: Einmaliger Informationsdialog beim ersten Betreten des Download-Bereichs mit dauerhafter Speicherung der Bestätigung.
- **Pipeline-Integration**: Automatische Online-Album-Auflösung via iTunes Search API und Duplikatsprüfung vor dem Speichern direkt im Download-Prozess.
- **Tools-Bereich**: Eigene Navigationsseite für Metadaten-Tools und Duplikat-Finder.
- **Lizenzdokumentation**: Hinzufügen von `LICENSE` (MIT License) und `THIRD_PARTY_NOTICES.md`.

### Changed
- **Repository-Struktur**: Professionelle Modularisierung des Codes in `src/` (`database`, `services`, `translations`, `ui`), `scripts/` und `tests/`.
- **UX-Redesign**: Zusammenlegung von In-App-Suche (Entdecken), Link-Download und Warteschlange in eine einheitliche Ansicht mit Reitern.
- Versionsnummer auf `v1.0.2` angehoben.

### Fixed
- Layout-Rücksetzung bei Sprachwechsel behoben.
- Korrektur der Seitenanzahl und Index-Navigation im UI-Testsuite.

## [1.0.1] - 2026-09-17

### Added
- **Mehrsprachigkeit (i18n)**: Unterstützung für Deutsch (DE), Englisch (EN) und Ungarisch (HU) mit Umschalter in der Kopfleiste.
- **Linux-Unterstützung**: Bereitstellung von AppImage und portablem Tarball (`.tar.gz`).
- **CI/CD Pipeline**: Automatisierte GitHub Actions Workflows für plattformübergreifende Releases.

### Fixed
- Fallback-Strategie gegen YouTube-Bot-Detection bei Audio-Streaming und Suche.
- Stabilität der Bibliotheksansicht bei unvollständigen Metadaten verbessert.

## [1.0.0] - 2026-09-16

### Added
- **Musikbibliothek**: Lokale Speicherung und Verwaltung von Titeln mit SQLite-Datenbank.
- **Grid/List View**: Schnelles Umschalten zwischen Tabellenansicht und Cover-Raster.
- **Filter**: Filter-Chips (Favoriten, Zuletzt hinzugefügt, Nicht gehört) sowie dynamische Dropdowns für Künstler, Genre und Jahr.
- **Playlists**: Erstellen, Verwalten und Sortieren eigener Wiedergabelisten.
- **Mini Player**: Kompaktes, rahmenloses Schwebefenster (`Ctrl+M`) mit Steuerungselementen.
- **YouTube Downloader**: Herunterladen und Konvertieren von Audio in hochwertige MP3-Dateien (320 kbps) mit Warteschlange.
- **Spotify Import**: Importieren von Titeln aus Spotify-Playlists mit automatischem Audio-Matching.
- **Duplicate Finder**: Erkennung doppelter Titel anhand von Fuzzy-Matching und Spieldauer-Toleranz.
- **Cover Enricher**: Automatisches Laden und Einbetten hochauflösender Cover (iTunes, Deezer).
- **Album Resolver**: Erkennung fehlender Albumnamen und Veröffentlichungsjahre über Online-APIs.
- **Mehrsprachigkeit**: Grundstruktur für mehrsprachige Benutzeroberflächen.
- **Portable Version**: Skript zur Erstellung einer portablen, eigenständigen Windows-Version inklusive FFmpeg.


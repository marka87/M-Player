"""
Internationalization (i18n) module for M-Player.
Supports German (de), English (en), and Hungarian (hu).
"""

from typing import Dict, Any

LANGUAGES: Dict[str, str] = {
    "de": "Deutsch",
    "en": "English",
    "hu": "Magyar",
}

DEFAULT_LANGUAGE = "de"
_CURRENT_LANGUAGE = DEFAULT_LANGUAGE

TRANSLATIONS: Dict[str, Dict[str, str]] = {
    # Navigation
    "nav_downloader": {
        "de": "Downloader",
        "en": "Downloader",
        "hu": "Letöltő",
    },
    "nav_discover": {
        "de": "Entdecken",
        "en": "Discover",
        "hu": "Felfedezés",
    },
    "nav_library": {
        "de": "Bibliothek",
        "en": "Library",
        "hu": "Könyvtár",
    },
    "nav_favorites": {
        "de": "Favoriten",
        "en": "Favorites",
        "hu": "Kedvencek",
    },
    "nav_playlists": {
        "de": "Playlists",
        "en": "Playlists",
        "hu": "Lejátszási listák",
    },
    "nav_downloads": {
        "de": "Downloads",
        "en": "Downloads",
        "hu": "Letöltések",
    },
    "nav_settings": {
        "de": "Einstellungen",
        "en": "Settings",
        "hu": "Beállítások",
    },
    "nav_albums": {
        "de": "Alben",
        "en": "Albums",
        "hu": "Albumok",
    },
    "nav_tracks": {
        "de": "Songs",
        "en": "Songs",
        "hu": "Dalok",
    },
    "nav_tools": {
        "de": "Tools",
        "en": "Tools",
        "hu": "Eszközök",
    },

    # Header / Top Bar
    "search_placeholder": {
        "de": "Suche nach Songs, Künstlern, Alben… (Strg+F)",
        "en": "Search songs, artists, albums… (Ctrl+F)",
        "hu": "Keresés dalok, előadók, albumok között… (Ctrl+F)",
    },
    "refresh_library": {
        "de": "Bibliothek aktualisieren",
        "en": "Refresh Library",
        "hu": "Könyvtár frissítése",
    },
    "loading_library": {
        "de": "Bibliothek wird geladen…",
        "en": "Loading library…",
        "hu": "Könyvtár betöltése…",
    },
    "stats_tracks_time": {
        "de": "{tracks} Songs • {time}",
        "en": "{tracks} songs • {time}",
        "hu": "{tracks} dal • {time}",
    },

    # Table columns
    "col_cover": {"de": "Cover", "en": "Cover", "hu": "Borító"},
    "col_title": {"de": "Titel", "en": "Title", "hu": "Cím"},
    "col_artist": {"de": "Künstler", "en": "Artist", "hu": "Előadó"},
    "col_album": {"de": "Album", "en": "Album", "hu": "Album"},
    "col_duration": {"de": "Dauer", "en": "Duration", "hu": "Hossz"},
    "col_year": {"de": "Jahr", "en": "Year", "hu": "Év"},
    "col_quality": {"de": "Qualität", "en": "Quality", "hu": "Minőség"},
    "col_status": {"de": "Status", "en": "Status", "hu": "Állapot"},
    "col_playlist": {"de": "Playlist", "en": "Playlist", "hu": "Lejátszási lista"},
    "col_speed": {"de": "Geschwindigkeit", "en": "Speed", "hu": "Sebesség"},
    "col_eta": {"de": "Restzeit", "en": "ETA", "hu": "Hátralévő idő"},
    "col_channel": {"de": "Künstler / Kanal", "en": "Artist / Channel", "hu": "Előadó / Csatorna"},
    "col_type": {"de": "Typ", "en": "Type", "hu": "Típus"},
    "col_actions": {"de": "Aktionen", "en": "Actions", "hu": "Műveletek"},

    # Filter chips
    "filter_all": {"de": "Alle", "en": "All", "hu": "Összes"},
    "filter_favorites": {"de": "Favoriten", "en": "Favorites", "hu": "Kedvencek"},
    "filter_recent": {"de": "Zuletzt hinzugefügt", "en": "Recently Added", "hu": "Legutóbb hozzáadva"},
    "filter_unplayed": {"de": "Nicht gehört", "en": "Unplayed", "hu": "Még nem játszott"},
    "filter_artist": {"de": "Künstler", "en": "Artist", "hu": "Előadó"},
    "filter_year": {"de": "Jahr", "en": "Year", "hu": "Év"},
    "filter_genre": {"de": "Genre", "en": "Genre", "hu": "Műfaj"},
    "find_duplicates": {"de": "Duplikate prüfen", "en": "Find Duplicates", "hu": "Duplikátumok keresése"},

    # Details sidebar
    "details_title": {"de": "Song-Details", "en": "Track Details", "hu": "Dal részletei"},
    "details_size": {"de": "Größe", "en": "Size", "hu": "Méret"},
    "details_played": {"de": "Gespielt", "en": "Played", "hu": "Lejátszva"},
    "details_location": {"de": "Speicherort", "en": "Location", "hu": "Fájl helye"},
    "details_delete": {"de": "Löschen", "en": "Delete", "hu": "Törlés"},
    "details_clean": {"de": "Clean", "en": "Clean", "hu": "Tisztítás"},
    "details_cover": {"de": "Cover", "en": "Cover", "hu": "Borító"},
    "details_folder": {"de": "Ordner", "en": "Folder", "hu": "Mappa"},
    "details_similar": {"de": "Ähnliche Songs", "en": "Similar Tracks", "hu": "Hasonló dalok"},
    "select_song_hint": {
        "de": "Wähle einen Song aus der Bibliothek",
        "en": "Select a song from the library",
        "hu": "Válassz egy dalt a könyvtárból",
    },
    "no_track_selected": {
        "de": "Kein Song ausgewählt",
        "en": "No track selected",
        "hu": "Nincs kiválasztott dal",
    },
    "unnamed_title": {
        "de": "Unbekannter Titel",
        "en": "Unknown Title",
        "hu": "Ismeretlen cím",
    },
    "unnamed_artist": {
        "de": "Unbekannter Künstler",
        "en": "Unknown Artist",
        "hu": "Ismeretlen előadó",
    },
    "remove_favorites": {
        "de": "Aus Favoriten",
        "en": "Remove Favorite",
        "hu": "Eltávolítás a kedvencekből",
    },
    "unnamed_album": {
        "de": "Unbekanntes Album",
        "en": "Unknown Album",
        "hu": "Ismeretlen album",
    },

    # Library Toolbar Buttons
    "btn_sync": {"de": "Sync", "en": "Sync", "hu": "Szinkron"},
    "btn_covers": {"de": "Covers", "en": "Covers", "hu": "Borítók"},
    "btn_clean": {"de": "Clean", "en": "Clean", "hu": "Tisztítás"},
    "tip_clean": {
        "de": "Markierte Tracks automatisch bereinigen (YouTube-Müll entfernen, Artist/Titel trennen)",
        "en": "Automatically clean selected tracks (remove YouTube junk, split artist/title)",
        "hu": "Kijelölt dalok automatikus tisztítása (YouTube felesleg eltávolítása)",
    },
    "btn_duplicates": {"de": "Duplikate", "en": "Duplicates", "hu": "Duplikátumok"},
    "btn_list": {"de": "Liste", "en": "List", "hu": "Lista"},
    "btn_grid": {"de": "Raster", "en": "Grid", "hu": "Rács"},
    "search_placeholder_short": {"de": "Suchen …", "en": "Search …", "hu": "Keresés …"},
    "queue_empty_summary": {"de": "Keine aktiven Downloads.", "en": "No active downloads.", "hu": "Nincsenek aktív letöltések."},
    "delete_playlist": {"de": "Playlist löschen", "en": "Delete Playlist", "hu": "Lejátszási lista törlése"},
    "sync_playlist": {"de": "Playlist synchronisieren", "en": "Sync Playlist", "hu": "Lejátszási lista szinkronizálása"},
    "dl_status_ready": {"de": "Bereit", "en": "Ready", "hu": "Kész"},

    # Player bar & Controls
    "player_prev": {"de": "Vorheriger Song", "en": "Previous Track", "hu": "Előző dal"},
    "player_play": {"de": "Abspielen", "en": "Play", "hu": "Lejátszás"},
    "player_pause": {"de": "Pause", "en": "Pause", "hu": "Szünet"},
    "player_next": {"de": "Nächster Song", "en": "Next Track", "hu": "Következő dal"},
    "player_shuffle": {"de": "Zufallswiedergabe", "en": "Shuffle", "hu": "Véletlenszerű lejátszás"},
    "player_repeat": {"de": "Wiederholen", "en": "Repeat", "hu": "Ismétlés"},
    "player_mute": {"de": "Stummschalten", "en": "Mute", "hu": "Némítás"},
    "player_volume": {"de": "Lautstärke", "en": "Volume", "hu": "Hangerő"},
    "lyrics_btn": {"de": "Songtext", "en": "Lyrics", "hu": "Dalszöveg"},

    # Downloader Page
    "downloader_title": {"de": "Playlist & Song Import", "en": "Playlist & Song Import", "hu": "Lejátszási lista & Dal importálása"},
    "downloader_sub": {
        "de": "Unterstützt YouTube, YouTube Music und Spotify Playlists oder Einzellinks",
        "en": "Supports YouTube, YouTube Music and Spotify playlists or single links",
        "hu": "Támogatja a YouTube, YouTube Music és Spotify lejátszási listákat vagy linkeket",
    },
    "downloader_input_placeholder": {
        "de": "Link hier einfügen (z. B. https://music.youtube.com/playlist?list=...) …",
        "en": "Paste link here (e.g. https://music.youtube.com/playlist?list=...) …",
        "hu": "Illeszd be a linket ide (pl. https://music.youtube.com/playlist?list=...) …",
    },
    "btn_analyze": {"de": "Analysieren", "en": "Analyze", "hu": "Elemzés"},
    "btn_to_discover": {"de": "Zur YouTube-Suche", "en": "To YouTube Search", "hu": "YouTube kereséshez"},
    "btn_toggle_all": {"de": "Alle an / ab", "en": "Toggle All", "hu": "Mind kijelöl / felold"},
    "btn_only_new": {"de": "Nur neue Songs", "en": "Only New Songs", "hu": "Csak új dalok"},
    "dl_ready_analyze": {"de": "Bereit für Link-Analyse.", "en": "Ready for link analysis.", "hu": "Készen áll az elemzésre."},
    "btn_start_download": {"de": "Download starten", "en": "Start Download", "hu": "Letöltés indítása"},
    "btn_search": {"de": "Suchen", "en": "Search", "hu": "Keresés"},
    "btn_download": {"de": "Download starten", "en": "Start Download", "hu": "Letöltés indítása"},
    "dl_status_queued": {"de": "Warteschlange", "en": "Queued", "hu": "Sorban áll"},
    "dl_status_downloading": {"de": "Wird geladen…", "en": "Downloading…", "hu": "Letöltés folyamatban…"},
    "dl_status_done": {"de": "Fertig", "en": "Done", "hu": "Kész"},
    "dl_status_error": {"de": "Fehler", "en": "Error", "hu": "Hiba"},
    "dl_clear_done": {"de": "Abgeschlossene entfernen", "en": "Clear completed", "hu": "Befejezettek törlése"},

    # Discover Page
    "discover_title": {
        "de": "Musik entdecken & direkt suchen",
        "en": "Discover & Search Music Directly",
        "hu": "Zene felfedezése és közvetlen keresése",
    },
    "discover_sub": {
        "de": "Finde Songs, Alben, Playlists oder Künstler direkt auf YouTube – ohne Browser.",
        "en": "Find songs, albums, playlists or artists directly on YouTube – without a browser.",
        "hu": "Keress dalokat, albumokat vagy előadókat a YouTube-on – böngésző nélkül.",
    },
    "discover_search_prompt": {
        "de": "Suchbegriff eingeben (z. B. The Weeknd, Hans Zimmer, Lofi Beats Playlist) …",
        "en": "Enter search term (e.g. The Weeknd, Hans Zimmer, Lofi Beats) …",
        "hu": "Adj meg keresőkifejezést (pl. The Weeknd, Hans Zimmer, Lofi Beats) …",
    },
    "discover_all": {"de": "Alle", "en": "All", "hu": "Összes"},
    "discover_songs": {"de": "Songs", "en": "Songs", "hu": "Dalok"},
    "discover_playlists": {"de": "Playlists", "en": "Playlists", "hu": "Lejátszási listák"},
    "discover_ready": {"de": "Bereit zum Suchen.", "en": "Ready to search.", "hu": "Készen áll a keresésre."},
    "btn_preview": {"de": "Vorhören", "en": "Preview", "hu": "Előhallgatás"},
    "btn_add_to_library": {"de": "In Bibliothek laden", "en": "Add to Library", "hu": "Hozzáadás a könyvtárhoz"},

    # Downloads Queue Page
    "queue_title": {
        "de": "Aktive Downloads & Warteschlange",
        "en": "Active Downloads & Queue",
        "hu": "Aktív letöltések és Várólista",
    },
    "queue_active": {"de": "Aktiv", "en": "Active", "hu": "Aktív"},
    "queue_waiting": {"de": "In Warteschlange", "en": "Queued", "hu": "Sorban áll"},
    "queue_done": {"de": "Fertig", "en": "Done", "hu": "Kész"},
    "queue_failed": {"de": "Fehlgeschlagen", "en": "Failed", "hu": "Sikertelen"},
    "btn_pause": {"de": "Pausieren", "en": "Pause", "hu": "Szünet"},
    "btn_resume": {"de": "Fortsetzen", "en": "Resume", "hu": "Folytatás"},
    "btn_retry": {"de": "Wiederholen", "en": "Retry", "hu": "Újra"},
    "btn_cancel": {"de": "Abbrechen", "en": "Cancel", "hu": "Mégse"},

    # Playlists Page
    "playlists_title": {"de": "Playlists", "en": "Playlists", "hu": "Lejátszási listák"},
    "btn_new_playlist": {"de": "＋ Neue Playlist anlegen", "en": "＋ Create New Playlist", "hu": "＋ Új lejátszási lista"},
    "btn_back_playlists": {"de": "← Zurück zu allen Playlists", "en": "← Back to all Playlists", "hu": "← Vissza a listákhoz"},
    "btn_play_all": {"de": "Alle abspielen", "en": "Play All", "hu": "Összes lejátszása"},
    "empty_playlists": {
        "de": "Erstelle Playlists, um deine Songs nach Stimmung oder Genre zu ordnen.",
        "en": "Create playlists to organize your songs by mood or genre.",
        "hu": "Hozz létre lejátszási listákat hangulat vagy műfaj szerint.",
    },

    # Settings Page
    "settings_title": {"de": "Einstellungen", "en": "Settings", "hu": "Beállítások"},
    "settings_language": {"de": "Sprache / Language / Nyelv", "en": "Language / Sprache / Nyelv", "hu": "Nyelv / Language / Sprache"},
    "settings_music_folder": {"de": "Musikordner", "en": "Music Folder", "hu": "Zenei mappa"},
    "settings_choose_folder": {"de": "Ordner auswählen …", "en": "Select Folder…", "hu": "Mappa kiválasztása…"},
    "settings_quality": {
        "de": "Standard-Audioqualität (kbps)",
        "en": "Default Audio Quality (kbps)",
        "hu": "Alapértelmezett hangminőség (kbps)",
    },
    "settings_parallel": {
        "de": "Gleichzeitige Downloads (max. 3 empfohlen)",
        "en": "Concurrent Downloads (max. 3 recommended)",
        "hu": "Párhuzamos letöltések (max. 3 ajánlott)",
    },
    "settings_auto_cover": {
        "de": "Albumcover automatisch online laden (iTunes, Deezer)",
        "en": "Automatically download album art online (iTunes, Deezer)",
        "hu": "Albumborítók automatikus letöltése az internetről (iTunes, Deezer)",
    },
    "settings_auto_meta": {
        "de": "Metadaten automatisch aktualisieren",
        "en": "Update metadata automatically",
        "hu": "Metaadatok automatikus frissítése",
    },
    "settings_only_new": {
        "de": "Nur neue Songs laden (Duplikate überspringen)",
        "en": "Download only new songs (skip duplicates)",
        "hu": "Csak új dalok letöltése (duplikátumok kihagyása)",
    },
    "settings_cleanup_startup": {
        "de": "Fehlende Dateien beim Programmstart bereinigen",
        "en": "Clean up missing files on startup",
        "hu": "Hiányzó fájlok eltávolítása indításkor",
    },
    "settings_auto_sync_pl": {
        "de": "Playlists automatisch synchronisieren",
        "en": "Sync playlists automatically",
        "hu": "Lejátszási listák automatikus szinkronizálása",
    },
    "btn_save": {"de": "Speichern", "en": "Save", "hu": "Mentés"},
    "btn_close": {"de": "Fertig / Schließen", "en": "Done / Close", "hu": "Kész / Bezárás"},
    "settings_saved_title": {"de": "Gespeichert", "en": "Saved", "hu": "Elmentve"},
    "settings_saved_msg": {
        "de": "Einstellungen erfolgreich gespeichert.",
        "en": "Settings saved successfully.",
        "hu": "A beállítások sikeresen mentve.",
    },
    "lang_restart_notice": {
        "de": "Die Sprache wurde geändert. Einige Elemente werden nach einem Neustart vollständig übernommen.",
        "en": "Language changed. Some elements will fully update after restarting the app.",
        "hu": "A nyelv megváltozott. Néhány felület az alkalmazás újraindítása után frissül teljesen.",
    },

    # Duplicates Dialog
    "dup_dialog_title": {
        "de": "Duplikate in der Bibliothek verwalten",
        "en": "Manage Duplicates in Library",
        "hu": "Duplikátumok kezelése a könyvtárban",
    },
    "dup_none_found": {
        "de": "Es wurden keine doppelten Titel in deiner Bibliothek gefunden.",
        "en": "No duplicate tracks were found in your library.",
        "hu": "Nem találhatók duplikált dalok a könyvtárban.",
    },
    "dup_delete_disk_btn": {
        "de": "Von Festplatte löschen",
        "en": "Delete from Disk",
        "hu": "Törlés a lemezről",
    },
    "dup_remove_lib_btn": {
        "de": "Nur aus Bibliothek entfernen",
        "en": "Remove from Library only",
        "hu": "Csak a könyvtárból eltávolítás",
    },
    "dup_cancel_btn": {"de": "Abbrechen", "en": "Cancel", "hu": "Mégse"},
    "dup_keep_best": {"de": "Beste Qualität behalten", "en": "Keep Best Quality", "hu": "Legjobb minőség megtartása"},

    # Context Menu & Actions
    "ctx_play": {"de": "Abspielen", "en": "Play", "hu": "Lejátszás"},
    "ctx_add_to_playlist": {"de": "Zu Playlist hinzufügen", "en": "Add to Playlist", "hu": "Hozzáadás lejátszási listához"},
    "ctx_toggle_fav": {"de": "Favorit umschalten", "en": "Toggle Favorite", "hu": "Kedvenc hozzáadása/törlése"},
    "ctx_open_folder": {"de": "In Dateimanager anzeigen", "en": "Show in File Manager", "hu": "Megnyitás a fájlkezelőben"},
    "ctx_edit_meta": {"de": "Metadaten bearbeiten", "en": "Edit Metadata", "hu": "Metaadatok szerkesztése"},
    "ctx_delete_track": {"de": "Song löschen", "en": "Delete Track", "hu": "Dal törlése"},

    # Empty states
    "empty_library_title": {
        "de": "Deine Bibliothek ist noch leer",
        "en": "Your library is still empty",
        "hu": "A könyvtárad még üres",
    },
    "empty_library_subtitle": {
        "de": "Lade Musik über den Downloader herunter oder kopiere MP3-Dateien in deinen Musikordner.",
        "en": "Download music using the Downloader or copy MP3 files into your music folder.",
        "hu": "Tölts le zenéket a Letöltővel, vagy másolj MP3 fájlokat a zenei mappádba.",
    },
    "empty_favorites_title": {
        "de": "Noch keine Favoriten vorhanden",
        "en": "No favorites yet",
        "hu": "Még nincsenek kedvencek",
    },
    "empty_favorites_subtitle": {
        "de": "Markiere Songs mit Rechtsklick in der Bibliothek als Favorit.",
        "en": "Right-click any song in your library to mark it as a favorite.",
        "hu": "Kattints jobb gombbal bármelyik dalra a könyvtárban a kedvencekhez adáshoz.",
    },
}


def get_language() -> str:
    """Return currently active language code ('de', 'en', 'hu')."""
    return _CURRENT_LANGUAGE


def set_language(lang_code: str):
    """Set the active language."""
    global _CURRENT_LANGUAGE
    if lang_code in LANGUAGES:
        _CURRENT_LANGUAGE = lang_code
    else:
        _CURRENT_LANGUAGE = DEFAULT_LANGUAGE


def tr(key: str, default: str = None, **kwargs: Any) -> str:
    """
    Translate a message key into current active language.
    Falls back to German (default) or key string if not found.
    Supports kwargs formatting (e.g. {count}, {tracks}).
    """
    entry = TRANSLATIONS.get(key)
    if entry:
        text = entry.get(_CURRENT_LANGUAGE) or entry.get(DEFAULT_LANGUAGE) or (default if default is not None else key)
    else:
        text = default if default is not None else key

    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


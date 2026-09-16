"""SQLite storage and automatic schema migrations for M-Player."""

from __future__ import annotations

import shutil
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from metadata import safe_name


class MusicDatabase:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._migrate()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self._connection() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS tracks (
                id INTEGER PRIMARY KEY, title TEXT NOT NULL, artist TEXT NOT NULL, album TEXT NOT NULL,
                year TEXT, track_number INTEGER, genre TEXT, source_url TEXT, file_path TEXT NOT NULL UNIQUE,
                added_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            existing = {row[1] for row in conn.execute("PRAGMA table_info(tracks)")}
            for name, definition in {"duration": "REAL NOT NULL DEFAULT 0", "bitrate": "INTEGER NOT NULL DEFAULT 0", "favorite": "INTEGER NOT NULL DEFAULT 0", "collection": "TEXT NOT NULL DEFAULT ''", "play_count": "INTEGER NOT NULL DEFAULT 0"}.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE tracks ADD COLUMN {name} {definition}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_favorite ON tracks(favorite)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_added ON tracks(added_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_play_count ON tracks(play_count)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_collection ON tracks(collection)")
            conn.execute("CREATE TABLE IF NOT EXISTS playlists (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)")
            conn.execute("""CREATE TABLE IF NOT EXISTS playlist_tracks (
                playlist_id INTEGER NOT NULL, track_id INTEGER NOT NULL, position INTEGER NOT NULL,
                PRIMARY KEY (playlist_id, track_id), FOREIGN KEY (playlist_id) REFERENCES playlists(id),
                FOREIGN KEY (track_id) REFERENCES tracks(id)
            )""")
            conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            conn.execute("""CREATE TABLE IF NOT EXISTS downloads (
                id INTEGER PRIMARY KEY, url TEXT NOT NULL, title TEXT NOT NULL, artist TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'Bereit', progress REAL NOT NULL DEFAULT 0,
                speed TEXT NOT NULL DEFAULT '', eta TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")
            existing_dl = {row[1] for row in conn.execute("PRAGMA table_info(downloads)")}
            if "playlist" not in existing_dl:
                conn.execute("ALTER TABLE downloads ADD COLUMN playlist TEXT NOT NULL DEFAULT ''")

            conn.execute("""CREATE TABLE IF NOT EXISTS favorites (
                id INTEGER PRIMARY KEY, track_id INTEGER NOT NULL UNIQUE,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (track_id) REFERENCES tracks(id)
            )""")

    def upsert(self, track: object, file_path: Path, duration: float = 0, bitrate: int = 0) -> None:
        values = (track.title, track.artist, track.album, track.year, track.track_number, track.genre, track.source_url, str(file_path), duration, bitrate, track.collection)
        with self._connection() as conn:
            conn.execute("""INSERT INTO tracks (title, artist, album, year, track_number, genre, source_url, file_path, duration, bitrate, collection)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(file_path) DO UPDATE SET
                title=excluded.title, artist=excluded.artist, album=excluded.album, year=excluded.year,
                track_number=excluded.track_number, genre=excluded.genre, source_url=excluded.source_url,
                duration=excluded.duration, bitrate=excluded.bitrate, collection=excluded.collection""", values)

    def increment_play_count(self, track_id: int) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE tracks SET play_count = play_count + 1 WHERE id = ?", (track_id,))

    def tracks(self, query: str = "", favorites: bool = False, filter_chip: str = "Alle") -> list[sqlite3.Row]:
        where, values = [], []
        order_by = "ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE, track_number, title COLLATE NOCASE"

        if query:
            where.append("(title LIKE ? OR artist LIKE ? OR album LIKE ? OR genre LIKE ? OR collection LIKE ?)")
            values.extend([f"%{query}%"] * 5)

        if favorites or filter_chip == "Favoriten":
            where.append("favorite = 1")
        elif filter_chip == "Zuletzt hinzugefügt":
            order_by = "ORDER BY added_at DESC, id DESC"
        elif filter_chip == "Nicht gehört":
            where.append("play_count = 0")
        elif filter_chip == "Playlists":
            where.append("collection != ''")
        elif filter_chip.startswith("Künstler:"):
            where.append("artist = ?")
            values.append(filter_chip.split(":", 1)[1].strip())
        elif filter_chip.startswith("Jahr:"):
            where.append("year = ?")
            values.append(filter_chip.split(":", 1)[1].strip())
        elif filter_chip.startswith("Genre:"):
            where.append("genre = ?")
            values.append(filter_chip.split(":", 1)[1].strip())

        clause = " WHERE " + " AND ".join(where) if where else ""
        with self._connection() as conn:
            return conn.execute("SELECT * FROM tracks" + clause + " " + order_by, values).fetchall()

    def search(self, text: str = "", artist: str = "", album: str = "", genre: str = "") -> list[sqlite3.Row]:
        return self.tracks(" ".join(part for part in (text, artist, album, genre) if part))

    def values_for(self, column: str) -> list[str]:
        if column not in {"artist", "album", "genre"}:
            raise ValueError("Ungültige Filterspalte")
        with self._connection() as conn:
            return [row[0] for row in conn.execute(f"SELECT DISTINCT {column} FROM tracks WHERE {column} != '' ORDER BY {column} COLLATE NOCASE")]

    def toggle_favorite(self, track_id: int) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE tracks SET favorite = 1 - favorite WHERE id = ?", (track_id,))
            fav = conn.execute("SELECT favorite FROM tracks WHERE id = ?", (track_id,)).fetchone()
            if fav and fav[0] == 1:
                conn.execute("INSERT OR IGNORE INTO favorites(track_id) VALUES (?)", (track_id,))
            else:
                conn.execute("DELETE FROM favorites WHERE track_id = ?", (track_id,))

    def update_track_tags(self, track_id: int, title: str, artist: str, album: str, year: str = "", genre: str = "") -> None:
        with self._connection() as conn:
            row = conn.execute("SELECT file_path FROM tracks WHERE id = ?", (track_id,)).fetchone()
            if not row:
                return
            conn.execute("UPDATE tracks SET title = ?, artist = ?, album = ?, year = ?, genre = ? WHERE id = ?",
                         (title.strip(), artist.strip(), album.strip(), year.strip(), genre.strip(), track_id))
            file_path = Path(row[0])
            if file_path.exists():
                try:
                    from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON
                    tags = ID3(file_path)
                    tags["TIT2"] = TIT2(encoding=3, text=title.strip())
                    tags["TPE1"] = TPE1(encoding=3, text=artist.strip())
                    tags["TALB"] = TALB(encoding=3, text=album.strip())
                    if year: tags["TDRC"] = TDRC(encoding=3, text=year.strip())
                    if genre: tags["TCON"] = TCON(encoding=3, text=genre.strip())
                    tags.save(file_path, v2_version=3)
                except Exception:
                    pass

    def record_download(self, url: str, title: str, artist: str = "", playlist: str = "", status: str = "Bereit") -> None:
        with self._connection() as conn:
            conn.execute("INSERT INTO downloads (url, title, artist, playlist, status, progress) VALUES (?, ?, ?, ?, ?, 0)",
                         (url, title, artist, playlist, status))

    def update_download(self, url: str, status: str, progress: float = 0, speed: str = "", eta: str = "") -> None:
        with self._connection() as conn:
            conn.execute("""UPDATE downloads SET status = ?, progress = ?, speed = ?, eta = ?
                            WHERE id = (SELECT id FROM downloads WHERE url = ? ORDER BY id DESC LIMIT 1)""",
                         (status, progress, speed, eta, url))

    def get_downloads(self) -> list[sqlite3.Row]:
        with self._connection() as conn:
            return conn.execute("SELECT * FROM downloads ORDER BY id DESC LIMIT 100").fetchall()

    def queue_stats(self) -> dict:
        with self._connection() as conn:
            rows = conn.execute("SELECT status, COUNT(*) as cnt FROM downloads GROUP BY status").fetchall()
            status_map = {r["status"]: r["cnt"] for r in rows}
            aktiv = status_map.get("Lädt...", 0)
            wartend = status_map.get("In Warteschlange", 0) + status_map.get("Bereit", 0)
            fertig = status_map.get("Fertig", 0)
            fehlgeschlagen = status_map.get("Fehler", 0) + status_map.get("Abgebrochen", 0) + status_map.get("Fehlgeschlagen", 0)
            return {"aktiv": aktiv, "wartend": wartend, "fertig": fertig, "fehlgeschlagen": fehlgeschlagen}

    def stats(self) -> sqlite3.Row:
        with self._connection() as conn:
            return conn.execute("SELECT COUNT(*) songs, COUNT(DISTINCT album) albums, COUNT(DISTINCT artist) artists, COALESCE(SUM(duration), 0) duration FROM tracks").fetchone()

    def playlist_names(self) -> list[str]:
        with self._connection() as conn:
            return [row[0] for row in conn.execute("SELECT name FROM playlists ORDER BY name COLLATE NOCASE")]

    def create_playlist(self, name: str) -> None:
        with self._connection() as conn:
            conn.execute("INSERT OR IGNORE INTO playlists(name) VALUES (?)", (name.strip(),))

    def add_to_playlist(self, name: str, track_id: int) -> None:
        self.create_playlist(name)
        with self._connection() as conn:
            playlist_id = conn.execute("SELECT id FROM playlists WHERE name = ?", (name,)).fetchone()[0]
            position = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,)).fetchone()[0]
            conn.execute("INSERT OR IGNORE INTO playlist_tracks(playlist_id, track_id, position) VALUES (?, ?, ?)", (playlist_id, track_id, position))

    def playlist_tracks(self, name: str) -> list[sqlite3.Row]:
        with self._connection() as conn:
            return conn.execute("""SELECT tracks.* FROM tracks JOIN playlist_tracks ON tracks.id = playlist_tracks.track_id
                JOIN playlists ON playlists.id = playlist_tracks.playlist_id WHERE playlists.name = ? ORDER BY playlist_tracks.position""", (name,)).fetchall()

    def get_setting(self, key: str, default: str = "") -> str:
        with self._connection() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        with self._connection() as conn:
            conn.execute("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))

    def load_all_settings(self) -> dict:
        defaults = {
            "music_folder": str(self.path.parent),
            "quality": "320",
            "parallel": "3",
            "auto_cover": "1",
            "auto_metadata": "1",
            "only_new": "1",
            "cleanup_missing_startup": "0",
            "auto_sync_playlist": "0",
            "shuffle": "0",
            "repeat": "0",
            "volume": "75"
        }
        with self._connection() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
            for r in rows:
                defaults[r["key"]] = r["value"]
        return defaults

    def save_settings_dict(self, data: dict) -> None:
        with self._connection() as conn:
            conn.executemany("INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", [(k, str(v)) for k, v in data.items()])

    def delete_track(self, track_id: int, delete_file: bool = False) -> bool:
        with self._connection() as conn:
            row = conn.execute("SELECT file_path FROM tracks WHERE id = ?", (track_id,)).fetchone()
            if not row:
                return False
            if delete_file:
                file_path = Path(row[0])
                if file_path.exists():
                    try:
                        file_path.unlink()
                    except OSError:
                        pass
            conn.execute("DELETE FROM playlist_tracks WHERE track_id = ?", (track_id,))
            conn.execute("DELETE FROM favorites WHERE track_id = ?", (track_id,))
            conn.execute("DELETE FROM tracks WHERE id = ?", (track_id,))
            return True

    def delete_playlist(self, name: str, music_root: Path) -> bool:
        with self._connection() as conn:
            p_row = conn.execute("SELECT id FROM playlists WHERE name = ?", (name,)).fetchone()
            if p_row:
                conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (p_row[0],))
                conn.execute("DELETE FROM playlists WHERE id = ?", (p_row[0],))
            p_dir = Path(music_root) / safe_name(name, "playlist")
            if p_dir.exists() and p_dir.is_dir():
                try:
                    shutil.rmtree(p_dir)
                except OSError:
                    pass
            all_tracks = conn.execute("SELECT id, file_path FROM tracks WHERE collection = ?", (name,)).fetchall()
            for t_id, f_path in all_tracks:
                if not Path(f_path).exists():
                    conn.execute("DELETE FROM favorites WHERE track_id = ?", (t_id,))
                    conn.execute("DELETE FROM tracks WHERE id = ?", (t_id,))
            return True

    def sync_library(self, music_root: Path, progress_callback=None) -> tuple[int, int]:
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3
        from metadata import TrackMetadata

        music_root = Path(music_root)
        files = list(music_root.rglob("*.mp3"))
        total = len(files)
        added, removed = 0, 0

        with self._connection() as conn:
            db_tracks = conn.execute("SELECT id, file_path FROM tracks").fetchall()
            for t_id, f_path in db_tracks:
                if not Path(f_path).exists():
                    conn.execute("DELETE FROM playlist_tracks WHERE track_id = ?", (t_id,))
                    conn.execute("DELETE FROM favorites WHERE track_id = ?", (t_id,))
                    conn.execute("DELETE FROM tracks WHERE id = ?", (t_id,))
                    removed += 1

            existing_paths = {row[1] for row in conn.execute("SELECT id, file_path FROM tracks")}

            for i, file_path in enumerate(files, 1):
                if progress_callback:
                    progress_callback(i, total, file_path.stem)
                if str(file_path) in existing_paths:
                    continue

                try:
                    audio = MP3(file_path)
                    tags = ID3(file_path)
                    title = str(tags.get("TIT2", file_path.stem))
                    artist = str(tags.get("TPE1", "Unbekannter Artist"))
                    album = str(tags.get("TALB", file_path.parent.name))
                    year = str(tags.get("TDRC", ""))
                    genre = str(tags.get("TCON", ""))
                    collection = file_path.parent.name
                    duration = audio.info.length if audio.info else 0
                    bitrate = int(getattr(audio.info, "bitrate", 0) / 1000) if audio.info else 320

                    track = TrackMetadata(
                        title=title, artist=artist, album=album, year=year,
                        genre=genre, collection=collection
                    )
                    conn.execute("""INSERT INTO tracks (title, artist, album, year, track_number, genre, source_url, file_path, duration, bitrate, collection)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(file_path) DO UPDATE SET
                        title=excluded.title, artist=excluded.artist, album=excluded.album, year=excluded.year,
                        track_number=excluded.track_number, genre=excluded.genre, source_url=excluded.source_url,
                        duration=excluded.duration, bitrate=excluded.bitrate, collection=excluded.collection""",
                        (track.title, track.artist, track.album, track.year, track.track_number, track.genre, track.source_url, str(file_path), duration, bitrate, track.collection))
                    if collection and collection not in ("Einzeltitel", "Single", music_root.name, ".covers"):
                        t_row = conn.execute("SELECT id FROM tracks WHERE file_path = ?", (str(file_path),)).fetchone()
                        if t_row:
                            conn.execute("INSERT OR IGNORE INTO playlists(name) VALUES (?)", (collection.strip(),))
                            pl_id = conn.execute("SELECT id FROM playlists WHERE name = ?", (collection.strip(),)).fetchone()[0]
                            pos = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM playlist_tracks WHERE playlist_id = ?", (pl_id,)).fetchone()[0]
                            conn.execute("INSERT OR IGNORE INTO playlist_tracks(playlist_id, track_id, position) VALUES (?, ?, ?)", (pl_id, t_row[0], pos))
                    added += 1
                except Exception:
                    continue

        return added, removed

    def dashboard_stats(self, music_root: Path) -> dict:
        with self._connection() as conn:
            counts = conn.execute("""SELECT
                COUNT(*) as songs,
                COUNT(DISTINCT album) as albums,
                COUNT(DISTINCT artist) as artists,
                COALESCE(SUM(duration), 0) as duration
                FROM tracks""").fetchone()

            pl_count = conn.execute("SELECT COUNT(*) FROM playlists").fetchone()[0]
            files = conn.execute("SELECT file_path FROM tracks").fetchall()
            total_bytes = sum(Path(f[0]).stat().st_size for f in files if Path(f[0]).exists())

            return {
                "songs": counts["songs"],
                "albums": counts["albums"],
                "artists": counts["artists"],
                "playlists": pl_count,
                "duration": counts["duration"],
                "size_bytes": total_bytes
            }

    def retry_download(self, download_id: int) -> None:
        with self._connection() as conn:
            conn.execute("UPDATE downloads SET status = 'Bereit', progress = 0, speed = '', eta = '' WHERE id = ?", (download_id,))

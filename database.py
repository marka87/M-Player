"""SQLite storage and automatic schema migrations for M-Player."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path


class MusicDatabase:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._migrate()

    @contextmanager
    def _connection(self):
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
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
            for name, definition in {"duration": "REAL NOT NULL DEFAULT 0", "bitrate": "INTEGER NOT NULL DEFAULT 0", "favorite": "INTEGER NOT NULL DEFAULT 0", "collection": "TEXT NOT NULL DEFAULT ''"}.items():
                if name not in existing:
                    conn.execute(f"ALTER TABLE tracks ADD COLUMN {name} {definition}")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_artist ON tracks(artist)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_album ON tracks(album)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tracks_genre ON tracks(genre)")
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

    def tracks(self, query: str = "", favorites: bool = False) -> list[sqlite3.Row]:
        where, values = [], []
        if query:
            where.append("(title LIKE ? OR artist LIKE ? OR album LIKE ? OR genre LIKE ? OR collection LIKE ?)")
            values.extend([f"%{query}%"] * 5)
        if favorites:
            where.append("favorite = 1")
        clause = " WHERE " + " AND ".join(where) if where else ""
        with self._connection() as conn:
            return conn.execute("SELECT * FROM tracks" + clause + " ORDER BY artist COLLATE NOCASE, album COLLATE NOCASE, track_number, title COLLATE NOCASE", values).fetchall()

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

    def record_download(self, url: str, title: str, artist: str = "", status: str = "Bereit") -> None:
        with self._connection() as conn:
            conn.execute("INSERT INTO downloads (url, title, artist, status, progress) VALUES (?, ?, ?, ?, 0)",
                         (url, title, artist, status))

    def update_download(self, url: str, status: str, progress: float = 0, speed: str = "", eta: str = "") -> None:
        with self._connection() as conn:
            conn.execute("""UPDATE downloads SET status = ?, progress = ?, speed = ?, eta = ?
                            WHERE id = (SELECT id FROM downloads WHERE url = ? ORDER BY id DESC LIMIT 1)""",
                         (status, progress, speed, eta, url))

    def get_downloads(self) -> list[sqlite3.Row]:
        with self._connection() as conn:
            return conn.execute("SELECT * FROM downloads ORDER BY id DESC LIMIT 100").fetchall()

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

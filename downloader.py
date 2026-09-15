"""Fetches YouTube audio and Spotify metadata, then files tracks locally."""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import uuid
import re
import urllib.request
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import spotipy
import yt_dlp
from spotipy.oauth2 import SpotifyClientCredentials

from database import MusicDatabase
from metadata import TrackMetadata, target_path, write_id3, save_playlist_json

Progress = Callable[[float, str, str, str], None]


class DownloadFailure(RuntimeError):
    pass


class DownloadCancelled(RuntimeError):
    pass


class MusicDownloader:
    def __init__(self, library_root: Path | str, database: MusicDatabase, cancel_event: threading.Event | None = None, resume_event: threading.Event | None = None) -> None:
        self.library_root = Path(library_root)
        self.database = database
        self.cancel_event = cancel_event or threading.Event()
        self.resume_event = resume_event or threading.Event()
        if resume_event is None:
            self.resume_event.set()

    @staticmethod
    def is_spotify(url: str) -> bool:
        return "open.spotify.com/" in url

    def download(self, url: str, progress: Progress, status: Callable[[str], None]) -> tuple[int, list[str]]:
        sources = self._spotify_sources(url) if self.is_spotify(url) else self._youtube_sources(url)
        self._check_cancelled()
        completed, errors = 0, []
        total = len(sources)
        for index, source in enumerate(sources, 1):
            try:
                self._check_cancelled()
                status(f"{index}/{total}: {source.title}")
                self._download_one(source, index, total, progress)
                completed += 1
            except DownloadCancelled:
                raise
            except Exception as exc:  # One bad item must not stop a playlist.
                errors.append(f"{source.title}: {exc}")
        return completed, errors

    def _youtube_sources(self, url: str) -> list[TrackMetadata]:
        options = {"quiet": True, "extract_flat": True, "skip_download": True}
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
        except Exception as exc:
            raise DownloadFailure(f"YouTube-Link konnte nicht gelesen werden: {exc}") from exc
        entries = info.get("entries") if isinstance(info, dict) else None
        items = entries or [info]
        collection = info.get("title") if entries else info.get("playlist_title") or "Einzeltitel"
        sources = []
        for position, item in enumerate(items, 1):
            if not item:
                continue
            video_url = item.get("webpage_url") or item.get("url")
            if video_url and not video_url.startswith("http"):
                video_url = f"https://www.youtube.com/watch?v={item.get('id', video_url)}"
            if video_url:
                sources.append(TrackMetadata(
                    title=item.get("title") or "Unbekannter Titel",
                    artist=item.get("uploader") or item.get("channel") or "Unbekannter Artist",
                    album=item.get("album") or "Unbekanntes Album",
                    year=str(item.get("release_year") or item.get("upload_date", "")[:4]),
                    track_number=position,
                    genre=item.get("genre") or "",
                    cover_url=item.get("thumbnail") or "",
                    source_url=video_url,
                    collection=collection or "Einzeltitel",
                ))
        if not sources:
            raise DownloadFailure("Der Link enthält keine herunterladbaren Titel.")
        return sources

    def _spotify_public_track(self, url: str) -> TrackMetadata:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8", "ignore")
            title_m = re.search(r'property="og:title"\s+content="([^"]+)"', html)
            desc_m = re.search(r'property="og:description"\s+content="([^"]+)"', html)
            img_m = re.search(r'property="og:image"\s+content="([^"]+)"', html)
            title = title_m.group(1) if title_m else "Unbekannter Titel"
            artist, album, year = "Unbekannter Artist", "Unbekanntes Album", ""
            if desc_m:
                parts = [p.strip() for p in desc_m.group(1).split("·")]
                if parts:
                    artist = parts[0]
                if len(parts) >= 3 and parts[-1].strip().isdigit():
                    year = parts[-1].strip()
                if len(parts) >= 4:
                    album = parts[1]
            cover = img_m.group(1) if img_m else ""
            return TrackMetadata(
                title=title,
                artist=artist,
                album=album,
                year=year,
                cover_url=cover,
                source_url=f"ytsearch1:{title} {artist} audio",
            )
        except Exception as exc:
            raise DownloadFailure(f"Spotify-Track konnte nicht gelesen werden: {exc}") from exc

    def _spotify_sources(self, url: str) -> list[TrackMetadata]:
        if not os.getenv("SPOTIPY_CLIENT_ID") or not os.getenv("SPOTIPY_CLIENT_SECRET"):
            if "/track/" in url:
                return [self._spotify_public_track(url)]
            raise DownloadFailure("Für Spotify-Playlists werden SPOTIPY_CLIENT_ID und SPOTIPY_CLIENT_SECRET benötigt (einzelne Tracks funktionieren direkt).")
        try:
            spotify = spotipy.Spotify(auth_manager=SpotifyClientCredentials())
            parts = [part for part in urlparse(url).path.split("/") if part]
            if len(parts) < 2:
                raise DownloadFailure("Ungültiger Spotify-Link.")
            kind, spotify_id = parts[-2:]
            if kind == "track":
                tracks = [spotify.track(spotify_id)]
                collection = tracks[0].get("album", {}).get("name") or "Einzeltitel"
            elif kind == "playlist":
                collection = spotify.playlist(spotify_id, fields="name").get("name") or "Spotify-Playlist"
                tracks = []
                results = spotify.playlist_items(spotify_id, additional_types=("track",))
                while results:
                    tracks.extend(item["track"] for item in results["items"] if item.get("track"))
                    results = spotify.next(results) if results.get("next") else None
            else:
                raise DownloadFailure("Spotify-Link muss ein Track oder eine Playlist sein.")
        except DownloadFailure:
            raise
        except Exception as exc:
            raise DownloadFailure(f"Spotify-Metadaten konnten nicht geladen werden: {exc}") from exc
        sources = []
        for position, item in enumerate(tracks, 1):
            album = item.get("album") or {}
            images = album.get("images") or []
            sources.append(TrackMetadata(
                title=item.get("name") or "Unbekannter Titel",
                artist=", ".join(artist["name"] for artist in item.get("artists", []) if artist.get("name")) or "Unbekannter Artist",
                album=album.get("name") or "Unbekanntes Album",
                year=(album.get("release_date") or "")[:4],
                track_number=item.get("track_number") or position,
                genre="",
                cover_url=images[0].get("url", "") if images else "",
                source_url=f"ytsearch1:{item.get('name', '')} {' '.join(a.get('name', '') for a in item.get('artists', []))} audio",
                collection=collection,
            ))
        if not sources:
            raise DownloadFailure("Die Spotify-Playlist enthält keine Tracks.")
        return sources

    def _download_one(self, track: TrackMetadata, index: int, total: int, progress: Progress) -> None:
        with tempfile.TemporaryDirectory(prefix="offline_music_") as temp:
            temp_dir = Path(temp)
            job_name = uuid.uuid4().hex

            def hook(event: dict) -> None:
                self._check_cancelled()
                self._wait_if_paused()
                speed_val = event.get("speed") or 0
                speed_str = event.get("_speed_str") or (f"{speed_val / (1024 * 1024):.1f} MB/s" if speed_val else "--")
                eta_val = event.get("eta")
                eta_str = event.get("_eta_str") or (f"{int(eta_val)}s" if eta_val is not None else "--")
                if event.get("status") == "downloading":
                    downloaded = event.get("downloaded_bytes", 0)
                    expected = event.get("total_bytes") or event.get("total_bytes_estimate") or 1
                    ratio = ((index - 1) + (downloaded / expected)) / total
                    progress(ratio, track.title, speed_str, eta_str)
                elif event.get("status") == "finished":
                    progress(index / total, track.title, "Fertig", "0s")

            options = {
                "format": "bestaudio/best",
                "outtmpl": str(temp_dir / f"{job_name}.%(ext)s"),
                "noplaylist": True,
                "quiet": True,
                "no_warnings": True,
                "concurrent_fragment_downloads": 4,
                "progress_hooks": [hook],
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "320"}],
                "postprocessor_args": {"FFmpegExtractAudio": ["-codec:a", "libmp3lame", "-b:a", "320k"]},
            }
            if not shutil.which("ffmpeg"):
                for cand in Path.home().glob("AppData/Local/Microsoft/WinGet/Packages/*FFmpeg*/bin/ffmpeg.exe"):
                    if cand.is_file():
                        options["ffmpeg_location"] = str(cand)
                        break
            try:
                with yt_dlp.YoutubeDL(options) as ydl:
                    info = ydl.extract_info(track.source_url, download=True)
            except DownloadCancelled:
                raise
            except Exception as exc:
                raise DownloadFailure(f"Download fehlgeschlagen: {exc}") from exc
            files = list(temp_dir.glob("*.mp3"))
            if not files:
                raise DownloadFailure("yt-dlp hat keine MP3-Datei erzeugt. Ist ffmpeg im PATH?")
            self._check_cancelled()
            if not track.cover_url:
                track.cover_url = info.get("thumbnail") or ""
            if track.artist == "Unbekannter Artist":
                track.artist = info.get("artist") or info.get("uploader") or track.artist
            if track.album == "Unbekanntes Album":
                track.album = info.get("album") or track.album
            if not track.year:
                track.year = str(info.get("release_year") or info.get("upload_date", "")[:4])
            cover = write_id3(files[0], track)
            destination = target_path(self.library_root, track)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination = self._unused_path(destination)
            shutil.move(str(files[0]), destination)
            if cover and not (destination.parent / "cover.jpg").exists():
                (destination.parent / "cover.jpg").write_bytes(cover[0])
            save_playlist_json(destination.parent, track.collection or "Einzeltitel", track.source_url, total)
            from mutagen.mp3 import MP3
            audio = MP3(destination).info
            self.database.upsert(track, destination, audio.length, int(getattr(audio, "bitrate", 0) / 1000))
            if track.collection and track.collection not in ("Einzeltitel", "Single"):
                with self.database._connection() as conn:
                    row = conn.execute("SELECT id FROM tracks WHERE file_path = ?", (str(destination),)).fetchone()
                    if row:
                        self.database.add_to_playlist(track.collection, row[0])

    def _check_cancelled(self) -> None:
        if self.cancel_event.is_set():
            raise DownloadCancelled("Download wurde abgebrochen.")

    def _wait_if_paused(self) -> None:
        while not self.resume_event.wait(0.2):
            self._check_cancelled()

    @staticmethod
    def _unused_path(path: Path) -> Path:
        if not path.exists():
            return path
        count = 2
        while True:
            candidate = path.with_stem(f"{path.stem} ({count})")
            if not candidate.exists():
                return candidate
            count += 1

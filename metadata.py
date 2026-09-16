"""Metadata normalization, ID3 writing, cover download and safe paths."""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from mutagen.mp3 import MP3
from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TCON, TIT2, TPE1, TPE2, TRCK, TDRC


@dataclass
class TrackMetadata:
    title: str
    artist: str
    album: str = "Unbekanntes Album"
    year: str = ""
    track_number: int = 0
    genre: str = ""
    cover_url: str = ""
    source_url: str = ""
    collection: str = "Einzeltitel"
    duration: float = 0
    bitrate: int = 0


def safe_name(value: str, fallback: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return value[:120] or fallback


def target_path(root: Path, track: TrackMetadata) -> Path:
    playlist = safe_name(track.collection, "Einzeltitel")
    artist = safe_name(track.artist, "Unbekannter Artist")
    title = safe_name(track.title, "Unbekannter Titel")
    return root / playlist / f"{artist} - {title}.mp3"


def save_playlist_json(folder: Path, playlist_name: str, url: str, song_count: int) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    import datetime, json
    data = {
        "playlist_name": playlist_name,
        "youtube_url": url,
        "download_date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "song_count": song_count
    }
    (folder / "playlist.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def download_cover(url: str) -> tuple[bytes, str] | None:
    if not url.startswith(("https://", "http://")):
        return None
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read(10 * 1024 * 1024 + 1)
            mime = response.headers.get_content_type()
        if len(data) > 10 * 1024 * 1024 or mime not in {"image/jpeg", "image/png"}:
            return None
        return data, mime
    except OSError:
        return None


def write_id3(path: Path, track: TrackMetadata, cover_override: tuple[bytes, str] | None = None) -> tuple[bytes, str] | None:
    MP3(path).info  # Reject a renamed WebM/AAC file before it reaches the library.
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall("APIC")
    tags["TIT2"] = TIT2(encoding=3, text=track.title)
    tags["TPE1"] = TPE1(encoding=3, text=track.artist)
    album_name = track.collection if track.collection and track.collection != "Einzeltitel" else track.album
    tags["TALB"] = TALB(encoding=3, text=album_name)
    tags["TPE2"] = TPE2(encoding=3, text=album_name)
    if track.year:
        tags["TDRC"] = TDRC(encoding=3, text=track.year)
    if track.track_number:
        tags["TRCK"] = TRCK(encoding=3, text=str(track.track_number))
    if track.genre:
        tags["TCON"] = TCON(encoding=3, text=track.genre)
    cover = cover_override or download_cover(track.cover_url)
    if cover:
        data, mime = cover
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
    tags.save(path, v2_version=3)
    return cover


def find_or_fetch_cover(artist: str, album: str, music_root: Path, file_path: Path | None = None) -> Path | None:
    if file_path and file_path.parent:
        local_cover = file_path.parent / "cover.jpg"
        if local_cover.is_file():
            return local_cover
    from cover_enricher import CoverEnricher
    enricher = CoverEnricher(timeout=5)
    res = enricher.find_cover(artist, album, music_root=music_root)
    if res:
        cache_file = music_root / ".covers" / f"{safe_name(artist, 'artist')}-{safe_name(album, 'album')}.jpg"
        if cache_file.exists():
            return cache_file
    return None


def read_audio_tags(file_path: Path) -> TrackMetadata:
    """Read metadata tags, duration, and bitrate from MP3, FLAC, M4A, WAV."""
    title = file_path.stem
    artist = "Unbekannter Artist"
    album = file_path.parent.name if file_path.parent else "Unbekanntes Album"
    year = ""
    genre = ""
    duration = 0.0
    bitrate = 320

    try:
        from mutagen import File as MutagenFile
        audio = MutagenFile(file_path)
        if audio:
            if hasattr(audio, "info") and audio.info:
                duration = float(getattr(audio.info, "length", 0.0))
                raw_br = getattr(audio.info, "bitrate", 0)
                if raw_br:
                    bitrate = int(raw_br / 1000)

            tags = audio.tags or {}

            def get_val(*keys):
                for k in keys:
                    v = tags.get(k)
                    if v is not None:
                        if isinstance(v, list) and v:
                            return str(v[0]).strip()
                        if hasattr(v, "text") and v.text:
                            return str(v.text[0]).strip()
                        s = str(v).strip()
                        if s:
                            return s
                return None

            t = get_val("TIT2", "title", "\xa9nam")
            if t:
                title = t
            a = get_val("TPE1", "artist", "\xa9ART")
            if a:
                artist = a
            alb = get_val("TALB", "album", "\xa9alb")
            if alb:
                album = alb
            y = get_val("TDRC", "date", "\xa9day")
            if y:
                year = str(y)[:4]
            g = get_val("TCON", "genre", "\xa9gen")
            if g:
                genre = g
    except Exception:
        pass

    collection = file_path.parent.name if file_path.parent else "Einzeltitel"
    return TrackMetadata(
        title=title,
        artist=artist,
        album=album,
        year=year,
        genre=genre,
        collection=collection,
        duration=duration,
        bitrate=bitrate
    )

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


def clean_artist_title(raw_title: str, raw_artist: str = "") -> tuple[str, str]:
    """Clean video/download artifacts from titles and extract artist if combined."""
    title = (raw_title or "").strip()
    artist = (raw_artist or "").strip()

    # Replace underscores if used instead of spaces
    if "_" in title:
        title = title.replace("_", " ")
    if "_" in artist:
        artist = artist.replace("_", " ")

    # Remove common video / audio suffixes in parentheses or brackets
    patterns = [
        r'[\(\[\{]\s*(?:official\s*(?:video|audio|music\s*video|hd\s*video|visualizer|lyric\s*video)|video\s*clip|clip\s*officiel|official|lyrics?|audio|hq|hd|4k|1080p|720p|explicit|extended\s*mix|remastered(?:\s*\d{4})?|live(?:\s*at\s*[^)\]]+)?|prod\.\s*[^)\]]+)\s*[\)\]\}]',
        r'\|.*$',
    ]
    for pat in patterns:
        title = re.sub(pat, "", title, flags=re.IGNORECASE).strip()

    # If title has "Artist - Title" format and artist is empty or generic
    split_match = re.split(r'\s+[-–—]\s+', title, maxsplit=1)
    if len(split_match) == 2:
        cand_artist, cand_title = split_match[0].strip(), split_match[1].strip()
        if cand_artist and cand_title:
            if not artist or artist in ("Unbekannter Artist", "Unbekannt", "YouTube", cand_artist):
                artist = cand_artist
                title = cand_title

    # Clean dangling dashes or extra spaces
    title = re.sub(r'\s+', ' ', title).strip(" -–—\"'[]()")
    artist = re.sub(r'\s+', ' ', artist).strip(" -–—\"'[]()")

    return title or raw_title, artist or (raw_artist if raw_artist else "Unbekannter Artist")


def clean_track_id3(file_path: Path, db=None) -> tuple[str, str]:
    """Cleans ID3 tags of an audio file and updates SQLite database if provided."""
    meta = read_audio_tags(file_path)
    clean_title, clean_artist = clean_artist_title(meta.title, meta.artist)

    # Update ID3 tags via Mutagen
    try:
        if file_path.suffix.lower() == ".mp3":
            try:
                tags = ID3(file_path)
            except ID3NoHeaderError:
                tags = ID3()
            tags.setall("TIT2", [TIT2(encoding=3, text=clean_title)])
            tags.setall("TPE1", [TPE1(encoding=3, text=clean_artist)])
            tags.save(file_path)
    except Exception:
        pass

    # Update SQLite database if provided
    if db is not None:
        try:
            with db._connection() as conn:
                conn.execute(
                    "UPDATE tracks SET title = ?, artist = ? WHERE file_path = ?",
                    (clean_title, clean_artist, str(file_path))
                )
        except Exception:
            pass

    return clean_title, clean_artist

"""Metadata normalization, ID3 writing, cover download and safe paths."""

from __future__ import annotations

import re
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from mutagen.mp3 import MP3
from mutagen.id3 import APIC, ID3, ID3NoHeaderError, TALB, TCON, TIT2, TPE1, TRCK, TDRC


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


def safe_name(value: str, fallback: str) -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")
    return value[:120] or fallback


def target_path(root: Path, track: TrackMetadata) -> Path:
    artist = safe_name(track.artist, "Unbekannter Artist")
    album = safe_name(track.album, "Singles") if track.album and track.album != "Unbekanntes Album" else "Singles"
    prefix = f"{track.track_number:02d} - " if album != "Singles" and track.track_number else ""
    return root / artist / album / f"{prefix}{safe_name(track.title, 'Unbekannter Titel')}.mp3"


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


def write_id3(path: Path, track: TrackMetadata) -> tuple[bytes, str] | None:
    MP3(path).info  # Reject a renamed WebM/AAC file before it reaches the library.
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = ID3()
    tags.delall("APIC")
    tags["TIT2"] = TIT2(encoding=3, text=track.title)
    tags["TPE1"] = TPE1(encoding=3, text=track.artist)
    tags["TALB"] = TALB(encoding=3, text=track.album)
    if track.year:
        tags["TDRC"] = TDRC(encoding=3, text=track.year)
    if track.track_number:
        tags["TRCK"] = TRCK(encoding=3, text=str(track.track_number))
    if track.genre:
        tags["TCON"] = TCON(encoding=3, text=track.genre)
    cover = download_cover(track.cover_url)
    if cover:
        data, mime = cover
        tags.add(APIC(encoding=3, mime=mime, type=3, desc="Cover", data=data))
    tags.save(path, v2_version=3)
    return cover

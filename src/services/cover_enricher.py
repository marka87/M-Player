"""
Album Cover Enricher for MP3 Files.

Automatically enriches MP3 audio files with high-resolution album covers
using prioritized public APIs (iTunes Search API, MusicBrainz / Cover Art Archive, Deezer)
and embeds them via Mutagen ID3 APIC frames.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Callable
import urllib.parse
import urllib.request

from src.services.metadata import safe_name

import mutagen
from mutagen.id3 import ID3, APIC, ID3NoHeaderError

logger = logging.getLogger("CoverEnricher")


class CoverEnricher:
    """Fetches high-resolution album artwork and embeds it into MP3 ID3 tags."""

    USER_AGENT = "MPlayer-CoverEnricher/2.0 (https://github.com/marka87/M-Player)"

    def __init__(self, timeout: int = 8) -> None:
        self.timeout = timeout

    def _download_bytes(self, url: str) -> bytes | None:
        if not url or not url.startswith(("http://", "https://")):
            return None
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = resp.read(15 * 1024 * 1024)
            return data if len(data) > 500 else None
        except Exception as err:
            logger.debug("Failed downloading bytes from %s: %s", url, err)
            return None

    # =========================================================================
    # 1. API STRATEGY (Priority 1: No Key Required, Fast, High Resolution)
    # =========================================================================

    def fetch_itunes_cover(self, artist: str, album: str, resolution: int = 1000) -> bytes | None:
        """
        Queries Apple's iTunes Search API (Priority 1: No API key needed).
        Replaces '100x100bb.jpg' with e.g. '1000x1000bb.jpg' for pristine resolution.
        """
        query = f"{artist} {album}".strip()
        if not query:
            return None

        url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&media=music&limit=3"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = data.get("results", [])
            if not results:
                return None

            # Get best match artwork URL and upgrade resolution
            for r in results:
                artwork_url = r.get("artworkUrl100", "")
                if artwork_url:
                    hi_res_url = artwork_url.replace("100x100bb.jpg", f"{resolution}x{resolution}bb.jpg")
                    img = self._download_bytes(hi_res_url)
                    if img:
                        return img
            return None
        except Exception as err:
            logger.debug("iTunes API lookup failed for '%s': %s", query, err)
            return None

    def fetch_musicbrainz_cover(self, artist: str, album: str) -> bytes | None:
        """
        Queries MusicBrainz REST API to find the MBID, then downloads artwork
        from the Cover Art Archive (CAA) at https://coverartarchive.org.
        """
        query = f'artist:"{artist}" AND release:"{album}"'
        mb_url = f"https://musicbrainz.org/ws/2/release/?query={urllib.parse.quote(query)}&fmt=json&limit=1"

        try:
            req = urllib.request.Request(mb_url, headers={"User-Agent": self.USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            releases = data.get("releases", [])
            if not releases:
                return None

            mbid = releases[0].get("id")
            if not mbid:
                return None

            caa_url = f"https://coverartarchive.org/release/{mbid}/front-500"
            return self._download_bytes(caa_url)
        except Exception as err:
            logger.debug("MusicBrainz / CAA lookup failed for '%s': %s", query, err)
            return None

    def fetch_deezer_cover(self, artist: str, album: str) -> bytes | None:
        """Fallback API: Queries Deezer's public API for 1000x1000 art."""
        query = f"{artist} {album}".strip()
        url = f"https://api.deezer.com/search?q={urllib.parse.quote(query)}&limit=3"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            items = data.get("data", [])
            for item in items:
                img_url = item.get("album", {}).get("cover_xl") or item.get("album", {}).get("cover_big") or item.get("cover_xl")
                if img_url:
                    img = self._download_bytes(img_url)
                    if img:
                        return img
        except Exception as err:
            logger.debug("Deezer API lookup failed for '%s': %s", query, err)
        return None

    def fetch_youtube_cover(self, source_url: str) -> bytes | None:
        """Downloads YouTube video thumbnail (Priority 7: maxresdefault or hqdefault)."""
        import re
        if not source_url:
            return None
        vid_match = re.search(r'(?:v=|youtu\.be/|shorts/)([a-zA-Z0-9_-]{11})', source_url)
        if not vid_match:
            return None
        video_id = vid_match.group(1)
        for quality in ("maxresdefault.jpg", "hqdefault.jpg"):
            url = f"https://img.youtube.com/vi/{video_id}/{quality}"
            data = self._download_bytes(url)
            if data:
                return data
        return None

    def find_cover(self, artist: str, album: str, source_url: str = "", music_root: Path | None = None, title: str = "") -> tuple[bytes, str] | None:
        """
        Executes multi-tier fallback search:
        1. Local cache (.covers/)
        2. MusicBrainz / Cover Art Archive
        3. Apple iTunes Artwork API (1000x1000px)
        4. Deezer API (1000x1000px)
        5. YouTube Thumbnail
        """
        # If album is unknown, try title as query
        eff_album = title if (not album or album in ("Unbekanntes Album", "Einzeltitel", "Single")) and title else album

        # Check .covers cache if music_root is available
        if music_root:
            cache_dir = Path(music_root) / ".covers"
            safe_a = safe_name(artist, "artist")
            safe_al = safe_name(eff_album, "album")
            cache_file = cache_dir / f"{safe_a}-{safe_al}.jpg"
            if cache_file.exists() and cache_file.stat().st_size > 1024:
                return cache_file.read_bytes(), "image/jpeg"

        # 1. iTunes Artwork API (Up to 1000x1000 - Fast)
        img_bytes = self.fetch_itunes_cover(artist, eff_album)
        if not img_bytes and title and eff_album != title:
            img_bytes = self.fetch_itunes_cover(artist, title)
        if img_bytes:
            self._save_cache(music_root, artist, eff_album, img_bytes)
            return img_bytes, "image/jpeg"

        # 2. Deezer API (Up to 1000x1000 - Fast)
        img_bytes = self.fetch_deezer_cover(artist, eff_album)
        if not img_bytes and title and eff_album != title:
            img_bytes = self.fetch_deezer_cover(artist, title)
        if img_bytes:
            self._save_cache(music_root, artist, eff_album, img_bytes)
            return img_bytes, "image/jpeg"

        # 3. YouTube Thumbnail (Direct & 100% reliable for YouTube tracks)
        if source_url:
            img_bytes = self.fetch_youtube_cover(source_url)
            if img_bytes:
                self._save_cache(music_root, artist, eff_album, img_bytes)
                return img_bytes, "image/jpeg"

        # 4. MusicBrainz & Cover Art Archive (Fallback)
        img_bytes = self.fetch_musicbrainz_cover(artist, eff_album)
        if img_bytes:
            self._save_cache(music_root, artist, eff_album, img_bytes)
            return img_bytes, "image/jpeg"

        return None

    def _save_cache(self, music_root: Path | None, artist: str, album: str, data: bytes) -> None:
        if music_root:
            try:
                cache_dir = Path(music_root) / ".covers"
                cache_dir.mkdir(parents=True, exist_ok=True)
                safe_a = safe_name(artist, "artist")
                safe_al = safe_name(album, "album")
                (cache_dir / f"{safe_a}-{safe_al}.jpg").write_bytes(data)
            except OSError:
                pass

    # =========================================================================
    # 2. MP3 / ID3 METADATA PARSING & EMBEDDING
    # =========================================================================

    @staticmethod
    def read_tags(file_path: Path) -> tuple[str, str, bool]:
        """
        Extracts (artist, album, has_cover) from an MP3 file.
        Returns:
            artist: extracted artist or parent folder fallback
            album: extracted album or filename fallback
            has_cover: True if file already contains an embedded APIC cover frame
        """
        try:
            tags = ID3(file_path)
            artist = str(tags.get("TPE1", "")).strip()
            album = str(tags.get("TALB", "")).strip()
            has_cover = bool(tags.getall("APIC"))
            return artist, album, has_cover
        except ID3NoHeaderError:
            return "", "", False
        except Exception as err:
            logger.warning("Error reading ID3 tags from %s: %s", file_path.name, err)
            return "", "", False

    @staticmethod
    def embed_cover(file_path: Path, image_data: bytes, mime_type: str = "image/jpeg") -> bool:
        """
        Embeds binary cover data directly into the MP3 ID3v2.3 tags as an APIC frame.
        """
        try:
            try:
                tags = ID3(file_path)
            except ID3NoHeaderError:
                tags = ID3()

            # Remove existing APIC frames
            tags.delall("APIC")

            # Add primary Front Cover (type=3)
            tags.add(APIC(
                encoding=3,       # UTF-8
                mime=mime_type,   # image/jpeg or image/png
                type=3,           # Front Cover
                desc="Cover",
                data=image_data
            ))
            tags.save(file_path, v2_version=3)
            return True
        except Exception as err:
            logger.error("Failed embedding cover into %s: %s", file_path.name, err)
            return False

    # =========================================================================
    # 3. LOGICAL WORKFLOW: SINGLE FILE & BATCH ENRICHMENT
    # =========================================================================

    def enrich_file(
        self,
        file_path: Path,
        force: bool = False,
        save_folder_cover: bool = True,
        music_root: Path | None = None,
        source_url: str = ""
    ) -> bool:
        """
        Full enrichment workflow for a single MP3 file:
        1. Reads existing ID3 tags.
        2. Skips if cover already exists and force is False.
        3. Checks local cover.jpg before hitting network.
        4. Fetches best cover from multi-tier APIs.
        5. Embeds cover into ID3 tags.
        6. Optionally saves 'cover.jpg' in the album folder.
        """
        file_path = Path(file_path)
        if not file_path.is_file() or file_path.suffix.lower() != ".mp3":
            return False

        artist, album, has_cover = self.read_tags(file_path)

        # 1. Do not overwrite if embedded cover exists and force is False
        if has_cover and not force:
            logger.debug("Skipping %s: already has embedded cover art.", file_path.name)
            return True

        # 2. Check local cover.jpg if not force
        if file_path.parent and not force:
            local_cover = file_path.parent / "cover.jpg"
            if local_cover.is_file() and local_cover.stat().st_size > 1024:
                return self.embed_cover(file_path, local_cover.read_bytes())

        # Fallback to parent directory name if tags are missing
        if not artist or artist == "Unbekannter Artist":
            artist = file_path.stem.split(" - ")[0] if " - " in file_path.stem else file_path.parent.name
        if not album or album == "Unbekanntes Album":
            album = file_path.parent.name

        cover_result = self.find_cover(artist, album, source_url=source_url, music_root=music_root)
        if not cover_result:
            logger.warning("No cover found for '%s - %s' (%s)", artist, album, file_path.name)
            return False

        image_data, mime_type = cover_result
        success = self.embed_cover(file_path, image_data, mime_type)

        if success and save_folder_cover and file_path.parent:
            folder_cover = file_path.parent / "cover.jpg"
            if not folder_cover.exists() or force:
                try:
                    folder_cover.write_bytes(image_data)
                except OSError:
                    pass

        return success

    def enrich_directory(
        self,
        directory: Path,
        force: bool = False,
        recursive: bool = True,
        callback: Callable[[int, int, str], None] | None = None
    ) -> dict[str, int]:
        """
        Processes an entire directory of MP3 files.
        Returns:
            Dictionary with counts: total, enriched, skipped, failed.
        """
        directory = Path(directory)
        pattern = "**/*.mp3" if recursive else "*.mp3"
        mp3_files = list(directory.glob(pattern))

        stats = {"total": len(mp3_files), "enriched": 0, "skipped": 0, "failed": 0}

        for i, file_path in enumerate(mp3_files, 1):
            if callback:
                callback(i, len(mp3_files), file_path.name)

            artist, album, has_cover = self.read_tags(file_path)
            if has_cover and not force:
                stats["skipped"] += 1
                continue

            ok = self.enrich_file(file_path, force=force)
            if ok:
                stats["enriched"] += 1
            else:
                stats["failed"] += 1

        return stats


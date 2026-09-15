"""
Album Cover Enricher for MP3 Files.

Automatically enriches MP3 audio files with high-resolution album covers
using prioritized public APIs (iTunes Search API, MusicBrainz / Cover Art Archive, Deezer)
and embeds them via Mutagen ID3 APIC frames.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Callable
import urllib.parse
import urllib.request

import mutagen
from mutagen.id3 import ID3, APIC, ID3NoHeaderError

logger = logging.getLogger("CoverEnricher")


class CoverEnricher:
    """Fetches high-resolution album artwork and embeds it into MP3 ID3 tags."""

    USER_AGENT = "MPlayer-CoverEnricher/2.0 (https://github.com/marka87/Musikapp)"

    def __init__(self, timeout: int = 8) -> None:
        self.timeout = timeout

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

        url = f"https://itunes.apple.com/search?term={urllib.parse.quote(query)}&entity=album&limit=3"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            results = data.get("results", [])
            if not results:
                return None

            # Get best match artwork URL and upgrade resolution
            artwork_url = results[0].get("artworkUrl100", "")
            if not artwork_url:
                return None

            hi_res_url = artwork_url.replace("100x100bb.jpg", f"{resolution}x{resolution}bb.jpg")
            return self._download_bytes(hi_res_url)
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
        """Fallback API: Queries Deezer's public album API for 500x500/1000x1000 art."""
        query = f"{artist} {album}".strip()
        url = f"https://api.deezer.com/search/album?q={urllib.parse.quote(query)}&limit=1"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": self.USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            items = data.get("data", [])
            if items:
                img_url = items[0].get("cover_xl") or items[0].get("cover_big")
                if img_url:
                    return self._download_bytes(img_url)
        except Exception as err:
            logger.debug("Deezer API lookup failed for '%s': %s", query, err)
        return None

    def _download_bytes(self, image_url: str) -> bytes | None:
        """Downloads image binary bytes with timeout and header check."""
        try:
            req = urllib.request.Request(image_url, headers={"User-Agent": self.USER_AGENT})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                if resp.status == 200:
                    raw = resp.read()
                    if len(raw) > 1024:  # Minimum valid image size
                        return raw
        except Exception as err:
            logger.debug("Failed downloading image from %s: %s", image_url, err)
        return None

    def find_cover(self, artist: str, album: str) -> tuple[bytes, str] | None:
        """
        Executes multi-tier fallback search:
        1. Apple iTunes Search API (1000x1000px)
        2. Deezer API (1000x1000px / 500x500px)
        3. MusicBrainz / Cover Art Archive (Front-500)
        """
        # 1. iTunes (Primary)
        img_bytes = self.fetch_itunes_cover(artist, album)
        if img_bytes:
            return img_bytes, "image/jpeg"

        # 2. Deezer (Fast fallback)
        img_bytes = self.fetch_deezer_cover(artist, album)
        if img_bytes:
            return img_bytes, "image/jpeg"

        # 3. MusicBrainz / CAA
        img_bytes = self.fetch_musicbrainz_cover(artist, album)
        if img_bytes:
            return img_bytes, "image/jpeg"

        return None

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

    def enrich_file(self, file_path: Path, force: bool = False, save_folder_cover: bool = True) -> bool:
        """
        Full enrichment workflow for a single MP3 file:
        1. Reads existing ID3 tags.
        2. Skips if cover already exists and force is False.
        3. Fetches best cover from APIs.
        4. Embeds cover into ID3 tags.
        5. Optionally saves 'cover.jpg' in the album folder.
        """
        file_path = Path(file_path)
        if not file_path.is_file() or file_path.suffix.lower() != ".mp3":
            return False

        artist, album, has_cover = self.read_tags(file_path)

        # Do not overwrite unless force is requested
        if has_cover and not force:
            logger.debug("Skipping %s: already has embedded cover art.", file_path.name)
            return False

        # Fallback to parent directory name if tags are missing
        if not artist or artist == "Unbekannter Artist":
            artist = file_path.stem.split(" - ")[0] if " - " in file_path.stem else file_path.parent.name
        if not album or album == "Unbekanntes Album":
            album = file_path.parent.name

        cover_result = self.find_cover(artist, album)
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


# =========================================================================
# 4. STANDALONE CLI ENTRYPOINT
# =========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Enrich MP3 files with high-resolution album artwork (iTunes, Deezer, MusicBrainz)."
    )
    parser.add_argument("path", type=Path, help="Path to an MP3 file or a directory containing MP3 files.")
    parser.add_argument("--force", "-f", action="store_true", help="Overwrite existing album artwork.")
    parser.add_argument("--no-recursive", action="store_true", help="Do not scan subdirectories.")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed logging.")

    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")

    enricher = CoverEnricher()
    target = args.path

    if target.is_file():
        print(f"Processing single file: {target.name} ...")
        success = enricher.enrich_file(target, force=args.force)
        print("✓ Cover successfully embedded!" if success else "✗ Cover could not be enriched.")
    elif target.is_dir():
        print(f"Scanning directory: {target} ...")
        stats = enricher.enrich_directory(
            target,
            force=args.force,
            recursive=not args.no_recursive,
            callback=lambda i, tot, name: print(f"[{i}/{tot}] Checking: {name}")
        )
        print("\n" + "=" * 40)
        print(f"Total files:    {stats['total']}")
        print(f"Enriched:       {stats['enriched']}")
        print(f"Skipped:        {stats['skipped']}")
        print(f"Failed/Missing: {stats['failed']}")
        print("=" * 40)
    else:
        print(f"Error: Path '{target}' does not exist.")


if __name__ == "__main__":
    main()

"""Tests for automated album recognition and library sync."""

import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.database.database import MusicDatabase
from src.services.metadata import TrackMetadata, resolve_album_online


def test_resolve_album_mocked():
    # Test that resolve_album_online formats and returns correctly
    with patch("requests.get") as mock_get:
        # Simulate iTunes returning a collection
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {
            "results": [{"collectionName": "A Night at the Opera", "releaseDate": "1975-11-21"}]
        }
        album, year = resolve_album_online("Queen", "Bohemian Rhapsody")
        assert album == "A Night at the Opera", f"Expected 'A Night at the Opera', got '{album}'"
        assert year == "1975", f"Expected '1975', got '{year}'"
    print("test_resolve_album_mocked passed!")


def test_sync_library_detects_album():
    with tempfile.TemporaryDirectory() as tmpdir:
        music_root = Path(tmpdir) / "Music"
        music_root.mkdir()
        mp3_file = music_root / "test_song.mp3"

        # Create a minimal valid MP3 file with ID3 tags
        from mutagen.id3 import ID3, TIT2, TPE1
        from mutagen.mp3 import MP3

        # Write valid MPEG-1 Layer 3 frame (128 kbps, 44.1 kHz, stereo)
        frame = b"\xff\xfb\x90\x00" + b"\x00" * 413
        mp3_file.write_bytes(frame * 10)

        # Set title and artist, but NO album
        tags = ID3()
        tags.add(TIT2(encoding=3, text="Bohemian Rhapsody"))
        tags.add(TPE1(encoding=3, text="Queen"))
        tags.save(mp3_file)

        db_path = Path(tmpdir) / "library.db"
        db = MusicDatabase(db_path)

        with patch("src.services.metadata.resolve_album_online") as mock_resolve:
            mock_resolve.return_value = ("A Night at the Opera", "1975")

            # 1. First sync: new file discovered and album resolved
            added, removed = db.sync_library(music_root)
            assert added == 1

            # Check SQLite
            tracks = db.tracks()
            assert len(tracks) == 1
            assert tracks[0]["album"] == "A Night at the Opera"
            assert tracks[0]["year"] == "1975"

            # Check MP3 ID3 tag directly via Mutagen
            reloaded_tags = ID3(mp3_file)
            assert "TALB" in reloaded_tags
            assert str(reloaded_tags["TALB"]) == "A Night at the Opera"
            assert "TDRC" in reloaded_tags
            assert str(reloaded_tags["TDRC"]) == "1975"

            # 2. Test re-syncing existing tracks that were previously 'Unbekanntes Album'
            with db._connection() as conn:
                conn.execute("UPDATE tracks SET album = 'Unbekanntes Album'")

            mock_resolve.return_value = ("A Night at the Opera (Remastered)", "2011")
            db.sync_library(music_root)

            tracks = db.tracks()
            assert tracks[0]["album"] == "A Night at the Opera (Remastered)"
            assert str(ID3(mp3_file)["TALB"]) == "A Night at the Opera (Remastered)"

    print("test_sync_library_detects_album passed successfully!")


if __name__ == "__main__":
    test_resolve_album_mocked()
    test_sync_library_detects_album()
    print("All album resolver tests passed!")

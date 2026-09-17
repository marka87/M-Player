"""Tests for duplicate detection in MusicDatabase."""

import tempfile
from pathlib import Path
from database import MusicDatabase
from metadata import TrackMetadata


def test_find_duplicates():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = MusicDatabase(db_path)

        # 1. Add two duplicate tracks: one Official Video (128kbps), one Topic (320kbps)
        t1 = TrackMetadata(title="Never Gonna Give You Up (Official Video)", artist="Rick Astley", duration=213.0, bitrate=128)
        t2 = TrackMetadata(title="Never Gonna Give You Up", artist="Rick Astley - Topic", duration=214.0, bitrate=320)
        p1 = Path(tmpdir) / "song1.mp3"
        p2 = Path(tmpdir) / "song2.mp3"
        p1.touch()
        p2.touch()

        db.upsert(t1, p1, duration=t1.duration, bitrate=t1.bitrate)
        db.upsert(t2, p2, duration=t2.duration, bitrate=t2.bitrate)

        # 2. Add an unrelated song
        t3 = TrackMetadata(title="Smooth Criminal", artist="Michael Jackson", duration=257.0, bitrate=320)
        p3 = Path(tmpdir) / "song3.mp3"
        p3.touch()
        db.upsert(t3, p3, duration=t3.duration, bitrate=t3.bitrate)

        # 3. Add a song with same title as t1/t2 but very different duration (Extended Mix, 300s vs 213s)
        t4 = TrackMetadata(title="Never Gonna Give You Up (Extended)", artist="Rick Astley", duration=300.0, bitrate=320)
        p4 = Path(tmpdir) / "song4.mp3"
        p4.touch()
        db.upsert(t4, p4, duration=t4.duration, bitrate=t4.bitrate)

        # Run duplicate detection
        duplicates = db.find_duplicates(duration_tolerance=2.0, similarity_threshold=0.85)

        assert len(duplicates) == 1, f"Expected 1 duplicate group, got {len(duplicates)}"
        group = duplicates[0]
        assert len(group) == 2, f"Expected 2 tracks in duplicate group, got {len(group)}"

        # The higher bitrate track (320 kbps) should be sorted first (recommended)
        assert group[0]["bitrate"] == 320, f"Expected highest bitrate first, got {group[0]['bitrate']}"
        assert group[1]["bitrate"] == 128, f"Expected lower bitrate second, got {group[1]['bitrate']}"

        # 4. Test deleting the duplicate
        dup_to_delete = group[1]
        deleted = db.delete_track(dup_to_delete["id"], delete_file=True)
        assert deleted is True

        # Check remaining duplicates
        remaining_dups = db.find_duplicates(duration_tolerance=2.0, similarity_threshold=0.85)
        assert len(remaining_dups) == 0, f"Expected 0 duplicate groups after deletion, got {len(remaining_dups)}"

        # Check remaining tracks in database
        all_tracks = db.tracks()
        assert len(all_tracks) == 3, f"Expected 3 remaining tracks, got {len(all_tracks)}"

        # Check find_duplicate_track
        assert db.find_duplicate_track(title="Smooth Criminal", artist="Michael Jackson") is not None
        assert db.find_duplicate_track(title="Nonexistent", artist="Nobody") is None
        assert db.find_duplicate_track(file_path=p3) is not None

        print("test_find_duplicates passed successfully!")


if __name__ == "__main__":
    test_find_duplicates()


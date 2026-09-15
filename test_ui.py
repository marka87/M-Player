"""Headless verification test for M-Player UI."""

import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PySide6.QtWidgets import QApplication, QMessageBox
from database import MusicDatabase
from metadata import TrackMetadata
from ui import MusicWindow

# Mock modal message boxes
QMessageBox.information = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.warning = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.critical = lambda *args, **kwargs: QMessageBox.StandardButton.Ok
QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes

def test_full_ui():
    app = QApplication.instance() or QApplication(sys.argv)
    with TemporaryDirectory() as tmp_dir:
        root = Path(tmp_dir)
        db_path = root / "test.db"
        db = MusicDatabase(db_path)

        # Seed sample tracks
        t1 = TrackMetadata("Song One", "Artist A", "Album X", genre="Pop", year="2022")
        f1 = root / "Artist A" / "Song One.mp3"
        f1.parent.mkdir(parents=True, exist_ok=True)
        f1.write_bytes(b"\xff\xfb\x90\x44" + b"\x00" * 200)
        db.upsert(t1, f1, duration=210, bitrate=320)

        t2 = TrackMetadata("Song Two", "Artist B", "Album Y", genre="Rock", year="2021", collection="BestOf")
        f2 = root / "BestOf" / "Song Two.mp3"
        f2.parent.mkdir(parents=True, exist_ok=True)
        f2.write_bytes(b"\xff\xfb\x90\x44" + b"\x00" * 200)
        db.upsert(t2, f2, duration=180, bitrate=320)
        db.create_playlist("BestOf")
        db.add_to_playlist("BestOf", 2)

        # Create window
        win = MusicWindow(db, root)
        win.show()

        # Check pages
        assert win.pages.count() == 6
        for p_idx in range(6):
            win.show_page(p_idx)

        # Check Details panel
        assert hasattr(win, "details_panel")
        track_row = db.tracks()[0]
        win.show_track_details(track_row)
        assert win.details_panel.isVisible()
        assert win.detail_title.text() == "Song One"

        # Check Filter Chips
        assert hasattr(win, "chip_buttons")
        assert "Alle" in win.chip_buttons
        win._on_chip_clicked("Nicht gehört", win.chip_buttons["Nicht gehört"])
        assert win.current_chip == "Nicht gehört"
        win._on_chip_clicked("Alle", win.chip_buttons["Alle"])
        assert win.current_chip == "Alle"

        # Check Playlists Stack
        assert hasattr(win, "pl_stack")
        assert win.pl_stack.count() == 2
        win._open_playlist_detail("BestOf")
        assert win.pl_stack.currentIndex() == 1
        assert win.pl_detail_title.text() == "BestOf"

        # Check Queue Stats
        win.update_queue_stats()
        assert hasattr(win, "stat_active_val")
        assert win.stat_active_val.text() == "0"

        # Check Mini Player ClickableSlider
        assert hasattr(win, "timeline_slider")
        assert win.timeline_slider.maximum() >= 0

        # Check Settings Checkboxes
        assert hasattr(win, "chk_auto_cover")
        assert hasattr(win, "chk_auto_meta")
        assert hasattr(win, "chk_only_new")
        assert hasattr(win, "chk_cleanup_startup")
        assert hasattr(win, "chk_auto_sync_pl")
        win.save_settings()

        win.close()
        print("All UI tests passed successfully!")

if __name__ == "__main__":
    test_full_ui()

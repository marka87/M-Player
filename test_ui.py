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

        # Check Window Icon & App Logo
        assert hasattr(win, "logo_lbl")
        assert win.logo_lbl.width() == 28 and win.logo_lbl.height() == 28
        assert not win.windowIcon().isNull()

        # Check pages (Downloader, Entdecken, Bibliothek, Favoriten, Playlists, Downloads, Einstellungen)
        assert win.pages.count() == 7
        for p_idx in range(7):
            win.show_page(p_idx)

        # Check Discover (YouTube-Suche) components
        assert hasattr(win, "discover_input")
        assert hasattr(win, "discover_btn")
        assert hasattr(win, "discover_model")
        assert hasattr(win, "disc_filter_buttons")
        win._set_discover_filter("video")
        assert win.discover_filter == "video"
        win._set_discover_filter("playlist")
        assert win.discover_filter == "playlist"
        win._set_discover_filter("all")
        assert win.discover_filter == "all"

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
        # Check Settings small window height protection
        win.resize(700, 420)
        win.show_page(6)
        app.processEvents()
        for chk in (win.chk_auto_cover, win.chk_auto_meta, win.chk_only_new, win.chk_cleanup_startup, win.chk_auto_sync_pl):
            assert chk.minimumHeight() >= 24
        win.save_settings()

        # Check Discover pagination & append_rows
        initial_hits = [{"id": "1", "title": "Song 1", "artist": "Artist 1", "duration": 120, "url": "https://...", "cover_url": "", "is_playlist": False, "type": "🎵 Song"}]
        win.discover_model.set_rows(initial_hits)
        assert win.discover_model.rowCount() == 1
        more_hits = [{"id": "2", "title": "Song 2", "artist": "Artist 2", "duration": 180, "url": "https://...", "cover_url": "", "is_playlist": False, "type": "🎵 Song"}]
        win._on_search_more_done(more_hits)
        assert win.discover_model.rowCount() == 2

        # Check cover resolution for MP3 files (embedded & folder cover.jpg)
        from ui import get_cover_pixmap
        # Test folder cover.jpg
        test_cover = f1.parent / "cover.jpg"
        from PySide6.QtGui import QPixmap
        pix = QPixmap(10, 10)
        pix.fill()
        pix.save(str(test_cover), "JPG")
        get_cover_pixmap.cache_clear()
        cov = get_cover_pixmap(str(f1), 48)
        # Check Table Sorting (Title asc/desc, duration, year)
        from PySide6.QtCore import Qt
        win.lib_table.sortByColumn(2, Qt.DescendingOrder)
        assert win.lib_model.rows[0]["title"] == "Song Two"
        # Check Sidebar scrollbar is disabled
        assert win.nav.verticalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
        assert win.nav.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff

        # Check List / Raster view toggle via button clicks
        assert win.lib_view_stack.currentIndex() == 0
        assert win.lib_list_btn.property("active") == "true"
        assert win.lib_grid_btn.property("active") == "false"

        # Click Raster button
        win.lib_grid_btn.click()
        assert win.lib_view_stack.currentIndex() == 1
        assert win.lib_grid_btn.property("active") == "true"
        assert win.lib_list_btn.property("active") == "false"
        assert win.lib_grid.count() == 2

        # Click List button
        win.lib_list_btn.click()
        assert win.lib_view_stack.currentIndex() == 0
        assert win.lib_list_btn.property("active") == "true"
        assert win.lib_grid_btn.property("active") == "false"

        # Check Drag & Drop acceptance and import
        assert win.acceptDrops()
        assert win.lib_table.acceptDrops()
        drop_file = root / "Artist C" / "Dropped Track.mp3"
        drop_file.parent.mkdir(parents=True, exist_ok=True)
        drop_file.write_bytes(b"\xff\xfb\x90\x44" + b"\x00" * 200)
        imported = win.import_dropped_files([drop_file])
        assert imported == 1
        assert any(t["title"] == "Dropped Track" for t in win.db.tracks())

        # Check Toast Notification
        win.notify("Download abgeschlossen", "'Test Song' wurde erfolgreich heruntergeladen.")

        # Check Context Menu & Explorer Reveal
        win._show_in_explorer(drop_file)

        # Check Sidebar Mini-Card (idle fallback state)
        assert hasattr(win, "sidebar_mini_card")
        assert win.sb_stats_box.isVisible()
        assert not win.sb_track_box.isVisible()

        # Play a song and verify Sidebar Mini-Card switches to track state
        win.play(win.lib_model.rows[0], 0, win.lib_model.rows)
        assert win.sb_track_box.isVisible()
        assert not win.sb_stats_box.isVisible()
        assert win.sb_title.text() != ""

        # Test GridCardDelegate painting directly with QPainter (must not raise exceptions)
        from PySide6.QtGui import QPainter, QPixmap
        from PySide6.QtWidgets import QStyleOptionViewItem
        delegate = win.lib_grid.itemDelegate()
        pix = QPixmap(200, 250)
        painter = QPainter(pix)
        opt = QStyleOptionViewItem()
        opt.rect = win.lib_grid.visualItemRect(win.lib_grid.item(0))
        opt.widget = win.lib_grid
        delegate.paint(painter, opt, win.lib_grid.model().index(0, 0))
        painter.end()

        # Check Single Modern Dark theme
        assert win.settings.get("theme") == "dark.qss"

        # 1. Test Auto Tag-Cleaner logic
        from metadata import clean_artist_title, clean_track_id3
        c_title, c_artist = clean_artist_title("Faithless - God Is a DJ (Official Video)")
        assert c_title == "God Is a DJ"
        assert c_artist == "Faithless"

        c_title2, c_artist2 = clean_artist_title("Song_With_Underscores [HQ] (Lyrics)")
        assert c_title2 == "Song With Underscores"

        # Test single track clean via UI
        assert hasattr(win, "clean_selected_tags")
        assert hasattr(win, "clean_single_track")
        win.clean_single_track(win.lib_model.rows[0])

        # 2. Test LRCLIB Synced Lyrics parsing & UI
        from lyrics import parse_lrc
        lrc_sample = "[00:12.50]Line One\n[00:25.00]Line Two\n[01:05.10]Line Three"
        parsed = parse_lrc(lrc_sample)
        assert len(parsed) == 3
        assert parsed[0] == (12.5, "Line One")
        assert parsed[1] == (25.0, "Line Two")
        assert parsed[2] == (65.1, "Line Three")

        # Test details panel lyrics tab & line click seeking
        assert hasattr(win, "lyrics_list")
        assert hasattr(win, "detail_tab_lyrics")
        win.detail_tab_lyrics.click()
        assert win.detail_stack.currentIndex() == 1
        win._populate_lyrics(parsed, is_synced=True)
        assert win.lyrics_list.count() == 3
        win._update_lyrics_position(15.0)
        assert win.lyrics_list.currentRow() == 0
        win._update_lyrics_position(30.0)
        assert win.lyrics_list.currentRow() == 1
        # Click lyric line to seek
        seek_events = []
        orig_set_pos = win.player.setPosition
        win.player.setPosition = lambda ms: (seek_events.append(ms), orig_set_pos(ms))
        win._on_lyric_line_clicked(win.lyrics_list.item(2))
        assert seek_events == [65100]

        # Switch back to Info tab
        win.detail_tab_info.click()
        assert win.detail_stack.currentIndex() == 0

        # 3. Test Mini-Player (Always-on-Top)
        assert hasattr(win, "mini_player")
        assert hasattr(win, "toggle_mini_player")
        assert hasattr(win, "mini_btn")
        # Toggle to show mini player
        win.toggle_mini_player()
        assert win.mini_player.isVisible()
        win.mini_player.update_track(win.lib_model.rows[0])
        assert win.mini_player.title_lbl.text() != ""
        # Seek from mini player
        win.mini_player._on_seek(500)
        # Restore main window
        win.mini_player.restore_main_window()
        assert not win.mini_player.isVisible()
        win.player.setPosition = orig_set_pos

        # 4. Test Direct-Stream Preview (Pre-Listening)
        from downloader import get_stream_url
        assert callable(get_stream_url)
        assert hasattr(win, "preview_stream")
        assert hasattr(win, "disc_preview_btn")
        assert win.discover_model.columnCount() == 6
        assert win.discover_model.headers[5] == "Aktionen"

        # Test previewing search result
        mock_hit = {
            "id": "abc12345678",
            "title": "Preview Song",
            "artist": "Stream Artist",
            "url": "https://www.youtube.com/watch?v=abc12345678",
            "cover_url": "",
            "duration": 200,
            "type": "Song"
        }
        win.discover_model.set_rows([mock_hit])
        win._attach_discover_action_buttons(0)
        action_widget = win.discover_table.indexWidget(win.discover_model.index(0, 5))
        assert action_widget is not None
        # Trigger preview
        win.preview_stream(mock_hit)
        assert win.current_track is not None
        assert win.current_track["is_stream"] is True

        # 5. Test Similar Songs / Recommendations (Radio)
        from recommendations import fetch_recommendations
        assert callable(fetch_recommendations)
        assert hasattr(win, "detail_tab_similar")
        assert hasattr(win, "similar_list")
        win.detail_tab_similar.click()
        assert win.detail_stack.currentIndex() == 2

        # Populate sample recommendations
        sample_recs = [
            {"id": "rec1", "title": "Similar Track 1", "artist": "Artist 1", "url": "https://...", "cover_url": "", "duration": 180},
            {"id": "rec2", "title": "Similar Track 2", "artist": "Artist 2", "url": "https://...", "cover_url": "", "duration": 210},
        ]
        win._populate_recommendations(sample_recs)
        assert win.similar_list.count() == 2
        item_w = win.similar_list.itemWidget(win.similar_list.item(0))
        assert item_w is not None

        win.close()
        print("All UI tests passed successfully!")

if __name__ == "__main__":
    test_full_ui()



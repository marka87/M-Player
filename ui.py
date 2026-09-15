"""M-Player UI Polish v1.1 — Windows 11 / Spotify-style UI for PySide6."""

from __future__ import annotations

import functools
import os
import random
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QObject, QRunnable,
                            QSize, Qt, QThreadPool, QUrl, Signal)
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QIcon, QPainter,
                           QPainterPath, QPixmap)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QFileDialog,
                             QFrame, QHBoxLayout, QHeaderView, QInputDialog,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMenu, QMessageBox, QProgressBar,
                             QPushButton, QSlider, QStackedWidget, QTableView,
                             QVBoxLayout, QWidget)

from database import MusicDatabase
from downloader import DownloadCancelled, MusicDownloader
from metadata import find_or_fetch_cover, safe_name


def time_text(seconds: float) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 60}:{seconds % 60:02d}"


def format_size(bytes_val: int | float) -> str:
    bytes_val = float(bytes_val or 0)
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024.0:
            return f"{bytes_val:.1f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.1f} TB"


@functools.lru_cache(maxsize=400)
def get_cover_pixmap(cover_source: str, size: int = 48) -> QPixmap:
    pix = QPixmap()
    if cover_source:
        p = Path(cover_source)
        if p.is_file():
            pix.load(str(p))
        elif p.is_dir() and (p / "cover.jpg").exists():
            pix.load(str(p / "cover.jpg"))
        elif (p.parent / "cover.jpg").exists():
            pix.load(str(p.parent / "cover.jpg"))

    if pix.isNull():
        pix = QPixmap(size, size)
        pix.fill(QColor("#20262F"))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("#3DDC63"))
        font = painter.font()
        font.setPixelSize(int(size * 0.45))
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignCenter, "🎵")
        painter.end()
        return pix

    scaled = pix.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    rounded = QPixmap(size, size)
    rounded.fill(Qt.transparent)
    painter = QPainter(rounded)
    painter.setRenderHint(QPainter.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(0, 0, size, size, 8, 8)
    painter.setClipPath(path)
    painter.drawPixmap(0, 0, scaled)
    painter.end()
    return rounded


class TrackModel(QAbstractTableModel):
    headers = ["□", "Cover", "Titel", "Künstler", "Album", "Dauer", "Jahr", "Qualität", "Status"]

    def __init__(self, rows: list[object] | None = None, selectable: bool = True) -> None:
        super().__init__()
        self.rows = rows or []
        self.selectable = selectable
        self.checked = set()
        self.status = {}

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if section == 0:
                if role == Qt.DisplayRole:
                    all_c = len(self.checked) == len(self.rows) and len(self.rows) > 0
                    return "☑" if all_c else "□"
                if role == Qt.ToolTipRole:
                    return "Klicken: Alle auswählen / abwählen"
            if role == Qt.DisplayRole:
                return self.headers[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        item = self.rows[row]

        if col == 0 and self.selectable and role == Qt.CheckStateRole:
            return Qt.Checked if row in self.checked else Qt.Unchecked

        def value(key, default=""):
            if isinstance(item, dict):
                return item.get(key, default)
            if hasattr(item, key):
                return getattr(item, key)
            if hasattr(item, "keys") and key in item.keys():
                return item[key]
            return default

        if col == 1:
            if role == Qt.DecorationRole:
                path = value("file_path") or value("cover_url")
                return get_cover_pixmap(str(path), 48)
            return None

        if role == Qt.TextAlignmentRole and col == 5:
            return int(Qt.AlignRight | Qt.AlignVCenter)

        if role == Qt.DisplayRole:
            values = [
                "",
                "",
                value("title"),
                value("artist"),
                value("album"),
                time_text(value("duration")) if value("duration") else "--:--",
                str(value("year") or "-"),
                f"{value('bitrate')} kbps" if value("bitrate") else "320 kbps",
                self.status.get(row, "Bereit")
            ]
            return values[col]
        return None

    def flags(self, index):
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if self.selectable and index.column() == 0:
            return flags | Qt.ItemIsUserCheckable
        return flags

    def setData(self, index, value, role=Qt.EditRole):
        if self.selectable and index.column() == 0 and role == Qt.CheckStateRole:
            if value in (Qt.Checked, Qt.CheckState.Checked, 2):
                self.checked.add(index.row())
            else:
                self.checked.discard(index.row())
            self.dataChanged.emit(index, index)
            self.headerDataChanged.emit(Qt.Horizontal, 0, 0)
            return True
        return False

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.checked = set(range(len(self.rows))) if self.selectable else set()
        self.status = {}
        self.endResetModel()

    def selected(self):
        return [self.rows[i] for i in sorted(self.checked)]


class DownloadQueueModel(QAbstractTableModel):
    headers = ["Cover", "Titel", "Fortschritt", "Geschwindigkeit", "Restzeit", "Status"]

    def __init__(self):
        super().__init__()
        self.items = []

    def rowCount(self, parent=QModelIndex()):
        return len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.headers[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        item = self.items[row]
        if col == 0 and role == Qt.DecorationRole:
            return get_cover_pixmap(item.get("cover_url", ""), 48)
        if role == Qt.DisplayRole:
            if col == 1:
                return f"{item.get('artist', '')} - {item.get('title', '')}".strip(" -")
            if col == 2:
                return f"{int(item.get('progress', 0) * 100)}%"
            if col == 3:
                return item.get("speed", "--")
            if col == 4:
                return item.get("eta", "--")
            if col == 5:
                return item.get("status", "Bereit")
        return None

    def add_task(self, title: str, artist: str = "", cover_url: str = "", track_obj=None):
        self.beginInsertRows(QModelIndex(), len(self.items), len(self.items))
        self.items.append({
            "title": title,
            "artist": artist,
            "cover_url": cover_url,
            "progress": 0.0,
            "speed": "--",
            "eta": "--",
            "status": "In Warteschlange",
            "track": track_obj
        })
        self.endInsertRows()
        return len(self.items) - 1

    def update_task(self, row: int, progress: float, speed: str, eta: str, status: str = "Lädt..."):
        if 0 <= row < len(self.items):
            self.items[row].update({
                "progress": progress,
                "speed": speed,
                "eta": eta,
                "status": status
            })
            idx1 = self.index(row, 2)
            idx2 = self.index(row, 5)
            self.dataChanged.emit(idx1, idx2)


class Signals(QObject):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(int, float, str, str, str)
    status = Signal(int, str)
    sync_progress = Signal(int, int, str)
    cover_progress = Signal(int, int, str)


class AnalyzeTask(QRunnable):
    def __init__(self, urls, root, db):
        super().__init__()
        self.urls, self.root, self.db, self.signals = urls, root, db, Signals()

    def run(self):
        try:
            tracks = []
            loader = MusicDownloader(self.root, self.db)
            for url in self.urls:
                tracks.extend(loader._spotify_sources(url) if loader.is_spotify(url) else loader._youtube_sources(url))
            self.signals.done.emit(tracks)
        except Exception as exc:
            self.signals.error.emit(str(exc))


class DownloadTask(QRunnable):
    def __init__(self, track, row_idx, queue_idx, step, total, root, db, cancelled, resumed):
        super().__init__()
        self.track = track
        self.row_idx = row_idx
        self.queue_idx = queue_idx
        self.step = step
        self.total = total
        self.root = root
        self.db = db
        self.cancelled = cancelled
        self.resumed = resumed
        self.signals = Signals()

    def run(self):
        try:
            loader = MusicDownloader(self.root, self.db, self.cancelled, self.resumed)
            def progress_hook(ratio, title, speed, eta):
                self.signals.progress.emit(self.queue_idx, ratio, title, speed, eta)

            loader._download_one(self.track, self.step, self.total, progress_hook)
            self.signals.status.emit(self.row_idx, "Fertig")
            self.signals.progress.emit(self.queue_idx, 1.0, self.track.title, "Fertig", "0s")
        except DownloadCancelled:
            self.signals.status.emit(self.row_idx, "Abgebrochen")
            self.signals.progress.emit(self.queue_idx, 0.0, self.track.title, "--", "--")
        except Exception as exc:
            self.signals.status.emit(self.row_idx, f"Fehler: {exc}")
            self.signals.progress.emit(self.queue_idx, 0.0, self.track.title, "--", "--")


class SyncLibraryTask(QRunnable):
    def __init__(self, db: MusicDatabase, root: Path):
        super().__init__()
        self.db = db
        self.root = root
        self.signals = Signals()

    def run(self):
        def cb(i, tot, name):
            self.signals.sync_progress.emit(i, tot, name)
        try:
            added, removed = self.db.sync_library(self.root, cb)
            self.signals.done.emit((added, removed))
        except Exception as exc:
            self.signals.error.emit(str(exc))


class CoverFinderTask(QRunnable):
    def __init__(self, db: MusicDatabase, root: Path):
        super().__init__()
        self.db = db
        self.root = root
        self.signals = Signals()

    def run(self):
        try:
            tracks = self.db.tracks()
            total = len(tracks)
            found = 0
            for i, t in enumerate(tracks, 1):
                self.signals.cover_progress.emit(i, total, t["title"])
                fp = Path(t["file_path"]) if t["file_path"] else None
                # Check if cover already exists
                if fp and fp.parent and (fp.parent / "cover.jpg").exists():
                    continue
                cov = find_or_fetch_cover(t["artist"], t["album"], self.root, fp)
                if cov:
                    found += 1
            self.signals.done.emit(found)
        except Exception as exc:
            self.signals.error.emit(str(exc))


class TagEditorDialog(QDialog):
    def __init__(self, track, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Metadaten & ID3 bearbeiten")
        self.setFixedWidth(440)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(12)

        def val(k):
            return track[k] if hasattr(track, "keys") and k in track.keys() else getattr(track, k, "")

        self.edits = {}
        fields = [("title", "Titel"), ("artist", "Künstler"), ("album", "Album (Playlist)"),
                  ("year", "Jahr"), ("genre", "Genre")]
        for key, label in fields:
            lbl = QLabel(label)
            lbl.setObjectName("secondary")
            edit = QLineEdit(str(val(key) or ""))
            self.edits[key] = edit
            layout.addWidget(lbl)
            layout.addWidget(edit)

        btn_row = QHBoxLayout()
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        save_btn = QPushButton("Speichern")
        save_btn.setObjectName("accent")
        save_btn.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def values(self):
        return {k: e.text().strip() for k, e in self.edits.items()}


class MusicWindow(QMainWindow):
    def __init__(self, database: MusicDatabase, music_root: Path):
        super().__init__()
        self.db = database
        self.music_root = Path(music_root)
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(3)
        self.cancelled = threading.Event()
        self.resumed = threading.Event()
        self.resumed.set()
        self.paused = False

        # Playback state
        self.current_idx = None
        self.active_rows = []
        self.is_shuffle = False
        self.is_repeat = False

        # Media Player
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.75)
        self.player.mediaStatusChanged.connect(self._on_media_status)

        self.setWindowTitle("M-Player — Offline Music Manager")
        self.resize(1340, 840)
        self.setMinimumSize(1020, 660)

        self._build_ui()
        self.refresh_library()
        self.refresh_dashboard()

    def _button(self, text, slot, accent=False, obj_name=""):
        btn = QPushButton(text)
        btn.clicked.connect(slot)
        if accent:
            btn.setObjectName("accent")
        elif obj_name:
            btn.setObjectName(obj_name)
        return btn

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("centralWidget")
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # 1. Top Bar: App Title + Settings
        header = QHBoxLayout()
        title_lbl = QLabel("M-Player")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #F4F4F4;")
        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(self._button("⚙ Einstellungen", lambda: self.show_page(5)))
        main_layout.addLayout(header)

        # 2. Main Area: 240px Sidebar + Content Area
        body = QHBoxLayout()
        body.setSpacing(14)

        # Overhauled Sidebar (240px width, 48px buttons, 8px spacing, left-aligned)
        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("sidebarFrame")
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(8, 12, 8, 12)
        sidebar_layout.setSpacing(8)

        self.nav = QListWidget()
        self.nav.setObjectName("sidebarNav")
        self.nav.setFixedWidth(240)
        nav_items = [
            ("🎵   Downloader", 0),
            ("📚   Bibliothek", 1),
            ("❤️   Favoriten", 2),
            ("📋   Playlists", 3),
            ("⬇   Downloads", 4),
        ]
        for title, _ in nav_items:
            self.nav.addItem(title)
        self.nav.currentRowChanged.connect(self.show_page)
        sidebar_layout.addWidget(self.nav)
        sidebar_layout.addStretch()
        body.addWidget(sidebar_frame)

        # Right Content Area
        content_box = QVBoxLayout()
        content_box.setSpacing(10)

        # Dashboard / Statistics Bar
        self.stats_bar = self._build_dashboard_bar()
        content_box.addWidget(self.stats_bar)

        # Stacked Pages
        self.pages = QStackedWidget()
        self.pages.addWidget(self._downloader_page())   # 0
        self.pages.addWidget(self._library_page(False))  # 1
        self.pages.addWidget(self._library_page(True))   # 2
        self.pages.addWidget(self._playlists_page())     # 3
        self.pages.addWidget(self._queue_page())         # 4
        self.pages.addWidget(self._settings_page())      # 5
        content_box.addWidget(self.pages, 1)

        body.addLayout(content_box, 1)
        main_layout.addLayout(body, 1)

        # Bottom Mini Player
        main_layout.addWidget(self._player_bar())
        self.nav.setCurrentRow(1)

    def _build_dashboard_bar(self) -> QWidget:
        frame = QFrame()
        frame.setObjectName("toolbarFrame")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(14)

        self.stat_songs = QLabel("0")
        self.stat_albums = QLabel("0")
        self.stat_playlists = QLabel("0")
        self.stat_size = QLabel("0 MB")
        self.stat_duration = QLabel("0:00")

        for val_lbl, label_text in [
            (self.stat_songs, "Songs"),
            (self.stat_albums, "Alben"),
            (self.stat_playlists, "Playlists"),
            (self.stat_size, "Gesamtgröße"),
            (self.stat_duration, "Gesamtdauer")
        ]:
            badge = QFrame()
            badge.setObjectName("statBadge")
            b_layout = QVBoxLayout(badge)
            b_layout.setContentsMargins(12, 4, 12, 4)
            b_layout.setSpacing(1)
            val_lbl.setObjectName("statValue")
            desc = QLabel(label_text)
            desc.setObjectName("statLabel")
            b_layout.addWidget(val_lbl)
            b_layout.addWidget(desc)
            layout.addWidget(badge)

        layout.addStretch()
        return frame

    def refresh_dashboard(self):
        stats = self.db.dashboard_stats(self.music_root)
        self.stat_songs.setText(str(stats["songs"]))
        self.stat_albums.setText(str(stats["albums"]))
        self.stat_playlists.setText(str(stats["playlists"]))
        self.stat_size.setText(format_size(stats["size_bytes"]))
        dur_min = int(stats["duration"] // 60)
        dur_hrs = dur_min // 60
        self.stat_duration.setText(f"{dur_hrs}h {dur_min % 60}m" if dur_hrs > 0 else f"{dur_min}m")

    def _downloader_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        layout.addWidget(QLabel("<h2>Playlist & Song Import</h2>"))

        self.links = QLineEdit()
        self.links.setPlaceholderText("YouTube- / YouTube-Music- oder Spotify-Link eingeben …")
        layout.addWidget(self.links)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addWidget(self._button("Playlist analysieren", self.analyze, True))
        btn_row.addWidget(self._button("Alle auswählen", lambda: self.set_checked(True)))
        btn_row.addWidget(self._button("Alle abwählen", lambda: self.set_checked(False)))
        btn_row.addWidget(self._button("Nur neue Songs", self.only_new))
        btn_row.addStretch()
        self.start_btn = self._button("Download starten", self.start_download, True)
        btn_row.addWidget(self.start_btn)
        layout.addLayout(btn_row)

        self.pre_model = TrackModel(selectable=True)
        self.pre_table = self._create_styled_table(self.pre_model)
        layout.addWidget(self.pre_table, 1)

        self.pre_status = QLabel("Bereit für Link-Analyse.")
        self.pre_status.setObjectName("secondary")
        layout.addWidget(self.pre_status)
        return page

    def _library_page(self, favorites: bool) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        # Windows 11 Library Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("toolbarFrame")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(8, 6, 8, 6)
        tb_layout.setSpacing(10)

        refresh_btn = self._button("🔄 Bibliothek aktualisieren", self.run_sync_library, obj_name="toolbarBtn")
        delete_btn = self._button("🗑 Löschen", lambda: self.delete_selected_track(favorites), obj_name="toolbarBtn")
        folder_btn = self._button("📂 Ordner öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.music_root))), obj_name="toolbarBtn")
        cover_btn = self._button("🖼 Cover suchen", self.run_cover_search, obj_name="toolbarBtn")

        for b in [refresh_btn, delete_btn, folder_btn, cover_btn]:
            tb_layout.addWidget(b)

        tb_layout.addStretch()

        # View Toggle Buttons
        view_stack = QStackedWidget()
        list_toggle = self._button("≡ Liste", lambda: view_stack.setCurrentIndex(0), obj_name="toolbarBtn")
        grid_toggle = self._button("⊞ Raster", lambda: view_stack.setCurrentIndex(1), obj_name="toolbarBtn")
        tb_layout.addWidget(list_toggle)
        tb_layout.addWidget(grid_toggle)

        # Live Search Field on Right
        search_input = QLineEdit()
        search_input.setObjectName("searchBar")
        search_input.setPlaceholderText("🔍 Suchen …")
        search_input.setFixedWidth(240)
        search_input.textChanged.connect(self.on_search_changed)
        tb_layout.addWidget(search_input)

        layout.addWidget(toolbar)

        # Table View
        model = TrackModel(selectable=True)
        table = self._create_styled_table(model)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda p, t=table, m=model: self.context_menu(t, m, p))
        table.doubleClicked.connect(lambda idx, m=model: self.play(m.rows[idx.row()], idx.row(), m.rows))

        # Grid View
        grid = QListWidget()
        grid.setViewMode(QListWidget.IconMode)
        grid.setIconSize(QSize(140, 140))
        grid.setGridSize(QSize(170, 210))
        grid.setResizeMode(QListWidget.Adjust)
        grid.setSpacing(12)
        grid.itemDoubleClicked.connect(lambda item, m=model: self._on_grid_double_click(item, m))

        view_stack.addWidget(table)
        view_stack.addWidget(grid)
        layout.addWidget(view_stack, 1)

        if favorites:
            self.fav_model, self.fav_table, self.fav_grid, self.fav_search = model, table, grid, search_input
        else:
            self.lib_model, self.lib_table, self.lib_grid, self.lib_search = model, table, grid, search_input
        return page

    def _create_styled_table(self, model: TrackModel) -> QTableView:
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setDefaultSectionSize(64)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)

        header = table.horizontalHeader()
        header.setSectionsClickable(True)
        header.sectionClicked.connect(lambda col: self._on_header_clicked(col, model))

        # Exact column width specifications
        # Checkbox 36, Cover 56, Titel Stretch, Künstler 240, Album 220, Dauer 70, Jahr 60, Qualität 90, Status 110
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        table.setColumnWidth(0, 36)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        table.setColumnWidth(1, 56)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        table.setColumnWidth(3, 240)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        table.setColumnWidth(4, 220)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        table.setColumnWidth(5, 70)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        table.setColumnWidth(6, 60)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        table.setColumnWidth(7, 90)
        header.setSectionResizeMode(8, QHeaderView.Fixed)
        table.setColumnWidth(8, 110)
        return table

    def _on_header_clicked(self, col: int, model: TrackModel):
        if col == 0 and model.selectable:
            all_selected = (len(model.checked) == len(model.rows) and len(model.rows) > 0)
            if all_selected:
                model.checked.clear()
            else:
                model.checked = set(range(len(model.rows)))
            model.layoutChanged.emit()
            model.headerDataChanged.emit(Qt.Horizontal, 0, 0)

    def _queue_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("<h2>Aktive Downloads & Warteschlange</h2>"))
        header_row.addStretch()
        self.pause_btn = self._button("Pausieren", self.pause_download)
        self.retry_btn = self._button("🔄 Retry", self.retry_failed_downloads)
        self.cancel_btn = self._button("Abbrechen", self.cancel_download, obj_name="danger")
        header_row.addWidget(self.pause_btn)
        header_row.addWidget(self.retry_btn)
        header_row.addWidget(self.cancel_btn)
        layout.addLayout(header_row)

        self.queue_model = DownloadQueueModel()
        self.queue_table = QTableView()
        self.queue_table.setModel(self.queue_model)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue_table.verticalHeader().setDefaultSectionSize(60)
        self.queue_table.verticalHeader().setVisible(False)
        self.queue_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.queue_table, 1)

        self.queue_progress = QProgressBar()
        layout.addWidget(self.queue_progress)
        self.queue_summary = QLabel("Keine aktiven Downloads.")
        self.queue_summary.setObjectName("secondary")
        layout.addWidget(self.queue_summary)
        return page

    def _playlists_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(12)

        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("<h2>Playlists</h2>"))
        top_row.addStretch()
        top_row.addWidget(self._button("Neue Playlist anlegen", self.new_playlist, True))
        self.del_pl_btn = self._button("🗑 Playlist löschen", self.delete_current_playlist, obj_name="danger")
        top_row.addWidget(self.del_pl_btn)
        layout.addLayout(top_row)

        # Playlist cards grid view
        self.pl_cards = QListWidget()
        self.pl_cards.setViewMode(QListWidget.IconMode)
        self.pl_cards.setIconSize(QSize(140, 140))
        self.pl_cards.setGridSize(QSize(200, 240))
        self.pl_cards.setResizeMode(QListWidget.Adjust)
        self.pl_cards.setSpacing(14)
        self.pl_cards.itemClicked.connect(self._on_playlist_card_clicked)
        layout.addWidget(self.pl_cards, 1)

        # Playlist Songs Table
        self.pl_header_lbl = QLabel("Wähle eine Playlist aus")
        self.pl_header_lbl.setStyleSheet("font-weight: 700; font-size: 16px;")
        layout.addWidget(self.pl_header_lbl)

        self.pl_track_model = TrackModel(selectable=True)
        self.pl_table = self._create_styled_table(self.pl_track_model)
        self.pl_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pl_table.customContextMenuRequested.connect(lambda p: self.context_menu(self.pl_table, self.pl_track_model, p))
        self.pl_table.doubleClicked.connect(lambda idx: self.play(self.pl_track_model.rows[idx.row()], idx.row(), self.pl_track_model.rows))
        layout.addWidget(self.pl_table, 1)
        return page

    def _settings_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(14)

        layout.addWidget(QLabel("<h2>Einstellungen</h2>"))
        self.folder = QLineEdit(str(self.music_root))
        self.quality = QComboBox()
        self.quality.addItems(["320", "256", "192"])
        self.parallel = QComboBox()
        self.parallel.addItems(["3", "2", "1", "4", "5"])

        for label, widget in [("Musikordner", self.folder),
                              ("Standard-Audioqualität (kbps)", self.quality),
                              ("Gleichzeitige Downloads (max. 3 empfohlen)", self.parallel)]:
            layout.addWidget(QLabel(label))
            layout.addWidget(widget)

        layout.addWidget(self._button("Ordner auswählen …", self.choose_folder))
        layout.addWidget(self._button("Speichern", self.save_settings, True))
        layout.addStretch()
        return page

    def _player_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("playerBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(16)

        # Left: Cover + Titles
        left = QHBoxLayout()
        left.setSpacing(12)
        self.bar_cover = QLabel()
        self.bar_cover.setFixedSize(48, 48)
        self.bar_cover.setPixmap(get_cover_pixmap("", 48))
        left.addWidget(self.bar_cover)

        meta_box = QVBoxLayout()
        meta_box.setSpacing(2)
        self.now_title = QLabel("Kein Song ausgewählt")
        self.now_title.setStyleSheet("font-weight: 700; color: #F4F4F4;")
        self.now_artist = QLabel("Wähle einen Song aus der Bibliothek")
        self.now_artist.setObjectName("secondary")
        meta_box.addWidget(self.now_title)
        meta_box.addWidget(self.now_artist)
        left.addLayout(meta_box)
        layout.addLayout(left, 1)

        # Center: Playback Controls & Timeline
        center = QVBoxLayout()
        center.setSpacing(4)
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        ctrl_row.addStretch()

        self.shuffle_btn = self._button("🔀", self.toggle_shuffle, obj_name="playerBtn")
        self.prev_btn = self._button("⏮", lambda: self.skip(-1), obj_name="playerBtn")
        self.play_btn = self._button("▶", self.toggle_play, obj_name="playPauseBtn")
        self.next_btn = self._button("⏭", lambda: self.skip(1), obj_name="playerBtn")
        self.repeat_btn = self._button("🔁", self.toggle_repeat, obj_name="playerBtn")

        for b in (self.shuffle_btn, self.prev_btn, self.play_btn, self.next_btn, self.repeat_btn):
            ctrl_row.addWidget(b)
        ctrl_row.addStretch()
        center.addLayout(ctrl_row)

        timeline = QHBoxLayout()
        timeline.setSpacing(8)
        self.time_cur = QLabel("0:00")
        self.time_cur.setObjectName("secondary")
        self.timeline_slider = QSlider(Qt.Horizontal)
        self.timeline_slider.sliderMoved.connect(self.player.setPosition)
        self.time_total = QLabel("0:00")
        self.time_total.setObjectName("secondary")
        timeline.addWidget(self.time_cur)
        timeline.addWidget(self.timeline_slider, 1)
        timeline.addWidget(self.time_total)
        center.addLayout(timeline)
        layout.addLayout(center, 2)

        # Right: Volume Control
        right = QHBoxLayout()
        right.setSpacing(8)
        vol_icon = QLabel("🔊")
        vol_icon.setObjectName("secondary")
        vol_slider = QSlider(Qt.Horizontal)
        vol_slider.setFixedWidth(100)
        vol_slider.setRange(0, 100)
        vol_slider.setValue(75)
        vol_slider.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        right.addStretch()
        right.addWidget(vol_icon)
        right.addWidget(vol_slider)
        layout.addLayout(right, 1)

        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        return bar

    def show_page(self, index: int):
        self.pages.setCurrentIndex(index)
        if index in (1, 2):
            self.refresh_library()
        elif index == 3:
            self.refresh_playlists()

    def on_search_changed(self, text: str):
        self.refresh_library()

    def analyze(self):
        urls = [u for u in self.links.text().split() if u.startswith("http")]
        if not urls:
            QMessageBox.warning(self, "Link fehlt", "Bitte einen gültigen YouTube- oder Spotify-Link eingeben.")
            return
        self.pre_status.setText("Playlist wird analysiert …")
        task = AnalyzeTask(urls, self.music_root, self.db)
        task.signals.done.connect(self._analysis_done)
        task.signals.error.connect(lambda err: self.pre_status.setText(f"Fehler: {err}"))
        self.pool.start(task)

    def _analysis_done(self, tracks):
        self.pre_model.set_rows(tracks)
        self.pre_table.resizeColumnsToContents()
        self.pre_status.setText(f"{len(tracks)} Titel gefunden. Bereit zum Download.")

    def set_checked(self, checked: bool):
        if checked:
            self.pre_model.checked = set(range(len(self.pre_model.rows)))
        else:
            self.pre_model.checked = set()
        self.pre_model.layoutChanged.emit()
        self.pre_model.headerDataChanged.emit(Qt.Horizontal, 0, 0)

    def only_new(self):
        existing_urls = {r["source_url"] for r in self.db.tracks() if r["source_url"]}
        self.pre_model.checked = {
            i for i, t in enumerate(self.pre_model.rows)
            if (hasattr(t, "source_url") and t.source_url not in existing_urls)
        }
        self.pre_model.layoutChanged.emit()
        self.pre_model.headerDataChanged.emit(Qt.Horizontal, 0, 0)

    def start_download(self):
        items = [(i, self.pre_model.rows[i]) for i in sorted(self.pre_model.checked)]
        if not items:
            QMessageBox.information(self, "Keine Auswahl", "Bitte mindestens einen Song zum Download auswählen.")
            return

        self.cancelled.clear()
        self.resumed.set()
        self.paused = False
        self.nav.setCurrentRow(4)

        for step, (row_idx, track) in enumerate(items, 1):
            q_idx = self.queue_model.add_task(
                track.title,
                track.artist,
                track.cover_url,
                track_obj=track
            )
            task = DownloadTask(
                track, row_idx, q_idx, step, len(items),
                self.music_root, self.db, self.cancelled, self.resumed
            )
            task.signals.progress.connect(self._on_download_progress)
            task.signals.status.connect(self._on_download_status)
            self.pool.start(task)

    def _on_download_progress(self, q_idx: int, ratio: float, title: str, speed: str, eta: str):
        status = "Fertig" if ratio >= 1.0 else "Lädt..."
        self.queue_model.update_task(q_idx, ratio, speed, eta, status)
        self.queue_progress.setValue(int(ratio * 100))
        self.queue_summary.setText(f"Aktuell: {title} | Speed: {speed} | Restzeit: {eta}")

    def _on_download_status(self, row_idx: int, status: str):
        self.pre_model.status[row_idx] = status
        idx = self.pre_model.index(row_idx, 8)
        self.pre_model.dataChanged.emit(idx, idx)
        self.refresh_library()
        self.refresh_dashboard()

    def pause_download(self):
        self.paused = not self.paused
        if self.paused:
            self.resumed.clear()
            self.pause_btn.setText("Fortsetzen")
            self.queue_summary.setText("Downloads pausiert.")
        else:
            self.resumed.set()
            self.pause_btn.setText("Pausieren")
            self.queue_summary.setText("Downloads werden fortgesetzt.")

    def cancel_download(self):
        self.cancelled.set()
        self.pool.clear()
        self.queue_summary.setText("Abbruch angefordert.")

    def retry_failed_downloads(self):
        retries = 0
        for i, item in enumerate(self.queue_model.items):
            if "Fehler" in item["status"] or "Abgebrochen" in item["status"]:
                track = item.get("track")
                if track:
                    task = DownloadTask(track, i, i, 1, 1, self.music_root, self.db, self.cancelled, self.resumed)
                    task.signals.progress.connect(self._on_download_progress)
                    task.signals.status.connect(self._on_download_status)
                    self.pool.start(task)
                    retries += 1
        self.queue_summary.setText(f"{retries} Download(s) werden erneut versucht.")

    def run_sync_library(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Bibliothek wird synchronisiert …")
        dialog.setFixedWidth(380)
        d_layout = QVBoxLayout(dialog)
        lbl = QLabel("Dateisystem wird mit SQLite abgeglichen …")
        pbar = QProgressBar()
        pbar.setRange(0, 0)
        d_layout.addWidget(lbl)
        d_layout.addWidget(pbar)
        dialog.show()

        task = SyncLibraryTask(self.db, self.music_root)
        def on_prog(i, tot, name):
            pbar.setRange(0, tot)
            pbar.setValue(i)
            lbl.setText(f"Importiere: {name}")

        def on_done(res):
            dialog.accept()
            added, removed = res
            self.refresh_library()
            self.refresh_dashboard()
            QMessageBox.information(self, "Aktualisierung abgeschlossen",
                                    f"Bibliothek erfolgreich synchronisiert:\n+ {added} hinzugefügt\n- {removed} entfernt.")

        task.signals.sync_progress.connect(on_prog)
        task.signals.done.connect(on_done)
        task.signals.error.connect(lambda e: (dialog.reject(), QMessageBox.critical(self, "Fehler", e)))
        self.pool.start(task)

    def run_cover_search(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Albumcover suchen …")
        dialog.setFixedWidth(380)
        d_layout = QVBoxLayout(dialog)
        lbl = QLabel("Durchsuche iTunes, Deezer und MusicBrainz …")
        pbar = QProgressBar()
        d_layout.addWidget(lbl)
        d_layout.addWidget(pbar)
        dialog.show()

        task = CoverFinderTask(self.db, self.music_root)
        def on_prog(i, tot, name):
            pbar.setRange(0, tot)
            pbar.setValue(i)
            lbl.setText(f"Suche ({i}/{tot}): {name}")

        def on_done(found):
            dialog.accept()
            get_cover_pixmap.cache_clear()
            self.refresh_library()
            QMessageBox.information(self, "Cover-Suche beendet", f"{found} neue Albumcover gefunden und geladen.")

        task.signals.cover_progress.connect(on_prog)
        task.signals.done.connect(on_done)
        task.signals.error.connect(lambda e: (dialog.reject(), QMessageBox.critical(self, "Fehler", e)))
        self.pool.start(task)

    def delete_selected_track(self, favorites: bool = False):
        model = self.fav_model if favorites else self.lib_model
        selected = model.selected()
        if not selected:
            QMessageBox.information(self, "Auswahl fehlt", "Bitte mindestens einen Song per Checkbox auswählen.")
            return

        titles = ", ".join(t["title"] for t in selected[:3])
        more = f" und {len(selected) - 3} weitere" if len(selected) > 3 else ""
        ret = QMessageBox.question(
            self, "Löschen bestätigen",
            f"Möchtest du {len(selected)} Song(s) ({titles}{more}) wirklich dauerhaft von der Festplatte löschen?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret == QMessageBox.Yes:
            for track in selected:
                self.db.delete_track(track["id"])
            self.refresh_library()
            self.refresh_dashboard()

    def refresh_library(self):
        active_search = (
            self.fav_search.text().strip()
            if self.pages.currentIndex() == 2 and hasattr(self, "fav_search")
            else (self.lib_search.text().strip() if hasattr(self, "lib_search") else "")
        )
        all_tracks = self.db.tracks(active_search)
        fav_tracks = self.db.tracks(active_search, favorites=True)

        self.lib_model.set_rows(all_tracks)
        self.fav_model.set_rows(fav_tracks)
        self._populate_grid(self.lib_grid, all_tracks)
        self._populate_grid(self.fav_grid, fav_tracks)

    def _populate_grid(self, grid: QListWidget, tracks: list):
        grid.clear()
        for t in tracks:
            item = QListWidgetItem()
            item.setText(f"{t['title']}\n{t['artist']}")
            pix = get_cover_pixmap(t["file_path"], 140)
            item.setIcon(QIcon(pix))
            item.setData(Qt.UserRole, dict(t))
            grid.addItem(item)

    def _on_grid_double_click(self, item: QListWidgetItem, model: TrackModel):
        track = item.data(Qt.UserRole)
        if track:
            self.play(track, model=model.rows)

    def refresh_playlists(self):
        self.pl_cards.clear()
        for name in self.db.playlist_names():
            p_dir = self.music_root / safe_name(name, "playlist")
            tracks = self.db.playlist_tracks(name)
            count = len(tracks)
            # Calculate folder size
            total_size = 0
            if p_dir.exists():
                total_size = sum(f.stat().st_size for f in p_dir.glob("*.mp3"))

            card_item = QListWidgetItem()
            card_item.setText(f"📋 {name}\n{count} Songs • {format_size(total_size)}")
            cov_path = str(p_dir / "cover.jpg") if (p_dir / "cover.jpg").exists() else ""
            card_item.setIcon(QIcon(get_cover_pixmap(cov_path, 140)))
            card_item.setData(Qt.UserRole, name)
            self.pl_cards.addItem(card_item)

    def _on_playlist_card_clicked(self, item: QListWidgetItem):
        name = item.data(Qt.UserRole)
        if name:
            self.pl_header_lbl.setText(f"Playlist: {name}")
            tracks = self.db.playlist_tracks(name)
            self.pl_track_model.set_rows(tracks)

    def new_playlist(self):
        name, ok = QInputDialog.getText(self, "Neue Playlist", "Playlist-Name:")
        if ok and name.strip():
            self.db.create_playlist(name.strip())
            self.refresh_playlists()
            self.refresh_dashboard()

    def delete_current_playlist(self):
        item = self.pl_cards.currentItem()
        if not item:
            QMessageBox.information(self, "Keine Auswahl", "Bitte wähle eine Playlist-Karte aus.")
            return
        name = item.data(Qt.UserRole)
        ret = QMessageBox.question(
            self, "Playlist löschen",
            f"Möchtest du die Playlist '{name}' und den gesamten zugehörigen Ordner wirklich löschen?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret == QMessageBox.Yes:
            self.db.delete_playlist(name, self.music_root)
            self.pl_track_model.set_rows([])
            self.pl_header_lbl.setText("Wähle eine Playlist aus")
            self.refresh_playlists()
            self.refresh_library()
            self.refresh_dashboard()

    def play(self, track, index: int | None = None, model: list | None = None):
        self.active_rows = model or self.lib_model.rows
        self.current_idx = index if index is not None else (
            self.active_rows.index(track) if track in self.active_rows else 0
        )
        t_title = track["title"] if hasattr(track, "keys") else getattr(track, "title", "")
        t_artist = track["artist"] if hasattr(track, "keys") else getattr(track, "artist", "")
        f_path = track["file_path"] if hasattr(track, "keys") else getattr(track, "file_path", "")

        self.now_title.setText(t_title)
        self.now_artist.setText(t_artist)
        self.bar_cover.setPixmap(get_cover_pixmap(f_path, 48))

        self.player.setSource(QUrl.fromLocalFile(f_path))
        self.player.play()
        self.play_btn.setText("❚❚")

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_btn.setText("▶")
        else:
            self.player.play()
            self.play_btn.setText("❚❚")

    def skip(self, delta: int):
        if not self.active_rows:
            return
        if self.is_shuffle:
            new_idx = random.randint(0, len(self.active_rows) - 1)
        else:
            cur = self.current_idx or 0
            new_idx = (cur + delta) % len(self.active_rows)
        self.play(self.active_rows[new_idx], new_idx, self.active_rows)

    def toggle_shuffle(self):
        self.is_shuffle = not self.is_shuffle
        self.shuffle_btn.setStyleSheet("color: #3DDC63;" if self.is_shuffle else "")

    def toggle_repeat(self):
        self.is_repeat = not self.is_repeat
        self.repeat_btn.setStyleSheet("color: #3DDC63;" if self.is_repeat else "")

    def _on_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            if self.is_repeat:
                self.player.setPosition(0)
                self.player.play()
            else:
                self.skip(1)

    def _on_position_changed(self, pos):
        self.timeline_slider.setValue(pos)
        self.time_cur.setText(time_text(pos / 1000))

    def _on_duration_changed(self, dur):
        self.timeline_slider.setMaximum(dur)
        self.time_total.setText(time_text(dur / 1000))

    def context_menu(self, table: QTableView, model: TrackModel, point):
        idx = table.indexAt(point)
        if not idx.isValid():
            return
        track = model.rows[idx.row()]
        menu = QMenu(self)

        menu.addAction("▶  Abspielen", lambda: self.play(track, idx.row(), model.rows))
        file_path = Path(track["file_path"])
        menu.addAction("📂  Ordner öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path.parent))))
        menu.addAction("📄  Datei öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path))))
        menu.addAction("❤️  Favorit umschalten", lambda: (self.db.toggle_favorite(track["id"]), self.refresh_library()))
        menu.addAction("📝  Tags bearbeiten", lambda: self._edit_tags(track))
        menu.addAction("🗑  Song löschen", lambda: self._delete_single_song(track))
        menu.addAction("🔄  Neu herunterladen", lambda: self._re_download(track))

        pl_menu = menu.addMenu("📋  Zu Playlist hinzufügen")
        for pl_name in self.db.playlist_names():
            pl_menu.addAction(pl_name, lambda n=pl_name, tid=track["id"]: self.db.add_to_playlist(n, tid))

        menu.exec(table.viewport().mapToGlobal(point))

    def _delete_single_song(self, track):
        ret = QMessageBox.question(
            self, "Song löschen",
            f"Möchtest du '{track['title']}' wirklich von der Festplatte und aus der Bibliothek löschen?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret == QMessageBox.Yes:
            self.db.delete_track(track["id"])
            self.refresh_library()
            self.refresh_dashboard()

    def _edit_tags(self, track):
        dialog = TagEditorDialog(track, self)
        if dialog.exec():
            vals = dialog.values()
            self.db.update_track_tags(
                track["id"],
                vals["title"],
                vals["artist"],
                vals["album"],
                vals["year"],
                vals["genre"]
            )
            self.refresh_library()

    def _re_download(self, track):
        if track["source_url"]:
            self.links.setText(track["source_url"])
            self.nav.setCurrentRow(0)
            self.analyze()
        else:
            QMessageBox.information(self, "Keine Quell-URL", "Für diesen Song ist keine Quell-URL hinterlegt.")

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Musikordner wählen", self.folder.text())
        if folder:
            self.folder.setText(folder)

    def save_settings(self):
        self.music_root = Path(self.folder.text())
        self.db.set_setting("music_root", str(self.music_root))
        self.db.set_setting("quality", self.quality.currentText())
        self.db.set_setting("parallel", self.parallel.currentText())
        self.pool.setMaxThreadCount(int(self.parallel.currentText()))
        self.refresh_dashboard()
        QMessageBox.information(self, "Gespeichert", "Einstellungen erfolgreich gespeichert.")

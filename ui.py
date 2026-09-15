"""Windows 11 / Spotify-style UI for M-Player."""

from __future__ import annotations

import functools
import os
import random
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
from metadata import safe_name


def time_text(seconds: float) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 60}:{seconds % 60:02d}"


@functools.lru_cache(maxsize=300)
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
        # Generate clean dark fallback cover
        pix = QPixmap(size, size)
        pix.fill(QColor("#222730"))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QColor("#3DDC63"))
        painter.setFont(painter.font())
        painter.drawText(pix.rect(), Qt.AlignCenter, "🎵")
        painter.end()
        return pix

    scaled = pix.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    # Rounded corners
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

    def __init__(self, rows: list[object] | None = None, selectable: bool = False) -> None:
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
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
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
        self.items = []  # list of dicts: {title, artist, progress, speed, eta, status, cover_url}

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

    def add_task(self, title: str, artist: str = "", cover_url: str = ""):
        self.beginInsertRows(QModelIndex(), len(self.items), len(self.items))
        self.items.append({
            "title": title,
            "artist": artist,
            "cover_url": cover_url,
            "progress": 0.0,
            "speed": "--",
            "eta": "--",
            "status": "In Warteschlange"
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
    progress = Signal(int, float, str, str, str)  # row_idx, ratio, title, speed, eta
    status = Signal(int, str)


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


class TagEditorDialog(QDialog):
    def __init__(self, track, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Metadaten & ID3 bearbeiten")
        self.setFixedWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
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
        self.music_root = music_root
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(3)
        self.cancelled = threading.Event()
        self.resumed = threading.Event()
        self.resumed.set()
        self.paused = False

        # State
        self.current_idx = None
        self.active_model = None
        self.active_rows = []
        self.is_shuffle = False
        self.is_repeat = False

        # Media Player
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(0.75)
        self.player.mediaStatusChanged.connect(self._on_media_status)

        self.setWindowTitle("M-Player — Windows 11 Offline Music Manager")
        self.resize(1300, 820)
        self.setMinimumSize(980, 640)

        self._build_ui()
        self.refresh_library()

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
        main_layout.setContentsMargins(14, 12, 14, 12)
        main_layout.setSpacing(10)

        # Header Bar
        header = QHBoxLayout()
        title_lbl = QLabel("M-Player")
        title_lbl.setObjectName("titleLabel")
        header.addWidget(title_lbl)
        header.addStretch()
        header.addWidget(self._button("⚙ Einstellungen", lambda: self.show_page(5)))
        main_layout.addLayout(header)

        # Body: Sidebar + Main Content
        body = QHBoxLayout()
        body.setSpacing(12)

        # Sidebar
        sidebar_frame = QFrame()
        sidebar_frame.setObjectName("sidebarFrame")
        sidebar_layout = QVBoxLayout(sidebar_frame)
        sidebar_layout.setContentsMargins(6, 12, 6, 12)
        sidebar_layout.setSpacing(6)

        self.nav = QListWidget()
        self.nav.setObjectName("sidebarNav")
        self.nav.setFixedWidth(200)
        nav_items = [
            ("🎵  Downloader", 0),
            ("📚  Bibliothek", 1),
            ("❤️  Favoriten", 2),
            ("📋  Playlists", 3),
            ("⬇  Downloads", 4),
        ]
        for title, _ in nav_items:
            self.nav.addItem(title)
        self.nav.currentRowChanged.connect(self.show_page)
        sidebar_layout.addWidget(self.nav)
        sidebar_layout.addStretch()
        body.addWidget(sidebar_frame)

        # Content Area
        content_box = QVBoxLayout()
        content_box.setSpacing(10)

        # Live Search Bar
        self.search = QLineEdit()
        self.search.setObjectName("searchBar")
        self.search.setPlaceholderText("🔍  Titel, Künstler, Album oder Playlist live durchsuchen …")
        self.search.textChanged.connect(self.on_search_changed)
        content_box.addWidget(self.search)

        # Pages
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

    def _downloader_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header = QLabel("<h2>Playlist & Song Import</h2>")
        layout.addWidget(header)

        self.links = QLineEdit()
        self.links.setPlaceholderText("YouTube- / YouTube-Music- oder Spotify-Link eingeben")
        layout.addWidget(self.links)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self._button("Playlist analysieren", self.analyze, True))
        btn_row.addWidget(self._button("Alle auswählen", lambda: self.set_checked(True)))
        btn_row.addWidget(self._button("Alle abwählen", lambda: self.set_checked(False)))
        btn_row.addWidget(self._button("Nur neue Songs", self.only_new))
        btn_row.addStretch()
        self.start_btn = self._button("Download starten", self.start_download, True)
        btn_row.addWidget(self.start_btn)
        layout.addLayout(btn_row)

        self.pre_model = TrackModel(selectable=True)
        self.pre_table = QTableView()
        self.pre_table.setModel(self.pre_model)
        self.pre_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pre_table.verticalHeader().setDefaultSectionSize(60)
        self.pre_table.verticalHeader().setVisible(False)
        self.pre_table.setSortingEnabled(True)
        layout.addWidget(self.pre_table, 1)

        self.pre_status = QLabel("Bereit für Link-Analyse.")
        self.pre_status.setObjectName("secondary")
        layout.addWidget(self.pre_status)
        return page

    def _library_page(self, favorites: bool) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        top_row = QHBoxLayout()
        title_text = "<h2>Favoriten</h2>" if favorites else "<h2>Bibliothek</h2>"
        top_row.addWidget(QLabel(title_text))
        top_row.addStretch()

        # View Toggle: Table vs Grid
        view_stack = QStackedWidget()
        list_btn = self._button("≡ Liste", lambda: view_stack.setCurrentIndex(0))
        grid_btn = self._button("⊞ Cover-Raster", lambda: view_stack.setCurrentIndex(1))
        top_row.addWidget(list_btn)
        top_row.addWidget(grid_btn)
        layout.addLayout(top_row)

        # Table View
        model = TrackModel()
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setDefaultSectionSize(64)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda p, t=table, m=model: self.context_menu(t, m, p))
        table.doubleClicked.connect(lambda idx, m=model: self.play(m.rows[idx.row()], idx.row(), m.rows))

        # Column widths
        header = table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setMinimumSectionSize(220)

        # Grid View
        grid = QListWidget()
        grid.setViewMode(QListWidget.IconMode)
        grid.setIconSize(QSize(140, 140))
        grid.setGridSize(QSize(170, 200))
        grid.setResizeMode(QListWidget.Adjust)
        grid.setSpacing(10)
        grid.itemDoubleClicked.connect(lambda item, m=model: self._on_grid_double_click(item, m))

        view_stack.addWidget(table)
        view_stack.addWidget(grid)
        layout.addWidget(view_stack, 1)

        if favorites:
            self.fav_model, self.fav_table, self.fav_grid = model, table, grid
        else:
            self.lib_model, self.lib_table, self.lib_grid = model, table, grid
        return page

    def _queue_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("<h2>Aktive Downloads & Warteschlange</h2>"))
        header_row.addStretch()
        self.pause_btn = self._button("Pausieren", self.pause_download)
        self.cancel_btn = self._button("Abbrechen", self.cancel_download, obj_name="danger")
        header_row.addWidget(self.pause_btn)
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
        self.queue_summary = QLabel("Keine Downloads aktiv")
        self.queue_summary.setObjectName("secondary")
        layout.addWidget(self.queue_summary)
        return page

    def _playlists_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        row = QHBoxLayout()
        row.addWidget(QLabel("<h2>Lokale Playlists</h2>"))
        row.addStretch()
        row.addWidget(self._button("Neue Playlist anlegen", self.new_playlist, True))
        layout.addLayout(row)

        split = QHBoxLayout()
        self.playlist_list = QListWidget()
        self.playlist_list.setFixedWidth(240)
        self.playlist_list.itemSelectionChanged.connect(self.open_playlist)
        split.addWidget(self.playlist_list)

        self.pl_track_model = TrackModel()
        self.pl_table = QTableView()
        self.pl_table.setModel(self.pl_track_model)
        self.pl_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.pl_table.verticalHeader().setDefaultSectionSize(64)
        self.pl_table.verticalHeader().setVisible(False)
        self.pl_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.pl_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pl_table.customContextMenuRequested.connect(lambda p: self.context_menu(self.pl_table, self.pl_track_model, p))
        self.pl_table.doubleClicked.connect(lambda idx: self.play(self.pl_track_model.rows[idx.row()], idx.row(), self.pl_track_model.rows))
        split.addWidget(self.pl_table, 1)

        layout.addLayout(split, 1)
        return page

    def _settings_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        layout.addWidget(QLabel("<h2>Einstellungen</h2>"))
        self.folder = QLineEdit(str(self.music_root))
        self.quality = QComboBox()
        self.quality.addItems(["320", "256", "192"])
        self.parallel = QComboBox()
        self.parallel.addItems(["3", "2", "1", "4", "5"])

        for label, widget in [("Musikordner", self.folder),
                              ("Standard-Audioqualität (kbps)", self.quality),
                              ("Gleichzeitige Downloads", self.parallel)]:
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
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(16)

        # Left: Cover & Titles
        left = QHBoxLayout()
        left.setSpacing(12)
        self.bar_cover = QLabel()
        self.bar_cover.setFixedSize(48, 48)
        self.bar_cover.setPixmap(get_cover_pixmap("", 48))
        left.addWidget(self.bar_cover)

        meta_box = QVBoxLayout()
        meta_box.setSpacing(2)
        self.now_title = QLabel("Kein Song ausgewählt")
        self.now_title.setStyleSheet("font-weight: 700;")
        self.now_artist = QLabel("Wähle einen Song aus der Bibliothek")
        self.now_artist.setObjectName("secondary")
        meta_box.addWidget(self.now_title)
        meta_box.addWidget(self.now_artist)
        left.addLayout(meta_box)
        layout.addLayout(left, 1)

        # Center: Playback Controls & Slider
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

        # Player Signals
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

    def only_new(self):
        existing_urls = {r["source_url"] for r in self.db.tracks() if r["source_url"]}
        self.pre_model.checked = {
            i for i, t in enumerate(self.pre_model.rows)
            if (hasattr(t, "source_url") and t.source_url not in existing_urls)
        }
        self.pre_model.layoutChanged.emit()

    def start_download(self):
        items = [(i, self.pre_model.rows[i]) for i in sorted(self.pre_model.checked)]
        if not items:
            QMessageBox.information(self, "Keine Auswahl", "Bitte mindestens einen Song zum Download anhaken.")
            return

        self.cancelled.clear()
        self.resumed.set()
        self.paused = False
        self.nav.setCurrentRow(4)  # Switch to Downloads Queue page

        for step, (row_idx, track) in enumerate(items, 1):
            q_idx = self.queue_model.add_task(
                track.title,
                track.artist,
                track.cover_url
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
        self.queue_summary.setText("Abbruch eingeleitet.")

    def refresh_library(self):
        query = self.search.text().strip()
        all_tracks = self.db.tracks(query)
        fav_tracks = self.db.tracks(query, favorites=True)

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
        self.playlist_list.clear()
        for name in self.db.playlist_names():
            self.playlist_list.addItem(name)

    def open_playlist(self):
        items = self.playlist_list.selectedItems()
        if items:
            tracks = self.db.playlist_tracks(items[0].text())
            self.pl_track_model.set_rows(tracks)

    def new_playlist(self):
        name, ok = QInputDialog.getText(self, "Neue Playlist", "Playlist-Name:")
        if ok and name.strip():
            self.db.create_playlist(name.strip())
            self.refresh_playlists()

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
        menu.addAction("🔄  Neu herunterladen", lambda: self._re_download(track))

        # Playlist Submenu
        pl_menu = menu.addMenu("📋  Zu Playlist hinzufügen")
        for pl_name in self.db.playlist_names():
            pl_menu.addAction(pl_name, lambda n=pl_name, tid=track["id"]: self.db.add_to_playlist(n, tid))

        menu.exec(table.viewport().mapToGlobal(point))

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
        QMessageBox.information(self, "Gespeichert", "Einstellungen erfolgreich gespeichert.")

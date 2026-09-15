"""PySide6 Windows-11-style UI for the offline music library."""

from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QObject, QRunnable, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QMainWindow, QMenu, QMessageBox, QPushButton, QProgressBar,
    QSlider, QStackedWidget, QTableView, QVBoxLayout, QWidget)

from database import MusicDatabase
from downloader import DownloadCancelled, MusicDownloader


def time_text(seconds: float) -> str:
    seconds = int(seconds or 0)
    return f"{seconds // 60}:{seconds % 60:02d}"


class TrackModel(QAbstractTableModel):
    headers = ["□", "Titel", "Künstler", "Album", "Dauer", "Qualität", "Status", "Datei"]

    def __init__(self, rows: list[object] | None = None, selectable: bool = False) -> None:
        super().__init__(); self.rows = rows or []; self.selectable = selectable; self.checked = set(); self.status = {}

    def rowCount(self, parent=QModelIndex()): return len(self.rows)
    def columnCount(self, parent=QModelIndex()): return len(self.headers)
    def headerData(self, section, orientation, role=Qt.DisplayRole): return self.headers[section] if orientation == Qt.Horizontal and role == Qt.DisplayRole else None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid(): return None
        item, col = self.rows[index.row()], index.column()
        if col == 0 and self.selectable and role == Qt.CheckStateRole: return Qt.Checked if index.row() in self.checked else Qt.Unchecked
        if role != Qt.DisplayRole: return None
        def value(key, default=""):
            if isinstance(item, dict): return item.get(key, default)
            if hasattr(item, key): return getattr(item, key)
            if hasattr(item, "keys") and key in item.keys(): return item[key]
            return default
        values = ["", value("title"), value("artist"), value("album"), time_text(value("duration")) if value("duration") else "-", f"{value('bitrate')} kbps" if value("bitrate") else "MP3", self.status.get(index.row(), "Bereit"), value("file_path") or "-"]
        return values[col]

    def flags(self, index):
        flags = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        return flags | Qt.ItemIsUserCheckable if self.selectable and index.column() == 0 else flags

    def setData(self, index, value, role=Qt.EditRole):
        if self.selectable and index.column() == 0 and role == Qt.CheckStateRole:
            (self.checked.add if value in (Qt.Checked, Qt.CheckState.Checked, 2) else self.checked.discard)(index.row())
            self.dataChanged.emit(index, index)
            return True
        return False

    def set_rows(self, rows): self.beginResetModel(); self.rows = list(rows); self.checked = set(range(len(self.rows))) if self.selectable else set(); self.status = {}; self.endResetModel()
    def selected(self): return [self.rows[i] for i in sorted(self.checked)]


class Signals(QObject):
    done = Signal(object); error = Signal(str); progress = Signal(float, str); status = Signal(int, str)


class AnalyzeTask(QRunnable):
    def __init__(self, urls, root, db): super().__init__(); self.urls, self.root, self.db, self.signals = urls, root, db, Signals()
    def run(self):
        try:
            tracks = []
            loader = MusicDownloader(self.root, self.db)
            for url in self.urls: tracks.extend(loader._spotify_sources(url) if loader.is_spotify(url) else loader._youtube_sources(url))
            self.signals.done.emit(tracks)
        except Exception as exc: self.signals.error.emit(str(exc))


class DownloadTask(QRunnable):
    def __init__(self, track, row_idx, step, total, root, db, cancelled, resumed):
        super().__init__(); self.track, self.row_idx, self.step, self.total, self.root, self.db, self.cancelled, self.resumed, self.signals = track, row_idx, step, total, root, db, cancelled, resumed, Signals()
    def run(self):
        try:
            loader = MusicDownloader(self.root, self.db, self.cancelled, self.resumed)
            loader._download_one(self.track, self.step, self.total, lambda value, title: self.signals.progress.emit(value, title))
            self.signals.status.emit(self.row_idx, "Fertig")
        except DownloadCancelled: self.signals.status.emit(self.row_idx, "Abgebrochen")
        except Exception as exc: self.signals.status.emit(self.row_idx, f"Fehler: {exc}")


class MusicWindow(QMainWindow):
    def __init__(self, database: MusicDatabase, music_root: Path):
        super().__init__(); self.db, self.music_root = database, music_root; self.pool = QThreadPool(); self.cancelled = threading.Event(); self.resumed = threading.Event(); self.resumed.set(); self.queue = []; self.paused = False
        self.player, self.audio = QMediaPlayer(), QAudioOutput(); self.player.setAudioOutput(self.audio); self.audio.setVolume(.7)
        self.current_idx, self.active_model = None, None
        self.setWindowTitle("M-Player"); self.resize(1220, 760); self._build(); self.refresh_library()

    def _button(self, text, slot, accent=False):
        button = QPushButton(text); button.clicked.connect(slot); button.setObjectName("accent" if accent else ""); return button

    def _build(self):
        root = QWidget(); self.setCentralWidget(root); outer = QVBoxLayout(root); outer.setContentsMargins(18, 14, 18, 14)
        header = QHBoxLayout(); header.addWidget(QLabel("<h2>M-Player</h2>")); header.addStretch(); header.addWidget(self._button("⚙ Einstellungen", lambda: self.nav.setCurrentRow(4))); outer.addLayout(header)
        self.search = QLineEdit(); self.search.setPlaceholderText("🔍  Bibliothek durchsuchen …"); self.search.textChanged.connect(self.refresh_library); outer.addWidget(self.search)
        body = QHBoxLayout(); self.nav = QListWidget(); self.nav.addItems(["🎵  Downloader", "📚  Bibliothek", "❤️  Favoriten", "📋  Playlists", "⚙  Einstellungen"]); self.nav.setFixedWidth(190); self.nav.currentRowChanged.connect(self.show_page); body.addWidget(self.nav)
        self.pages = QStackedWidget(); self.pages.addWidget(self._downloader_page()); self.pages.addWidget(self._library_page(False)); self.pages.addWidget(self._library_page(True)); self.pages.addWidget(self._playlists_page()); self.pages.addWidget(self._settings_page()); body.addWidget(self.pages, 1); outer.addLayout(body, 1)
        outer.addWidget(self._player_bar()); self.nav.setCurrentRow(0)

    def _downloader_page(self):
        page = QFrame(); page.setObjectName("card"); layout = QVBoxLayout(page); layout.addWidget(QLabel("<h2>Download Queue</h2>")); self.links = QLineEdit(); self.links.setPlaceholderText("YouTube-/YouTube-Music-Link(s), mehrere mit Leerzeichen eingeben"); layout.addWidget(self.links)
        row = QHBoxLayout(); row.addWidget(self._button("Playlist analysieren", self.analyze, True)); row.addWidget(self._button("Alles auswählen", lambda: self.set_checked(True))); row.addWidget(self._button("Alles abwählen", lambda: self.set_checked(False))); row.addWidget(self._button("Nur neue", self.only_new)); row.addStretch(); self.start = self._button("Download starten", self.start_download, True); self.pause = self._button("Download pausieren", self.pause_download); self.abort = self._button("Abbrechen", self.cancel_download); self.abort.setObjectName("danger"); [row.addWidget(x) for x in (self.start, self.pause, self.abort)]; layout.addLayout(row)
        self.queue_model = TrackModel(selectable=True); self.queue_table = QTableView(); self.queue_table.setModel(self.queue_model); self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows); self.queue_table.setSortingEnabled(True); layout.addWidget(self.queue_table, 1)
        self.progress = QProgressBar(); self.queue_status = QLabel("Bereit"); layout.addWidget(self.progress); layout.addWidget(self.queue_status); return page

    def _library_page(self, favorites):
        page = QFrame(); page.setObjectName("card"); layout = QVBoxLayout(page); layout.addWidget(QLabel("<h2>Favoriten</h2>" if favorites else "<h2>Bibliothek</h2>")); model = TrackModel(); table = QTableView(); table.setModel(model); table.setSelectionBehavior(QAbstractItemView.SelectRows); table.setSortingEnabled(True); table.setContextMenuPolicy(Qt.CustomContextMenu); table.customContextMenuRequested.connect(lambda p, t=table, m=model: self.context_menu(t, m, p)); table.doubleClicked.connect(lambda idx, m=model: self.play(m.rows[idx.row()], idx.row(), m)); layout.addWidget(table)
        if favorites: self.fav_model, self.fav_table = model, table
        else: self.library_model, self.library_table = model, table
        return page

    def _playlists_page(self):
        page = QFrame(); page.setObjectName("card"); layout = QVBoxLayout(page); row = QHBoxLayout(); row.addWidget(QLabel("<h2>Lokale Playlists</h2>")); row.addStretch(); row.addWidget(self._button("Neue Playlist", self.new_playlist, True)); layout.addLayout(row); self.playlists = QListWidget(); self.playlists.itemSelectionChanged.connect(self.open_playlist); layout.addWidget(self.playlists); return page

    def _settings_page(self):
        page = QFrame(); page.setObjectName("card"); layout = QVBoxLayout(page); layout.addWidget(QLabel("<h2>Einstellungen</h2>")); self.folder = QLineEdit(str(self.music_root)); self.quality = QComboBox(); self.quality.addItems(["320", "256", "192"]); self.parallel = QComboBox(); self.parallel.addItems(["1", "2", "3", "4", "5"])
        for label, widget in (("Musikordner", self.folder), ("Standardqualität (kbps)", self.quality), ("Gleichzeitige Downloads", self.parallel)): layout.addWidget(QLabel(label)); layout.addWidget(widget)
        layout.addWidget(self._button("Ordner wählen", self.choose_folder)); layout.addWidget(self._button("Speichern", self.save_settings, True)); layout.addStretch(); return page

    def _player_bar(self):
        card = QFrame(); card.setObjectName("card"); row = QHBoxLayout(card); self.now = QLabel("Nichts wird abgespielt"); row.addWidget(self._button("⏮", lambda: self.skip(-1))); row.addWidget(self._button("▶ / ❚❚", self.toggle_play)); row.addWidget(self._button("⏭", lambda: self.skip(1))); row.addWidget(self.now, 1); self.position = QSlider(Qt.Horizontal); self.position.sliderMoved.connect(self.player.setPosition); row.addWidget(self.position, 2); volume = QSlider(Qt.Horizontal); volume.setRange(0, 100); volume.setValue(70); volume.valueChanged.connect(lambda v: self.audio.setVolume(v / 100)); row.addWidget(volume); self.player.positionChanged.connect(self.position.setValue); self.player.durationChanged.connect(self.position.setMaximum); return card

    def show_page(self, index): self.pages.setCurrentIndex(index); self.refresh_library()
    def analyze(self):
        urls = [url for url in self.links.text().split() if url.startswith("http")]
        if not urls: return QMessageBox.warning(self, "Link fehlt", "Bitte mindestens einen gültigen Link eingeben.")
        self.queue_status.setText("Playlist wird analysiert …"); task = AnalyzeTask(urls, self.music_root, self.db); task.signals.done.connect(self.analysis_done); task.signals.error.connect(lambda e: self.queue_status.setText(e)); self.pool.start(task)
    def analysis_done(self, tracks):
        self.queue = tracks; self.queue_model.set_rows(tracks); self.queue_status.setText(f"{len(tracks)} Titel gefunden")
        self.queue_table.resizeColumnsToContents()
    def set_checked(self, checked): self.queue_model.checked = set(range(len(self.queue_model.rows))) if checked else set(); self.queue_model.layoutChanged.emit()
    def only_new(self): self.queue_model.checked = {i for i, t in enumerate(self.queue_model.rows) if not any(r["source_url"] == t.source_url for r in self.db.tracks())}; self.queue_model.layoutChanged.emit()
    def start_download(self):
        items = [(i, self.queue_model.rows[i]) for i in sorted(self.queue_model.checked)]
        if not items: return
        self.cancelled.clear(); self.resumed.set(); self.paused = False; self.pool.setMaxThreadCount(int(self.parallel.currentText())); self.progress.setValue(0)
        for step, (row_idx, track) in enumerate(items, 1):
            task = DownloadTask(track, row_idx, step, len(items), self.music_root, self.db, self.cancelled, self.resumed)
            task.signals.progress.connect(self.download_progress); task.signals.status.connect(self.download_status); self.pool.start(task)
        self.queue_status.setText(f"{len(items)} Downloads gestartet")
    def download_progress(self, value, title): self.progress.setValue(int(value * 100)); self.queue_status.setText(f"Lädt: {title}")
    def download_status(self, row, status): self.queue_model.status[row] = status; self.queue_model.layoutChanged.emit(); self.refresh_library()
    def pause_download(self):
        self.paused = not self.paused
        (self.resumed.clear if self.paused else self.resumed.set)()
        self.pause.setText("Download fortsetzen" if self.paused else "Download pausieren")
        self.queue_status.setText("Downloads pausiert." if self.paused else "Downloads werden fortgesetzt.")
    def cancel_download(self): self.cancelled.set(); self.pool.clear(); self.queue_status.setText("Abbruch angefordert – temporäre Dateien werden verworfen.")
    def refresh_library(self):
        if hasattr(self, "library_model"):
            rows = self.db.tracks(self.search.text()); self.library_model.set_rows(rows); self.fav_model.set_rows(self.db.tracks(self.search.text(), True)); self.playlists.clear(); self.playlists.addItems(self.db.playlist_names())
    def context_menu(self, table, model, point):
        index = table.indexAt(point)
        if not index.isValid(): return
        track = model.rows[index.row()]; menu = QMenu(self); menu.addAction("Abspielen", lambda: self.play(track, index.row(), model)); menu.addAction("Ordner öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(track["file_path"]).parent)))); menu.addAction("Datei öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(track["file_path"]))); menu.addAction("Favorit umschalten", lambda: (self.db.toggle_favorite(track["id"]), self.refresh_library()))
        playlists = self.db.playlist_names()
        if playlists:
            pl_menu = menu.addMenu("Zu Playlist hinzufügen")
            for name in playlists:
                pl_menu.addAction(name, lambda n=name, tid=track["id"]: self.db.add_to_playlist(n, tid))
        menu.exec(table.viewport().mapToGlobal(point))
    def play(self, track, index=None, model=None):
        self.current_idx = index
        self.active_model = model or getattr(self, "library_model", None)
        self.now.setText(f"{track['artist']} – {track['title']}"); self.player.setSource(QUrl.fromLocalFile(track["file_path"])); self.player.play()
    def skip(self, delta):
        model = getattr(self, "active_model", None) or getattr(self, "library_model", None)
        if not model or not model.rows or self.current_idx is None: return
        new_idx = max(0, min(len(model.rows) - 1, self.current_idx + delta))
        self.play(model.rows[new_idx], new_idx, model)
    def toggle_play(self): self.player.pause() if self.player.playbackState() == QMediaPlayer.PlayingState else self.player.play()
    def new_playlist(self):
        name, ok = QInputDialog.getText(self, "Playlist", "Name:");
        if ok and name: self.db.create_playlist(name); self.refresh_library()
    def open_playlist(self):
        items = self.playlists.selectedItems()
        if items: self.library_model.set_rows(self.db.playlist_tracks(items[0].text()))
    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Musikordner", self.folder.text());
        if folder: self.folder.setText(folder)
    def save_settings(self):
        self.music_root = Path(self.folder.text()); self.db.set_setting("music_root", str(self.music_root)); self.db.set_setting("quality", self.quality.currentText()); self.db.set_setting("parallel", self.parallel.currentText()); QMessageBox.information(self, "Gespeichert", "Einstellungen gespeichert.")

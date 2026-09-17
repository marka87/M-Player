"""M-Player UI Polish v1.1 — Windows 11 / Spotify-style UI for PySide6."""

from __future__ import annotations

import functools
import os
import random
import shutil
import threading
from pathlib import Path

from PySide6.QtCore import (QAbstractTableModel, QModelIndex, QObject, QRunnable,
                            QSize, Qt, QThreadPool, QTimer, QUrl, Signal)
from PySide6.QtGui import (QAction, QColor, QDesktopServices, QFont, QFontMetrics, QIcon,
                           QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
                             QFrame, QHBoxLayout, QHeaderView, QInputDialog,
                             QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMainWindow, QMenu, QMessageBox, QProgressBar,
                             QPushButton, QScrollArea, QSizePolicy, QSlider, QStackedWidget, QSystemTrayIcon,
                             QTableView, QVBoxLayout, QWidget)
import subprocess
import sys
import urllib.parse

from database import MusicDatabase
from downloader import DownloadCancelled, MusicDownloader, get_stream_url
from metadata import TrackMetadata, safe_name, read_audio_tags, clean_artist_title, clean_track_id3
from mini_player import MiniPlayerWindow
from recommendations import fetch_recommendations


class ClickableSlider(QSlider):
    """Direct-seek horizontal slider for instantaneous timeline jumping on click."""
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            width = max(1, self.width())
            pos = event.position().x() if hasattr(event, "position") else event.x()
            ratio = max(0.0, min(1.0, pos / width))
            val = self.minimum() + ratio * (self.maximum() - self.minimum())
            self.setValue(int(val))
            self.sliderMoved.emit(int(val))
        super().mousePressEvent(event)


from PySide6.QtWidgets import QStyledItemDelegate, QStyle
from PySide6.QtCore import QRect
class GridCardDelegate(QStyledItemDelegate):
    """Theme-aware item delegate for rendering song and album cards in grid mode."""
    def paint(self, painter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRect(option.rect)
        rect.adjust(6, 6, -6, -6)  # Card margin

        is_hover = bool(option.state & QStyle.State_MouseOver)
        is_selected = bool(option.state & QStyle.State_Selected)

        # Modern Dark Card Styling
        bg_color = QColor("#222832") if is_hover else (QColor("#1A2421") if is_selected else QColor("#161A20"))
        border_color = QColor("#3DDC63") if (is_hover or is_selected) else QColor("#262E38")
        title_color = QColor("#FFFFFF")
        artist_color = QColor("#A7A7A7")

        # Draw card background & border
        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        painter.fillPath(path, bg_color)
        painter.strokePath(path, QPen(border_color, 1))

        # Retrieve track or playlist data
        track = index.data(Qt.UserRole)
        icon = index.data(Qt.DecorationRole)

        # Draw Cover centered (130x130)
        cover_size = 130
        img_x = rect.x() + (rect.width() - cover_size) // 2
        img_y = rect.y() + 8
        if icon:
            pixmap = icon.pixmap(cover_size, cover_size)
            painter.drawPixmap(QRect(img_x, img_y, cover_size, cover_size), pixmap)

        if isinstance(track, dict):
            title = track.get("title") or "Unbekannt"
            artist = track.get("artist") or "Unbekannt"
        else:
            raw_text = index.data(Qt.DisplayRole) or ""
            parts = raw_text.split("\n")
            title = parts[0] if parts else (str(track) if track else "Unbekannt")
            artist = parts[1] if len(parts) > 1 else ""

        # Draw Song Title (12px, bold, elided)
        title_font = QFont(option.font)
        title_font.setPixelSize(12)
        title_font.setBold(True)
        painter.setFont(title_font)
        fm_title = QFontMetrics(title_font)

        text_width = max(10, rect.width() - 16)
        text_rect = QRect(rect.x() + 8, img_y + cover_size + 6, text_width, 18)
        elided_title = fm_title.elidedText(title, Qt.ElideRight, text_width)
        painter.setPen(title_color)
        painter.drawText(text_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_title)

        # Draw Artist (11px, elided)
        artist_font = QFont(option.font)
        artist_font.setPixelSize(11)
        artist_font.setBold(False)
        painter.setFont(artist_font)
        fm_artist = QFontMetrics(artist_font)

        artist_rect = QRect(rect.x() + 8, text_rect.bottom() + 2, text_width, 16)
        elided_artist = fm_artist.elidedText(artist, Qt.ElideRight, text_width)
        painter.setPen(artist_color)
        painter.drawText(artist_rect, Qt.AlignLeft | Qt.AlignVCenter, elided_artist)

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(176, 216)


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


def _track_id(track) -> int | None:
    if not track:
        return None
    if isinstance(track, dict):
        return track.get("id")
    if hasattr(track, "keys") and "id" in track.keys():
        return track["id"]
    return getattr(track, "id", None)


ICON_DIR = Path(__file__).resolve().parent / "assets" / "icons"


def get_icon(name: str) -> QIcon:
    svg_path = ICON_DIR / f"{name}.svg"
    if svg_path.is_file():
        return QIcon(str(svg_path))
    return QIcon()


@functools.lru_cache(maxsize=600)
def get_cover_pixmap(cover_source: str, size: int = 48) -> QPixmap:
    pix = QPixmap()
    if cover_source:
        if cover_source.startswith(("http://", "https://")):
            try:
                import hashlib, tempfile, urllib.request
                h = hashlib.md5(cover_source.encode()).hexdigest()
                cached = Path(tempfile.gettempdir()) / "mplayer_thumbs" / f"{h}.jpg"
                if cached.is_file() and cached.stat().st_size > 0:
                    pix.load(str(cached))
                else:
                    cached.parent.mkdir(parents=True, exist_ok=True)
                    req = urllib.request.Request(cover_source, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=1.5) as resp:
                        c_data = resp.read()
                    if c_data:
                        cached.write_bytes(c_data)
                        pix.loadFromData(c_data)
            except Exception:
                pass
        else:
            p = Path(cover_source)
            if p.is_file():
                if p.suffix.lower() == ".mp3":
                    # 1. Embedded ID3 APIC frame (individual track cover art)
                    try:
                        from mutagen.id3 import ID3
                        tags = ID3(p)
                        for apic in tags.getall("APIC"):
                            if apic.data:
                                pix.loadFromData(apic.data)
                                break
                    except Exception:
                        pass
                    # 2. Folder cover.jpg fallback (for complete albums)
                    if pix.isNull() and (p.parent / "cover.jpg").is_file():
                        pix.load(str(p.parent / "cover.jpg"))
                else:
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
        ico = get_icon("library").pixmap(int(size * 0.5), int(size * 0.5))
        painter.drawPixmap((size - ico.width()) // 2, (size - ico.height()) // 2, ico)
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
    def __init__(self, rows=None, selectable=True):
        super().__init__()
        self.rows = list(rows or [])
        self.selectable = selectable
        self.checked = set()
        self.status = {}
        self._sort_col: int | None = None
        self._sort_order = Qt.AscendingOrder
        self.headers = ["", "Cover", "Titel", "Künstler", "Album", "Dauer", "Jahr", "Bitrate", "Status"]

    def rowCount(self, parent=QModelIndex()):
        return len(self.rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.headers)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if section == 0:
                if role == Qt.DecorationRole:
                    all_c = len(self.checked) == len(self.rows) and len(self.rows) > 0
                    return get_icon("check-square-active") if all_c else get_icon("square")
                if role == Qt.DisplayRole:
                    return ""
                if role == Qt.ToolTipRole:
                    return "Klicken: Alle auswählen / abwählen"
            if role == Qt.DisplayRole:
                return self.headers[section]
        return None

    @staticmethod
    def _val(item, key, default=""):
        if isinstance(item, dict):
            return item.get(key, default)
        if hasattr(item, key):
            return getattr(item, key)
        if hasattr(item, "keys") and key in item.keys():
            return item[key]
        return default

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        item = self.rows[row]

        if col == 0 and self.selectable and role == Qt.CheckStateRole:
            return Qt.Checked if row in self.checked else Qt.Unchecked

        if col == 1:
            if role == Qt.DecorationRole:
                path = self._val(item, "file_path") or self._val(item, "cover_url")
                return get_cover_pixmap(str(path), 48)
            return None

        if role == Qt.TextAlignmentRole and col == 5:
            return int(Qt.AlignRight | Qt.AlignVCenter)

        if role == Qt.DisplayRole:
            values = [
                "",
                "",
                self._val(item, "title"),
                self._val(item, "artist"),
                self._val(item, "album"),
                time_text(self._val(item, "duration")) if self._val(item, "duration") else "--:--",
                str(self._val(item, "year") or "-"),
                f"{self._val(item, 'bitrate')} kbps" if self._val(item, "bitrate") else "320 kbps",
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

    def _apply_sort(self, column: int, order: Qt.SortOrder) -> None:
        col_map = {
            2: "title",
            3: "artist",
            4: "album",
            5: "duration",
            6: "year",
            7: "bitrate",
            8: "status",
        }
        key_name = col_map.get(column)
        if not key_name or not self.rows:
            return

        status_map = dict(self.status)

        def sort_key(item):
            if key_name == "status":
                row_idx = self.rows.index(item) if item in self.rows else -1
                return status_map.get(row_idx, "Bereit").lower()
            val = self._val(item, key_name, "")
            if key_name in ("duration", "bitrate"):
                try:
                    return float(val or 0)
                except (ValueError, TypeError):
                    return 0.0
            if key_name == "year":
                try:
                    return int(str(val).strip()[:4])
                except (ValueError, TypeError):
                    return 0
            return str(val or "").lower()

        self.rows.sort(key=sort_key, reverse=(order == Qt.DescendingOrder))

    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder) -> None:
        if column < 2 or not self.rows:
            return
        self._sort_col = column
        self._sort_order = order

        self.layoutAboutToBeChanged.emit()

        checked_objs = {id(self.rows[i]) for i in self.checked if i < len(self.rows)}
        status_objs = {id(self.rows[i]): st for i, st in self.status.items() if i < len(self.rows)}

        self._apply_sort(column, order)

        self.checked = {i for i, r in enumerate(self.rows) if id(r) in checked_objs}
        self.status = {i: status_objs[id(r)] for i, r in enumerate(self.rows) if id(r) in status_objs}

        self.layoutChanged.emit()

    def set_rows(self, rows, select_all=False):
        self.beginResetModel()
        old_ids = {self._val(self.rows[i], "id") for i in self.checked if i < len(self.rows)} if not select_all else set()
        self.rows = list(rows)
        if getattr(self, "_sort_col", None) is not None:
            self._apply_sort(self._sort_col, self._sort_order)
        if select_all or not old_ids:
            self.checked = set(range(len(self.rows))) if self.selectable else set()
        else:
            self.checked = {i for i, r in enumerate(self.rows) if self._val(r, "id") in old_ids}
        self.status = {}
        self.endResetModel()

    def selected(self):
        return [self.rows[i] for i in sorted(self.checked)]


class DownloadQueueModel(QAbstractTableModel):
    headers = ["Cover", "Titel", "Playlist", "Status", "%", "Speed", "ETA"]

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
                return item.get("playlist", "Single") or "Single"
            if col == 3:
                return item.get("status", "Bereit")
            if col == 4:
                return f"{int(item.get('progress', 0) * 100)}%"
            if col == 5:
                return item.get("speed", "--")
            if col == 6:
                return item.get("eta", "--")
        return None

    def add_task(self, title: str, artist: str = "", cover_url: str = "", playlist: str = "", track_obj=None):
        self.beginInsertRows(QModelIndex(), len(self.items), len(self.items))
        self.items.append({
            "title": title,
            "artist": artist,
            "cover_url": cover_url,
            "playlist": playlist or "Single",
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
            idx2 = self.index(row, 6)
            self.dataChanged.emit(idx1, idx2)


class SearchResultModel(QAbstractTableModel):
    headers = ["Cover", "Titel", "Künstler / Kanal", "Dauer", "Typ", "Aktionen"]

    def __init__(self, rows: list[dict] | None = None):
        super().__init__()
        self.rows = rows or []

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
        if col == 0 and role == Qt.DecorationRole:
            return get_cover_pixmap(item.get("cover_url", ""), 48)
        if role == Qt.DecorationRole and col == 4:
            is_pl = "Playlist" in str(item.get("type", ""))
            return get_icon("playlist") if is_pl else get_icon("library")
        if role == Qt.DisplayRole:
            if col in (0, 5):
                return ""
            if col == 1:
                return item.get("title", "")
            if col == 2:
                return item.get("artist", "")
            if col == 3:
                d = item.get("duration", 0)
                return time_text(d) if d else "--:--"
            if col == 4:
                return str(item.get("type", "Song")).replace("🎵 ", "").replace("📋 ", "")
        if role == Qt.TextAlignmentRole and col == 3:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = list(rows)
        self.endResetModel()

    def append_rows(self, new_rows: list):
        if not new_rows:
            return
        start_row = len(self.rows)
        end_row = start_row + len(new_rows) - 1
        self.beginInsertRows(QModelIndex(), start_row, end_row)
        self.rows.extend(new_rows)
        self.endInsertRows()


class Signals(QObject):
    done = Signal(object)
    error = Signal(str)
    progress = Signal(int, float, str, str, str)
    status = Signal(int, str)
    sync_progress = Signal(int, int, str)
    cover_progress = Signal(int, int, str)


class SearchTask(QRunnable):
    def __init__(self, query: str, filter_type: str = "all", start: int = 1, limit: int = 30):
        super().__init__()
        self.query = query
        self.filter_type = filter_type
        self.start = start
        self.limit = limit
        self.signals = Signals()

    def run(self):
        try:
            import yt_dlp
            end = self.start + self.limit - 1
            options = {
                "quiet": True,
                "extract_flat": True,
                "skip_download": True,
                "no_warnings": True,
                "playliststart": self.start,
                "playlistend": end,
                "extractor_args": {"youtube": {"player_client": ["android", "ios", "mweb"]}},
            }
            if self.filter_type == "playlist":
                target = f"https://www.youtube.com/results?search_query={urllib.parse.quote(self.query)}&sp=EgIQAw%253D%253D"
            else:
                target = f"ytsearch{end}:{self.query}"

            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(target, download=False)

            raw_entries = info.get("entries", []) if isinstance(info, dict) else [info]
            results = []
            for e in raw_entries:
                if not e:
                    continue
                v_id = e.get("id", "")
                url = e.get("url") or e.get("webpage_url") or ""
                is_pl = (e.get("_type") == "playlist") or ("playlist" in url) or (self.filter_type == "playlist")
                if self.filter_type == "video" and is_pl:
                    continue
                if self.filter_type == "playlist" and not is_pl:
                    continue
                if not url.startswith("http"):
                    if is_pl:
                        url = f"https://www.youtube.com/playlist?list={v_id}"
                    else:
                        url = f"https://www.youtube.com/watch?v={v_id}"

                thumbs = e.get("thumbnails", [])
                thumb_url = thumbs[-1].get("url") if thumbs else (f"https://img.youtube.com/vi/{v_id}/hqdefault.jpg" if v_id else "")

                results.append({
                    "id": v_id,
                    "title": e.get("title") or "Unbekannter Titel",
                    "artist": e.get("uploader") or e.get("channel") or "Unbekannter Artist",
                    "duration": e.get("duration") or 0,
                    "url": url,
                    "cover_url": thumb_url,
                    "is_playlist": is_pl,
                    "type": "Playlist" if is_pl else "Song"
                })

            self.signals.done.emit(results)
        except Exception as exc:
            self.signals.error.emit(str(exc))


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
            from cover_enricher import CoverEnricher
            enricher = CoverEnricher()
            tracks = self.db.tracks()
            total = len(tracks)
            found = 0
            for i, t in enumerate(tracks, 1):
                self.signals.cover_progress.emit(i, total, t["title"])
                fp = Path(t["file_path"]) if t["file_path"] else None
                if fp and fp.is_file():
                    if enricher.enrich_file(fp, force=False):
                        found += 1
            self.signals.done.emit(found)
        except Exception as exc:
            self.signals.error.emit(str(exc))



class StreamUrlTask(QRunnable):
    def __init__(self, youtube_url: str):
        super().__init__()
        self.youtube_url = youtube_url
        self.signals = Signals()

    def run(self):
        try:
            from downloader import get_stream_url
            url = get_stream_url(self.youtube_url)
            try:
                self.signals.done.emit(url)
            except RuntimeError:
                pass
        except Exception as exc:
            try:
                self.signals.error.emit(str(exc))
            except RuntimeError:
                pass


class RecommendationsTask(QRunnable):
    def __init__(self, artist: str, title: str, source_url: str = ""):
        super().__init__()
        self.artist = artist
        self.title = title
        self.source_url = source_url
        self.signals = Signals()

    def run(self):
        try:
            from recommendations import fetch_recommendations
            items = fetch_recommendations(self.artist, self.title, self.source_url)
            # Pre-cache thumbnails in background thread so GUI doesn't freeze
            import hashlib, tempfile, urllib.request
            for rec in items[:15]:
                curl = rec.get("cover_url", "")
                if curl and curl.startswith(("http://", "https://")):
                    try:
                        h = hashlib.md5(curl.encode()).hexdigest()
                        cached = Path(tempfile.gettempdir()) / "mplayer_thumbs" / f"{h}.jpg"
                        if not cached.is_file() or cached.stat().st_size == 0:
                            cached.parent.mkdir(parents=True, exist_ok=True)
                            req = urllib.request.Request(curl, headers={"User-Agent": "Mozilla/5.0"})
                            with urllib.request.urlopen(req, timeout=1.5) as resp:
                                c_data = resp.read()
                            if c_data:
                                cached.write_bytes(c_data)
                    except Exception:
                        pass
            try:
                self.signals.done.emit(items)
            except RuntimeError:
                pass
        except Exception as exc:
            try:
                self.signals.error.emit(str(exc))
            except RuntimeError:
                pass


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


class DeleteTrackDialog(QDialog):
    """Two-tier song deletion dialog: Library only vs. Disk deletion."""
    def __init__(self, track_name: str, count: int = 1, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Song löschen" if count == 1 else "Songs löschen")
        self.setFixedWidth(440)
        self.choice: str | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        heading = QLabel(f"Wie möchtest du {f'„{track_name}“' if count == 1 else f'{count} ausgewählte Songs'} löschen?")
        heading.setStyleSheet("font-size: 15px; font-weight: 700; color: #F4F4F4;")
        heading.setWordWrap(True)
        layout.addWidget(heading)

        desc = QLabel(
            "• Nur aus Bibliothek entfernen: Behält die Datei auf deiner Festplatte.\n"
            "• Datei vom Datenträger löschen: Löscht die Datei(en) unwiderruflich von der Festplatte."
        )
        desc.setObjectName("secondary")
        desc.setStyleSheet("font-size: 13px; line-height: 1.4;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        btn_lib = QPushButton("Nur aus Bibliothek entfernen")
        btn_lib.setIcon(get_icon("library"))
        btn_lib.setIconSize(QSize(16, 16))
        btn_lib.setObjectName("secondary")
        btn_lib.clicked.connect(lambda: self._select("library"))
        layout.addWidget(btn_lib)

        btn_disk = QPushButton("Datei(en) vom Datenträger löschen")
        btn_disk.setIcon(get_icon("trash"))
        btn_disk.setIconSize(QSize(16, 16))
        btn_disk.setObjectName("danger")
        btn_disk.clicked.connect(lambda: self._select("disk"))
        layout.addWidget(btn_disk)

        cancel_row = QHBoxLayout()
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        cancel_row.addStretch()
        cancel_row.addWidget(cancel_btn)
        layout.addLayout(cancel_row)

    def _select(self, val: str):
        self.choice = val
        self.accept()


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

        # Load persisted settings
        self.settings = self.db.load_all_settings()
        self.settings["theme"] = "dark.qss"
        self.db.set_setting("theme", "dark.qss")
        self.music_root = Path(self.settings.get("music_folder", str(music_root)))
        self.is_shuffle = (self.settings.get("shuffle", "0") == "1")
        self.is_repeat = (self.settings.get("repeat", "0") == "1")
        saved_vol = float(self.settings.get("volume", "75")) / 100.0

        # Playback state
        self.current_idx = None
        self.active_rows = []
        self.current_track = None
        self.current_playlist_name = ""
        self.prev_volume = saved_vol if saved_vol > 0 else 0.75

        # Media Player
        self.player = QMediaPlayer()
        self.audio = QAudioOutput()
        self.player.setAudioOutput(self.audio)
        self.audio.setVolume(saved_vol)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_player_error)

        self._active_tasks = set()

        self.setWindowTitle("M-Player — Offline Music Manager")
        ico_file = ICON_DIR.parent / "icon.ico"
        if ico_file.exists():
            self.setWindowIcon(QIcon(str(ico_file)))
        self.setAcceptDrops(True)
        self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray_icon.show()
        self.resize(1360, 860)
        self.setMinimumSize(1040, 680)

        # Active library filter chip
        self.current_chip = "Alle"
        self._lib_grid_dirty = False
        self._fav_grid_dirty = False
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(220)
        self.search_timer.timeout.connect(self.refresh_library)

        self._build_ui()
        self.mini_player = MiniPlayerWindow(self)
        self._setup_shortcuts()

        # Startup cleanup if enabled
        if self.settings.get("cleanup_missing_startup", "0") == "1":
            self.db.sync_library(self.music_root)

        self.refresh_library()
        self.refresh_dashboard()
        self.refresh_playlists()
        self.update_queue_stats()

    def start_task(self, task):
        """Starts a QRunnable in the thread pool while retaining a strong Python ref to prevent premature GC crashes."""
        self._active_tasks.add(task)
        def _cleanup(*args):
            self._active_tasks.discard(task)
        if hasattr(task, "signals"):
            if hasattr(task.signals, "done"):
                task.signals.done.connect(_cleanup)
            if hasattr(task.signals, "error"):
                task.signals.error.connect(_cleanup)
        self.pool.start(task)

    def _on_player_error(self, error, error_string=""):
        try:
            if hasattr(self, "play_btn"):
                self.play_btn.setIcon(get_icon("play"))
        except Exception:
            pass

    def closeEvent(self, event):
        if hasattr(self, "mini_player"):
            self.mini_player.close()
        super().closeEvent(event)

    def _setup_shortcuts(self):
        QShortcut(QKeySequence(Qt.Key_Space), self, self._on_space_pressed)
        QShortcut(QKeySequence(Qt.Key_Left), self, lambda: self._seek_relative(-5000))
        QShortcut(QKeySequence(Qt.Key_Right), self, lambda: self._seek_relative(5000))
        QShortcut(QKeySequence(Qt.Key_Delete), self, self._on_delete_pressed)
        QShortcut(QKeySequence(Qt.Key_Return), self, self._on_enter_pressed)
        QShortcut(QKeySequence(Qt.Key_Enter), self, self._on_enter_pressed)
        QShortcut(QKeySequence("Ctrl+M"), self, self.toggle_mini_player)

    def toggle_mini_player(self):
        if not hasattr(self, "mini_player"):
            self.mini_player = MiniPlayerWindow(self)
        if self.mini_player.isVisible():
            self.mini_player.restore_main_window()
        else:
            self.mini_player.update_track(getattr(self, "current_track", None))
            self.mini_player.set_playing(self.player.playbackState() == QMediaPlayer.PlayingState)
            if self.player.duration() > 0:
                self.mini_player.update_position(self.player.position(), self.player.duration())
            self.mini_player.show()
            self.showMinimized()

    def clean_selected_tags(self, favorites: bool = False):
        model = self.fav_model if favorites else self.lib_model
        selected = model.selected()
        if not selected:
            QMessageBox.information(self, "Keine Auswahl", "Bitte markiere mindestens einen Song mit der Checkbox.")
            return
        cleaned = 0
        for t in selected:
            fp = t["file_path"] if hasattr(t, "keys") else getattr(t, "file_path", "")
            if fp and Path(fp).exists():
                clean_track_id3(Path(fp), self.db)
                cleaned += 1
        self.refresh_library()
        self.refresh_dashboard()
        self.notify("Tags bereinigt", f"{cleaned} Song(s) erfolgreich bereinigt.")

    def clean_single_track(self, track):
        if not track:
            return
        fp = track["file_path"] if hasattr(track, "keys") else getattr(track, "file_path", "")
        if fp and Path(fp).exists():
            clean_track_id3(Path(fp), self.db)
            self.refresh_library()
            self.refresh_dashboard()
            self.notify("Tags bereinigt", "Titel und Interpret wurden bereinigt.")

    def _on_space_pressed(self):
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit):
            return
        self.toggle_play()

    def _seek_relative(self, delta_ms: int):
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit):
            return
        new_pos = max(0, min(self.player.duration(), self.player.position() + delta_ms))
        self.player.setPosition(new_pos)

    def _on_enter_pressed(self):
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit):
            return
        if hasattr(self, "lib_table") and self.lib_table.hasFocus():
            idx = self.lib_table.currentIndex()
            if idx.isValid() and idx.row() < len(self.lib_model.rows):
                self.play(self.lib_model.rows[idx.row()], idx.row(), self.lib_model.rows)
        elif hasattr(self, "lib_grid") and self.lib_grid.hasFocus():
            item = self.lib_grid.currentItem()
            if item:
                self._on_grid_double_click(item, self.lib_model)
        elif hasattr(self, "fav_table") and self.fav_table.hasFocus():
            idx = self.fav_table.currentIndex()
            if idx.isValid() and idx.row() < len(self.fav_model.rows):
                self.play(self.fav_model.rows[idx.row()], idx.row(), self.fav_model.rows)
        elif hasattr(self, "fav_grid") and self.fav_grid.hasFocus():
            item = self.fav_grid.currentItem()
            if item:
                self._on_grid_double_click(item, self.fav_model)

    def _on_delete_pressed(self):
        focus = QApplication.focusWidget()
        if isinstance(focus, QLineEdit):
            return
        cur_page = self.pages.currentIndex() if hasattr(self, "pages") else 2
        if cur_page == 2:
            self.delete_selected_track(favorites=False)
        elif cur_page == 3:
            self.delete_selected_track(favorites=True)

    def _button(self, text, slot, accent=False, obj_name="", icon: QIcon | None = None, icon_size: QSize | None = None):
        btn = QPushButton(text)
        if icon is not None and not icon.isNull():
            btn.setIcon(icon)
            btn.setIconSize(icon_size or QSize(16, 16))
        btn.clicked.connect(slot)
        if accent:
            btn.setObjectName("accent")
        elif obj_name:
            btn.setObjectName(obj_name)
        return btn

    def notify(self, title: str, body: str):
        try:
            import win11toast
            win11toast.toast(title, body)
            return
        except Exception:
            pass
        if hasattr(self, "tray_icon") and self.tray_icon:
            self.tray_icon.showMessage(title, body, QSystemTrayIcon.Information, 4000)

    def _show_in_explorer(self, file_path: Path):
        if not file_path.exists():
            QMessageBox.warning(self, "Datei fehlt", f"Die Datei '{file_path.name}' wurde nicht gefunden.")
            return
        if sys.platform == "win32":
            subprocess.run(["explorer", f"/select,{file_path}"], check=False)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(file_path.parent)))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [Path(u.toLocalFile()) for u in urls if u.toLocalFile()]
        if paths:
            event.acceptProposedAction()
            self.import_dropped_files(paths)

    def import_dropped_files(self, paths: list[Path]) -> int:
        audio_exts = {".mp3", ".flac", ".m4a", ".wav"}
        files_to_import: list[Path] = []
        for p in paths:
            if p.is_dir():
                for f in p.rglob("*"):
                    if f.is_file() and f.suffix.lower() in audio_exts:
                        files_to_import.append(f)
            elif p.is_file() and p.suffix.lower() in audio_exts:
                files_to_import.append(p)

        if not files_to_import:
            return 0

        count = 0
        for fp in files_to_import:
            track = read_audio_tags(fp)
            self.db.upsert(track, fp, duration=track.duration, bitrate=track.bitrate)
            if track.collection and track.collection not in ("Einzeltitel", "Single", self.music_root.name, ".covers"):
                t_rows = [t for t in self.db.tracks() if t["file_path"] == str(fp)]
                if t_rows:
                    self.db.add_to_playlist(track.collection, t_rows[0]["id"])
            count += 1

        self.refresh_library()
        self.refresh_dashboard()
        self.notify("Import abgeschlossen", f"{count} Song(s) erfolgreich zur Bibliothek hinzugefügt.")
        return count

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("centralWidget")
        self.setCentralWidget(root)
        main_layout = QVBoxLayout(root)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(10)

        # 1. Top Bar: App Title with Logo + Global Refresh + Settings
        header = QHBoxLayout()
        header.setSpacing(10)

        self.logo_lbl = QLabel()
        self.logo_lbl.setFixedSize(28, 28)
        logo_path = ICON_DIR.parent / "logo.svg"
        if logo_path.exists():
            self.logo_lbl.setPixmap(QIcon(str(logo_path)).pixmap(28, 28))
        header.addWidget(self.logo_lbl)

        title_lbl = QLabel("M-Player")
        title_lbl.setStyleSheet("font-size: 22px; font-weight: 700; color: #F4F4F4;")
        header.addWidget(title_lbl)
        header.addStretch()

        self.top_refresh_btn = self._button("Bibliothek aktualisieren", self.run_sync_library, True, icon=get_icon("refresh"), icon_size=QSize(16, 16))
        self.top_refresh_btn.setShortcut("F5")
        self.top_refresh_btn.setToolTip("Musikordner vollständig scannen & synchronisieren (F5)")
        header.addWidget(self.top_refresh_btn)

        # Global F5 shortcut
        self.f5_shortcut = QShortcut(QKeySequence("F5"), self)
        self.f5_shortcut.activated.connect(self.run_sync_library)

        header.addWidget(self._button("Einstellungen", lambda: self.show_page(6), icon=get_icon("settings"), icon_size=QSize(16, 16)))
        main_layout.addLayout(header)

        # 2. Main Area: Sidebar + Content Area + Collapsible Details Panel
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
        self.nav.setSpacing(0)
        self.nav.setIconSize(QSize(20, 20))
        self.nav.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.nav.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        nav_items = [
            ("Downloader", "downloader", 0),
            ("Entdecken", "compass", 1),
            ("Bibliothek", "library", 2),
            ("Favoriten", "heart", 3),
            ("Playlists", "playlist", 4),
            ("Downloads", "download", 5),
        ]
        for title, icon_name, _ in nav_items:
            item = QListWidgetItem(get_icon(icon_name), f"  {title}")
            item.setSizeHint(QSize(200, 48))
            self.nav.addItem(item)
        self.nav.currentRowChanged.connect(self.show_page)

        # Ensure all nav items fit without scrolling (replaces QAbstractScrollArea default 192px limit)
        nav_h = sum(self.nav.sizeHintForRow(i) for i in range(self.nav.count())) + (self.nav.count() * 6) + 16
        self.nav.setFixedHeight(nav_h)
        sidebar_layout.addWidget(self.nav, 0)
        sidebar_layout.addStretch(1)

        # Now Playing Mini-Card / Stats Fallback Widget
        self.sidebar_mini_card = self._build_sidebar_mini_card()
        sidebar_layout.addWidget(self.sidebar_mini_card)

        try:
            from main import __version__
        except ImportError:
            __version__ = "v1.0.0"

        self.version_lbl = QLabel(__version__)
        self.version_lbl.setStyleSheet("color: #6a7282; font-size: 11px; padding-top: 4px;")
        self.version_lbl.setAlignment(Qt.AlignCenter)
        sidebar_layout.addWidget(self.version_lbl)

        body.addWidget(sidebar_frame)

        # Right Content Area
        content_box = QVBoxLayout()
        content_box.setSpacing(10)

        # Stacked Pages
        self.pages = QStackedWidget()
        self.pages.addWidget(self._downloader_page())   # 0: Link-Import
        self.pages.addWidget(self._discover_page())     # 1: YouTube-Suche / Entdecken
        self.pages.addWidget(self._library_page(False))  # 2: Bibliothek
        self.pages.addWidget(self._library_page(True))   # 3: Favoriten
        self.pages.addWidget(self._playlists_page())     # 4: Playlists
        self.pages.addWidget(self._queue_page())         # 5: Downloads
        self.pages.addWidget(self._settings_page())      # 6: Einstellungen
        content_box.addWidget(self.pages, 1)

        body.addLayout(content_box, 1)

        # Collapsible Right Details Panel (Priority 7)
        self.details_panel = self._build_details_panel()
        body.addWidget(self.details_panel)
        self.details_panel.hide()

        main_layout.addLayout(body, 1)

        # Bottom Mini Player
        main_layout.addWidget(self._player_bar())
        self.nav.setCurrentRow(2)

    def refresh_dashboard(self):
        stats = self.db.dashboard_stats(self.music_root)
        dur_min = int(stats["duration"] // 60)
        dur_hrs = dur_min // 60
        dur_text = f"{dur_hrs}h {dur_min % 60}m" if dur_hrs > 0 else f"{dur_min}m"
        size_text = format_size(stats["size_bytes"])
        text = f"{stats['songs']} Songs  ·  {stats['albums']} Alben  ·  {stats['playlists']} Playlists  ·  {size_text}  ·  {dur_text}"
        if hasattr(self, "lib_stats_lbl"):
            self.lib_stats_lbl.setText(text)
        if hasattr(self, "fav_stats_lbl"):
            fav_count = len(self.fav_model.rows) if hasattr(self, "fav_model") else 0
            self.fav_stats_lbl.setText(f"{fav_count} Favoriten")
        self._update_sidebar_mini_card(getattr(self, "current_track", None))

    def _build_sidebar_mini_card(self) -> QWidget:
        card = QFrame()
        card.setObjectName("sidebarMiniCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(8, 8, 8, 8)
        card_layout.setSpacing(6)

        # 1. Track Active Widget
        self.sb_track_box = QWidget()
        tb_layout = QHBoxLayout(self.sb_track_box)
        tb_layout.setContentsMargins(0, 0, 0, 0)
        tb_layout.setSpacing(8)

        self.sb_cover = QLabel()
        self.sb_cover.setFixedSize(48, 48)
        self.sb_cover.setPixmap(get_cover_pixmap("", 48))
        self.sb_cover.setScaledContents(True)

        meta_layout = QVBoxLayout()
        meta_layout.setContentsMargins(0, 0, 0, 0)
        meta_layout.setSpacing(2)
        meta_layout.setAlignment(Qt.AlignVCenter)

        self.sb_title = QLabel("Kein Song")
        self.sb_title.setStyleSheet("font-weight: 700; font-size: 12px;")
        self.sb_title.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        self.sb_artist = QLabel("Bereit")
        self.sb_artist.setObjectName("secondary")
        self.sb_artist.setStyleSheet("font-size: 11px;")
        self.sb_artist.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

        meta_layout.addWidget(self.sb_title)
        meta_layout.addWidget(self.sb_artist)

        self.sb_fav_btn = self._button("", self._toggle_current_fav, obj_name="playerBtn", icon=get_icon("heart"), icon_size=QSize(16, 16))
        self.sb_fav_btn.setFixedSize(28, 28)
        self.sb_fav_btn.setToolTip("Zu Favoriten hinzufügen")

        tb_layout.addWidget(self.sb_cover)
        tb_layout.addLayout(meta_layout, 1)
        tb_layout.addWidget(self.sb_fav_btn)

        # 2. Idle Fallback Stats Widget
        self.sb_stats_box = QWidget()
        sb_layout = QHBoxLayout(self.sb_stats_box)
        sb_layout.setContentsMargins(4, 4, 4, 4)
        sb_layout.setSpacing(8)

        stats_icon = QLabel()
        stats_icon.setPixmap(get_icon("library").pixmap(24, 24))
        stats_icon.setFixedSize(24, 24)

        stats_info = QVBoxLayout()
        stats_info.setContentsMargins(0, 0, 0, 0)
        stats_info.setSpacing(1)
        stats_info.setAlignment(Qt.AlignVCenter)

        self.sb_stats_title = QLabel("Bibliothek")
        self.sb_stats_title.setStyleSheet("font-weight: 600; font-size: 11px;")
        self.sb_stats_desc = QLabel("0 Songs · 0 Alben")
        self.sb_stats_desc.setObjectName("secondary")
        self.sb_stats_desc.setStyleSheet("font-size: 10px;")

        stats_info.addWidget(self.sb_stats_title)
        stats_info.addWidget(self.sb_stats_desc)

        sb_layout.addWidget(stats_icon)
        sb_layout.addLayout(stats_info, 1)

        card_layout.addWidget(self.sb_track_box)
        card_layout.addWidget(self.sb_stats_box)

        card.mousePressEvent = self._on_sidebar_mini_card_clicked

        self._update_sidebar_mini_card(None)
        return card

    def _on_sidebar_mini_card_clicked(self, event):
        if getattr(self, "current_track", None):
            self.show_track_details(self.current_track)
        else:
            self.show_page(2)

    def _update_sidebar_mini_card(self, track=None):
        if not hasattr(self, "sb_track_box") or not hasattr(self, "sb_stats_box"):
            return
        if track:
            self.sb_stats_box.hide()
            self.sb_track_box.show()
            t_title = track["title"] if hasattr(track, "keys") else (track.get("title", "") if isinstance(track, dict) else getattr(track, "title", ""))
            t_artist = track["artist"] if hasattr(track, "keys") else (track.get("artist", "") if isinstance(track, dict) else getattr(track, "artist", ""))
            f_path = track["file_path"] if hasattr(track, "keys") else (track.get("file_path", "") if isinstance(track, dict) else getattr(track, "file_path", ""))
            fav = track["favorite"] if hasattr(track, "keys") and "favorite" in track.keys() else (track.get("favorite", 0) if isinstance(track, dict) else getattr(track, "favorite", 0))

            if not t_title and f_path:
                t_title = Path(f_path).stem
            if not t_artist:
                t_artist = "Unbekannter Interpret"

            self.sb_title.setText(t_title or "Unbekannter Titel")
            self.sb_artist.setText(t_artist)
            self.sb_cover.setPixmap(get_cover_pixmap(f_path, 48))
            self.sb_fav_btn.setIcon(get_icon("heart-filled" if fav else "heart"))
        else:
            self.sb_track_box.hide()
            self.sb_stats_box.show()
            try:
                st = self.db.stats()
                songs = st["songs"] if st else 0
                albums = st["albums"] if st else 0
                self.sb_stats_desc.setText(f"{songs} Songs · {albums} Alben")
            except Exception:
                self.sb_stats_desc.setText("Bereit")

    def _build_details_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("detailsPanel")
        panel.setFixedWidth(290)
        
        main_layout = QVBoxLayout(panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: #171A1F;")
        
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Top Header (Shrinked)
        hdr = QHBoxLayout()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(24, 24)
        close_btn.setObjectName("closeBtn")
        close_btn.clicked.connect(lambda: self.details_panel.hide())
        hdr.addStretch()
        hdr.addWidget(close_btn)
        layout.addLayout(hdr)

        # Large Cover
        cover_container = QHBoxLayout()
        self.detail_cover = QLabel()
        self.detail_cover.setFixedSize(140, 140)
        self.detail_cover.setPixmap(get_cover_pixmap("", 140))
        self.detail_cover.setAlignment(Qt.AlignCenter)
        cover_container.setAlignment(Qt.AlignCenter)
        cover_container.addWidget(self.detail_cover)
        layout.addLayout(cover_container)

        # Title & Artist
        self.detail_title = QLabel("Kein Song ausgewählt")
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet("font-size: 14px; font-weight: 700; color: #F4F4F4;")
        self.detail_artist = QLabel("")
        self.detail_artist.setWordWrap(True)
        self.detail_artist.setStyleSheet("font-size: 13px; font-weight: 600; color: #3DDC63;")
        layout.addWidget(self.detail_title)
        layout.addWidget(self.detail_artist)

        # Badges row: Album / Playlist
        self.detail_album_badge = QLabel("")
        self.detail_album_badge.setObjectName("metaBadge")
        self.detail_album_badge.setWordWrap(True)
        layout.addWidget(self.detail_album_badge)

        # Tab switcher: Info vs Ähnliche Songs
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(0, 4, 0, 4)
        tab_row.setSpacing(4)
        self.detail_tab_info = QPushButton("Info")
        self.detail_tab_info.setObjectName("chipBtn")
        self.detail_tab_info.setProperty("active", "true")
        self.detail_tab_similar = QPushButton("Ähnlich")
        self.detail_tab_similar.setObjectName("chipBtn")
        self.detail_tab_similar.setProperty("active", "false")
        self.detail_tab_similar.setToolTip("Ähnliche Songs & Empfehlungen")

        self.detail_tab_info.clicked.connect(lambda: self._switch_detail_tab(0))
        self.detail_tab_similar.clicked.connect(lambda: self._switch_detail_tab(1))

        tab_row.addWidget(self.detail_tab_info)
        tab_row.addWidget(self.detail_tab_similar)
        layout.addLayout(tab_row)

        self.detail_stack = QStackedWidget()

        # Page 0: Info page
        info_page = QWidget()
        info_layout = QVBoxLayout(info_page)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(8)

        # Metadata box
        meta_frame = QFrame()
        meta_frame.setObjectName("metaBox")
        meta_layout = QVBoxLayout(meta_frame)
        meta_layout.setContentsMargins(10, 10, 10, 10)
        meta_layout.setSpacing(6)

        self.detail_duration = QLabel("Dauer: --:--")
        self.detail_size = QLabel("Größe: --")
        self.detail_bitrate = QLabel("Qualität: 320 kbps")
        self.detail_year = QLabel("Jahr: --")
        self.detail_genre = QLabel("Genre: --")
        self.detail_plays = QLabel("Gespielt: 0 mal")

        for lbl in (self.detail_duration, self.detail_size, self.detail_bitrate, self.detail_year, self.detail_genre, self.detail_plays):
            lbl.setObjectName("secondary")
            lbl.setStyleSheet("font-size: 12px;")
            meta_layout.addWidget(lbl)

        info_layout.addWidget(meta_frame)

        # Action buttons
        self.detail_play_btn = self._button("Abspielen", self._on_detail_play, True, icon=get_icon("play"), icon_size=QSize(16, 16))
        self.detail_fav_btn = self._button("Zu Favoriten", self._on_detail_fav, icon=get_icon("heart"), icon_size=QSize(16, 16))
        self.detail_clean_btn = self._button("Tags bereinigen", self._on_detail_clean, icon=get_icon("zap"), icon_size=QSize(16, 16))
        self.detail_clean_btn.setToolTip("Auto-Clean ID3 Tags (YouTube-Müll entfernen, Artist/Titel trennen)")
        self.detail_cover_btn = self._button("Cover aktualisieren", self._on_detail_update_cover, icon=get_icon("covers"), icon_size=QSize(16, 16))
        self.detail_folder_btn = self._button("Im Explorer anzeigen", self._on_detail_open_folder, icon=get_icon("folder"), icon_size=QSize(16, 16))
        self.detail_del_btn = self._button("Löschen", self._on_detail_delete, obj_name="danger", icon=get_icon("trash"), icon_size=QSize(16, 16))

        for btn in (self.detail_play_btn, self.detail_fav_btn, self.detail_clean_btn, self.detail_cover_btn, self.detail_folder_btn, self.detail_del_btn):
            info_layout.addWidget(btn)

        self.detail_stack.addWidget(info_page)

        # Page 1: Recommendations / Similar songs page
        similar_page = QWidget()
        similar_layout = QVBoxLayout(similar_page)
        similar_layout.setContentsMargins(0, 0, 0, 0)
        similar_layout.setSpacing(6)

        self.similar_status_lbl = QLabel("Keine Empfehlungen geladen")
        self.similar_status_lbl.setObjectName("secondary")
        self.similar_status_lbl.setStyleSheet("font-size: 11px; padding: 2px;")
        similar_layout.addWidget(self.similar_status_lbl)

        self.similar_list = QListWidget()
        self.similar_list.setObjectName("similarList")
        self.similar_list.setFocusPolicy(Qt.NoFocus)
        self.similar_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        similar_layout.addWidget(self.similar_list, 1)

        self.detail_stack.addWidget(similar_page)
        layout.addWidget(self.detail_stack, 1)

        self.selected_detail_track = None
        self._last_rec_key = ""
        
        scroll.setWidget(content)
        main_layout.addWidget(scroll)
        
        return panel

    def show_track_details(self, track):
        if not track:
            return
        self.selected_detail_track = track
        t_dict = dict(track) if hasattr(track, "keys") else track.__dict__

        title = t_dict.get("title", "Unbekannter Titel")
        artist = t_dict.get("artist", "Unbekannter Künstler")
        album = t_dict.get("album", "")
        coll = t_dict.get("collection", "")
        fp = t_dict.get("file_path", "")
        dur = t_dict.get("duration", 0)
        bitrate = t_dict.get("bitrate", 320)
        year = t_dict.get("year", "")
        genre = t_dict.get("genre", "")
        plays = t_dict.get("play_count", 0)
        fav = t_dict.get("favorite", 0)

        self.detail_title.setText(title)
        self.detail_artist.setText(artist)
        badge_text = album if album else (coll if coll else "")
        self.detail_album_badge.setText(badge_text)
        self.detail_album_badge.setVisible(bool(badge_text))

        self.detail_duration.setText(f"Dauer: {time_text(dur)}")

        file_size = 0
        if fp and Path(fp).is_file():
            try:
                file_size = Path(fp).stat().st_size
            except OSError:
                file_size = 0
        self.detail_size.setText(f"Größe: {format_size(file_size)}")
        self.detail_bitrate.setText(f"Qualität: {bitrate} kbps" if bitrate else "Qualität: 320 kbps")
        self.detail_year.setText(f"Jahr: {year}" if year else "Jahr: --")
        self.detail_genre.setText(f"Genre: {genre}" if genre else "Genre: --")
        self.detail_plays.setText(f"Gespielt: {plays} mal")

        self.detail_cover.setPixmap(get_cover_pixmap(fp, 140))
        self.detail_fav_btn.setText("Aus Favoriten" if fav else "Zu Favoriten")
        self.detail_fav_btn.setIcon(get_icon("heart-filled" if fav else "heart"))
        self.details_panel.show()
        if hasattr(self, "detail_stack") and self.detail_stack.currentIndex() == 1:
            self._load_recommendations_for_track(track)

    def _switch_detail_tab(self, idx: int):
        self.detail_stack.setCurrentIndex(idx)
        self.detail_tab_info.setProperty("active", "true" if idx == 0 else "false")
        self.detail_tab_similar.setProperty("active", "true" if idx == 1 else "false")
        self.detail_tab_info.style().unpolish(self.detail_tab_info)
        self.detail_tab_info.style().polish(self.detail_tab_info)
        self.detail_tab_similar.style().unpolish(self.detail_tab_similar)
        self.detail_tab_similar.style().polish(self.detail_tab_similar)
        target = getattr(self, "current_track", None) or getattr(self, "selected_detail_track", None)
        if idx == 1 and (not hasattr(self, "similar_list") or self.similar_list.count() == 0) and target:
            self._load_recommendations_for_track(target)

    def _on_detail_clean(self):
        if not self.selected_detail_track:
            return
        self.clean_single_track(self.selected_detail_track)
        fp = self.selected_detail_track["file_path"] if hasattr(self.selected_detail_track, "keys") else getattr(self.selected_detail_track, "file_path", "")
        updated = [t for t in self.db.tracks() if t["file_path"] == fp]
        if updated:
            self.show_track_details(updated[0])

    def _load_recommendations_for_track(self, track):
        if not track or not hasattr(self, "similar_list"):
            return
        t_title = track["title"] if hasattr(track, "keys") else (track.get("title", "") if isinstance(track, dict) else getattr(track, "title", ""))
        t_artist = track["artist"] if hasattr(track, "keys") else (track.get("artist", "") if isinstance(track, dict) else getattr(track, "artist", ""))
        src_url = track["source_url"] if (hasattr(track, "keys") and "source_url" in track.keys()) else (track.get("source_url", "") if isinstance(track, dict) else getattr(track, "source_url", ""))
        f_path = track["file_path"] if hasattr(track, "keys") else (track.get("file_path", "") if isinstance(track, dict) else getattr(track, "file_path", ""))

        if not t_title and f_path:
            t_title = Path(f_path).stem

        if not t_title:
            return

        t_key = f"{t_artist} - {t_title}"
        if getattr(self, "_last_rec_key", "") == t_key and self.similar_list.count() > 0:
            return
        self._last_rec_key = t_key

        self.similar_status_lbl.setText(f"Lade Empfehlungen für „{t_title}“ …")

        task = RecommendationsTask(t_artist or "", t_title or "", src_url or "")

        def on_recs_done(items):
            if getattr(self, "_last_rec_key", "") != t_key:
                return
            self._populate_recommendations(items)

        def on_recs_err(_):
            if hasattr(self, "similar_status_lbl"):
                self.similar_status_lbl.setText("Keine Empfehlungen gefunden.")

        task.signals.done.connect(on_recs_done)
        task.signals.error.connect(on_recs_err)
        self.start_task(task)

    def _populate_recommendations(self, items: list[dict]):
        if not hasattr(self, "similar_list"):
            return
        self.similar_list.clear()
        if not items:
            self.similar_status_lbl.setText("Keine Empfehlungen gefunden.")
            return

        self.similar_status_lbl.setText(f"{len(items)} ähnliche Songs gefunden:")
        for rec in items:
            item = QListWidgetItem(self.similar_list)
            item.setSizeHint(QSize(250, 48))

            row_w = QWidget()
            r_lay = QHBoxLayout(row_w)
            r_lay.setContentsMargins(4, 2, 4, 2)
            r_lay.setSpacing(6)

            cov_lbl = QLabel()
            cov_lbl.setFixedSize(36, 36)
            cov_lbl.setScaledContents(True)
            cov_lbl.setPixmap(get_cover_pixmap(rec.get("cover_url", ""), 36))
            r_lay.addWidget(cov_lbl)

            text_col = QVBoxLayout()
            text_col.setContentsMargins(0, 0, 0, 0)
            text_col.setSpacing(2)

            t_lbl = QLabel(rec.get("title", ""))
            t_lbl.setStyleSheet("font-size: 11px; font-weight: 600; color: #F4F4F4;")
            fm = QFontMetrics(t_lbl.font())
            t_lbl.setText(fm.elidedText(rec.get("title", ""), Qt.ElideRight, 130))

            a_lbl = QLabel(rec.get("artist", ""))
            a_lbl.setObjectName("secondary")
            a_lbl.setStyleSheet("font-size: 10px; color: #A0A6AD;")
            fm_a = QFontMetrics(a_lbl.font())
            a_lbl.setText(fm_a.elidedText(rec.get("artist", ""), Qt.ElideRight, 130))

            text_col.addWidget(t_lbl)
            text_col.addWidget(a_lbl)
            r_lay.addLayout(text_col, 1)

            btn_play = QPushButton()
            btn_play.setIcon(get_icon("play"))
            btn_play.setFixedSize(26, 26)
            btn_play.setObjectName("toolbarBtn")
            btn_play.setToolTip("Vorhören (Direct Stream)")
            btn_play.clicked.connect(lambda _, r=rec: self.preview_stream(r))

            btn_dl = QPushButton()
            btn_dl.setIcon(get_icon("download"))
            btn_dl.setFixedSize(26, 26)
            btn_dl.setObjectName("toolbarBtn")
            btn_dl.setToolTip("In Bibliothek laden")
            btn_dl.clicked.connect(lambda _, r=rec: self._handle_search_hit(r))

            r_lay.addWidget(btn_play)
            r_lay.addWidget(btn_dl)
            self.similar_list.setItemWidget(item, row_w)

    def preview_stream(self, res: dict):
        if not res or not res.get("url"):
            return

        t_title = res.get("title", "Unbekannter Titel")
        t_artist = res.get("artist", "Unbekannter Künstler")
        cover_url = res.get("cover_url", "")

        self.now_title.setText(f"⚡ [Lade Stream …] {t_title}")
        self.now_artist.setText(t_artist)
        self.bar_cover.setPixmap(get_cover_pixmap(cover_url, 56))
        self.now_audio_info.setText("Verbinde …")
        self.now_audio_info.show()

        virtual_track = {
            "id": None,
            "title": t_title,
            "artist": t_artist,
            "cover_url": cover_url,
            "file_path": "",
            "source_url": res.get("url", ""),
            "duration": res.get("duration", 0),
            "is_stream": True,
        }
        self.current_track = virtual_track

        if hasattr(self, "mini_player"):
            self.mini_player.update_track(virtual_track)

        task = StreamUrlTask(res["url"])

        def on_stream_ready(stream_url):
            if not stream_url:
                self.notify("Stream-Fehler", "Direkt-Stream konnte nicht abgerufen werden.")
                self.now_title.setText(t_title)
                self.now_audio_info.setText("Fehler")
                return

            if getattr(self, "current_track", None) is not virtual_track:
                return

            self.player.setSource(QUrl(stream_url))
            self.player.play()
            self.play_btn.setIcon(get_icon("pause"))
            if hasattr(self, "mini_player"):
                self.mini_player.set_playing(True)

            self.now_title.setText(f"⚡ [Vorhören] {t_title}")
            self.now_audio_info.setText("Direct Stream")
            self._update_sidebar_mini_card(virtual_track)
            self._load_recommendations_for_track(virtual_track)

        def on_stream_err(err):
            self.notify("Stream-Fehler", f"Stream-Fehler: {err}")
            self.now_title.setText(t_title)
            self.now_audio_info.setText("Fehler")

        task.signals.done.connect(on_stream_ready)
        task.signals.error.connect(on_stream_err)
        self.start_task(task)

    def _on_detail_play(self):
        if self.selected_detail_track:
            self.play(self.selected_detail_track)

    def _on_detail_fav(self):
        if not self.selected_detail_track:
            return
        t_id = self.selected_detail_track["id"] if hasattr(self.selected_detail_track, "keys") else getattr(self.selected_detail_track, "id", None)
        if t_id:
            self.db.toggle_favorite(t_id)
            updated = [t for t in self.db.tracks() if t["id"] == t_id]
            if updated:
                self.show_track_details(updated[0])
            self.refresh_library()
            self.refresh_dashboard()

    def _on_detail_open_folder(self):
        if not self.selected_detail_track:
            return
        fp = self.selected_detail_track["file_path"] if hasattr(self.selected_detail_track, "keys") else getattr(self.selected_detail_track, "file_path", "")
        if fp and Path(fp).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(fp).parent)))

    def _on_detail_update_cover(self):
        if self.selected_detail_track:
            self._refresh_single_cover(self.selected_detail_track)

    def _on_detail_delete(self):
        if self.selected_detail_track:
            self._prompt_delete_track(self.selected_detail_track)

    def _downloader_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # Header Title & Subtitle
        header_box = QVBoxLayout()
        header_box.setSpacing(3)
        header_title = QLabel("Playlist & Song Import")
        header_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #F4F4F4;")
        header_sub = QLabel("Unterstützt YouTube, YouTube Music und Spotify Playlists oder Einzellinks")
        header_sub.setObjectName("secondary")
        header_box.addWidget(header_title)
        header_box.addWidget(header_sub)
        layout.addLayout(header_box)

        # Input Row: URL Field + Analysieren Button directly adjacent
        input_row = QHBoxLayout()
        input_row.setSpacing(10)
        self.links = QLineEdit()
        self.links.setPlaceholderText("Link hier einfügen (z. B. https://music.youtube.com/playlist?list=...) …")
        self.links.returnPressed.connect(self.analyze)
        self.analyze_btn = self._button("Analysieren", self.analyze, True, icon=get_icon("search"))
        self.analyze_btn.setFixedWidth(140)
        self.to_discover_btn = self._button("Zur YouTube-Suche", lambda: self.nav.setCurrentRow(1), icon=get_icon("compass"))
        self.to_discover_btn.setToolTip("Direkt in YouTube suchen ohne Browser")
        input_row.addWidget(self.links, 1)
        input_row.addWidget(self.analyze_btn)
        input_row.addWidget(self.to_discover_btn)
        layout.addLayout(input_row)

        # Actions & Filter Bar
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.toggle_all_btn = self._button("Alle an / ab", self._toggle_all_preview, icon=get_icon("check-square"))
        self.only_new_btn = self._button("Nur neue Songs", self.only_new, icon=get_icon("zap"))
        action_row.addWidget(self.toggle_all_btn)
        action_row.addWidget(self.only_new_btn)
        action_row.addStretch()

        self.pre_status = QLabel("Bereit für Link-Analyse.")
        self.pre_status.setObjectName("secondary")
        action_row.addWidget(self.pre_status)

        self.start_btn = self._button("Download starten", self.start_download, True, icon=get_icon("download"))
        self.start_btn.setFixedWidth(180)
        action_row.addWidget(self.start_btn)
        layout.addLayout(action_row)

        # Preview Table (clean: hide non-relevant columns before download)
        self.pre_model = TrackModel(selectable=True)
        self.pre_table = self._create_styled_table(self.pre_model)
        self.pre_table.setColumnHidden(4, True)  # Album
        self.pre_table.setColumnHidden(5, True)  # Dauer
        self.pre_table.setColumnHidden(6, True)  # Jahr
        self.pre_table.setColumnHidden(7, True)  # Qualität
        layout.addWidget(self.pre_table, 1)

        return page

    def _toggle_all_preview(self):
        all_checked = len(self.pre_model.checked) == len(self.pre_model.rows) and len(self.pre_model.rows) > 0
        self.set_checked(not all_checked)

    def _discover_page(self) -> QWidget:
        page = QFrame()
        page.setObjectName("card")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(14)

        # Header Title & Subtitle
        header_box = QVBoxLayout()
        header_box.setSpacing(3)
        header_title = QLabel("Musik entdecken & direkt suchen")
        header_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #F4F4F4;")
        header_sub = QLabel("Finde Songs, Alben, Playlists oder Künstler direkt auf YouTube – ohne Browser.")
        header_sub.setObjectName("secondary")
        header_box.addWidget(header_title)
        header_box.addWidget(header_sub)
        layout.addLayout(header_box)

        # Search Input + Button Row
        search_row = QHBoxLayout()
        search_row.setSpacing(10)
        self.discover_input = QLineEdit()
        self.discover_input.setPlaceholderText("Suchbegriff eingeben (z. B. The Weeknd, Hans Zimmer, Lofi Beats Playlist) …")
        self.discover_input.returnPressed.connect(self.run_youtube_search)
        self.discover_btn = self._button("Suchen", self.run_youtube_search, True, icon=get_icon("search"))
        self.discover_btn.setFixedWidth(140)
        search_row.addWidget(self.discover_input, 1)
        search_row.addWidget(self.discover_btn)
        layout.addLayout(search_row)

        # Filter Pills Bar (Alle / Songs / Playlists)
        filter_row = QHBoxLayout()
        filter_row.setSpacing(8)
        self.discover_filter = "all"

        self.disc_filter_all = QPushButton("Alle")
        self.disc_filter_songs = QPushButton("Songs")
        self.disc_filter_songs.setIcon(get_icon("library"))
        self.disc_filter_songs.setIconSize(QSize(14, 14))
        self.disc_filter_playlists = QPushButton("Playlists")
        self.disc_filter_playlists.setIcon(get_icon("playlist"))
        self.disc_filter_playlists.setIconSize(QSize(14, 14))

        self.disc_filter_buttons = {
            "all": self.disc_filter_all,
            "video": self.disc_filter_songs,
            "playlist": self.disc_filter_playlists,
        }

        for f_key, b in self.disc_filter_buttons.items():
            b.setObjectName("chipBtn")
            b.setProperty("active", "true" if f_key == "all" else "false")
            b.clicked.connect(lambda _, k=f_key: self._set_discover_filter(k))
            filter_row.addWidget(b)

        filter_row.addStretch()

        self.discover_status = QLabel("Bereit zum Suchen.")
        self.discover_status.setObjectName("secondary")
        filter_row.addWidget(self.discover_status)

        self.disc_preview_btn = self._button("Vorhören", self._preview_selected_search_result, icon=get_icon("play"))
        self.disc_preview_btn.setToolTip("Ausgewählten Song vorhören (Direct Stream)")
        filter_row.addWidget(self.disc_preview_btn)

        self.disc_action_btn = self._button("Laden", self._download_selected_search_result, True, icon=get_icon("download"))
        self.disc_action_btn.setToolTip("Ausgewählten Treffer herunterladen")
        filter_row.addWidget(self.disc_action_btn)
        layout.addLayout(filter_row)

        # Results Table
        self.discover_model = SearchResultModel()
        self.discover_table = QTableView()
        self.discover_table.setModel(self.discover_model)
        self.discover_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.discover_table.verticalHeader().setDefaultSectionSize(60)
        self.discover_table.verticalHeader().setVisible(False)

        h = self.discover_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.Fixed)
        self.discover_table.setColumnWidth(0, 56)
        h.setSectionResizeMode(1, QHeaderView.Stretch)
        h.setSectionResizeMode(2, QHeaderView.Interactive)
        self.discover_table.setColumnWidth(2, 160)
        h.setSectionResizeMode(3, QHeaderView.Fixed)
        self.discover_table.setColumnWidth(3, 65)
        h.setSectionResizeMode(4, QHeaderView.Fixed)
        self.discover_table.setColumnWidth(4, 75)
        h.setSectionResizeMode(5, QHeaderView.Fixed)
        self.discover_table.setColumnWidth(5, 150)

        self.discover_table.doubleClicked.connect(self._on_search_result_double_clicked)
        self.discover_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.discover_table.customContextMenuRequested.connect(self._search_context_menu)
        self.discover_table.verticalScrollBar().valueChanged.connect(self._on_search_scroll)

        layout.addWidget(self.discover_table, 1)
        return page

    def _attach_discover_action_buttons(self, start_idx: int = 0):
        for row in range(start_idx, len(self.discover_model.rows)):
            res = self.discover_model.rows[row]
            w = QWidget()
            w_layout = QHBoxLayout(w)
            w_layout.setContentsMargins(2, 2, 2, 2)
            w_layout.setSpacing(4)
            w_layout.setAlignment(Qt.AlignCenter)

            if not res.get("is_playlist"):
                play_btn = QPushButton("Vorhören")
                play_btn.setObjectName("toolbarBtn")
                play_btn.setIcon(get_icon("play"))
                play_btn.setIconSize(QSize(13, 13))
                play_btn.setToolTip("Vorhören per Direct-Stream (ohne Download)")
                play_btn.clicked.connect(lambda _, r=res: self.preview_stream(r))
                w_layout.addWidget(play_btn)

                dl_btn = QPushButton("Laden")
                dl_btn.setObjectName("primaryBtn")
                dl_btn.setIcon(get_icon("download"))
                dl_btn.setIconSize(QSize(13, 13))
                dl_btn.setToolTip("In Bibliothek laden")
                dl_btn.clicked.connect(lambda _, r=res: self._handle_search_hit(r))
                w_layout.addWidget(dl_btn)
            else:
                pl_btn = QPushButton("Öffnen")
                pl_btn.setObjectName("primaryBtn")
                pl_btn.setIcon(get_icon("playlist"))
                pl_btn.setIconSize(QSize(13, 13))
                pl_btn.setToolTip("Playlist im Downloader analysieren")
                pl_btn.clicked.connect(lambda _, r=res: self._handle_search_hit(r))
                w_layout.addWidget(pl_btn)

            self.discover_table.setIndexWidget(self.discover_model.index(row, 5), w)

    def _on_search_scroll(self, val: int):
        sb = self.discover_table.verticalScrollBar()
        if sb.maximum() > 0 and val >= sb.maximum() - 2:
            self._load_more_search_results()

    def _set_discover_filter(self, filter_key: str):
        self.discover_filter = filter_key
        for k, b in self.disc_filter_buttons.items():
            b.setProperty("active", "true" if k == filter_key else "false")
            b.style().unpolish(b)
            b.style().polish(b)
        if self.discover_input.text().strip():
            self.run_youtube_search()

    def run_youtube_search(self):
        query = self.discover_input.text().strip()
        if not query:
            return
        self.discover_query = query
        self.discover_loading = True
        self.discover_has_more = True
        self.discover_status.setText(f"Suche nach „{query}“ …")
        self.discover_btn.setEnabled(False)
        task = SearchTask(query, self.discover_filter, start=1, limit=30)
        task.signals.done.connect(self._on_search_done)
        task.signals.error.connect(self._on_search_error)
        self.start_task(task)

    def _on_search_done(self, results: list):
        self.discover_loading = False
        self.discover_btn.setEnabled(True)
        self.discover_model.set_rows(results)
        self._attach_discover_action_buttons(0)
        if len(results) < 30:
            self.discover_has_more = False
        self.discover_status.setText(f"{len(results)} Treffer gefunden.")

    def _load_more_search_results(self):
        if getattr(self, "discover_loading", False) or not getattr(self, "discover_has_more", True):
            return
        query = getattr(self, "discover_query", "")
        if not query:
            return
        self.discover_loading = True
        cur_count = len(self.discover_model.rows)
        self.discover_status.setText(f"{cur_count} Treffer (lädt weitere nach …)")
        task = SearchTask(query, self.discover_filter, start=cur_count + 1, limit=30)
        task.signals.done.connect(self._on_search_more_done)
        task.signals.error.connect(lambda _: setattr(self, "discover_loading", False))
        self.start_task(task)

    def _on_search_more_done(self, new_results: list):
        self.discover_loading = False
        if not new_results:
            self.discover_has_more = False
            self.discover_status.setText(f"{len(self.discover_model.rows)} Treffer (alle geladen).")
            return
        if len(new_results) < 30:
            self.discover_has_more = False
        prev_count = len(self.discover_model.rows)
        self.discover_model.append_rows(new_results)
        self._attach_discover_action_buttons(prev_count)
        self.discover_status.setText(f"{len(self.discover_model.rows)} Treffer geladen.")

    def _on_search_error(self, err: str):
        self.discover_loading = False
        self.discover_btn.setEnabled(True)
        self.discover_status.setText("Suche fehlgeschlagen.")
        QMessageBox.warning(self, "Suchfehler", f"Fehler bei der YouTube-Suche:\n{err}")

    def _on_search_result_double_clicked(self, idx: QModelIndex):
        if not idx.isValid() or idx.row() >= len(self.discover_model.rows):
            return
        res = self.discover_model.rows[idx.row()]
        if res.get("is_playlist"):
            self._handle_search_hit(res)
        else:
            self.preview_stream(res)

    def _preview_selected_search_result(self):
        indexes = self.discover_table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(self, "Keine Auswahl", "Bitte wähle zuerst einen Treffer aus der Tabelle aus.")
            return
        row = indexes[0].row()
        res = self.discover_model.rows[row]
        if res.get("is_playlist"):
            self._handle_search_hit(res)
        else:
            self.preview_stream(res)

    def _download_selected_search_result(self):
        indexes = self.discover_table.selectionModel().selectedRows()
        if not indexes:
            QMessageBox.information(self, "Keine Auswahl", "Bitte wähle zuerst einen Treffer aus der Tabelle aus.")
            return
        row = indexes[0].row()
        res = self.discover_model.rows[row]
        self._handle_search_hit(res)

    def _handle_search_hit(self, res: dict):
        if res.get("is_playlist"):
            self.links.setText(res["url"])
            self.nav.setCurrentRow(0)
            self.analyze()
        else:
            track = TrackMetadata(
                title=res["title"],
                artist=res["artist"],
                cover_url=res.get("cover_url", ""),
                source_url=res["url"],
                duration=res.get("duration", 0),
                collection="Einzeltitel"
            )
            self.cancelled.clear()
            self.resumed.set()
            self.paused = False

            q_idx = self.queue_model.add_task(
                track.title,
                track.artist,
                track.cover_url,
                playlist="Single",
                track_obj=track
            )
            task = DownloadTask(
                track, -1, q_idx, 1, 1,
                self.music_root, self.db, self.cancelled, self.resumed
            )
            task.signals.progress.connect(self._on_download_progress)
            task.signals.status.connect(self._on_download_status)
            self.start_task(task)
            self.update_queue_stats()
            self.nav.setCurrentRow(5)

    def _search_context_menu(self, point):
        idx = self.discover_table.indexAt(point)
        if not idx.isValid() or idx.row() >= len(self.discover_model.rows):
            return
        res = self.discover_model.rows[idx.row()]
        menu = QMenu(self)

        if res.get("is_playlist"):
            menu.addAction(get_icon("playlist"), "Playlist in Downloader analysieren", lambda: self._handle_search_hit(res))
        else:
            menu.addAction(get_icon("play"), "Vorhören (Direct Stream)", lambda: self.preview_stream(res))
            menu.addAction(get_icon("download"), "In Bibliothek laden", lambda: self._handle_search_hit(res))
            menu.addAction(get_icon("zap"), "Ähnliche Songs anzeigen", lambda: (self.details_panel.show(), self._switch_detail_tab(2), self._load_recommendations_for_track(res)))
            menu.addAction(get_icon("downloader"), "In Downloader einfügen", lambda: (self.links.setText(res["url"]), self.nav.setCurrentRow(0)))

        menu.addAction(get_icon("link"), "YouTube-Link kopieren", lambda: QApplication.clipboard().setText(res["url"]))
        menu.addAction(get_icon("compass"), "Im Browser öffnen", lambda: QDesktopServices.openUrl(QUrl(res["url"])))
        menu.exec(self.discover_table.viewport().mapToGlobal(point))

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
        tb_layout.setSpacing(8)

        refresh_btn = self._button("Sync", self.run_sync_library, obj_name="toolbarBtn", icon=get_icon("sync"), icon_size=QSize(16, 16))
        cover_btn = self._button("Covers", self.run_cover_search, obj_name="toolbarBtn", icon=get_icon("covers"), icon_size=QSize(16, 16))
        clean_btn = self._button("Clean", lambda: self.clean_selected_tags(favorites), obj_name="toolbarBtn", icon=get_icon("zap"), icon_size=QSize(16, 16))
        clean_btn.setToolTip("Markierte Tracks automatisch bereinigen (YouTube-Müll entfernen, Artist/Titel trennen)")
        folder_btn = self._button("Ordner", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.music_root))), obj_name="toolbarBtn", icon=get_icon("folder"), icon_size=QSize(16, 16))
        delete_btn = self._button("Löschen", lambda: self.delete_selected_track(favorites), obj_name="toolbarBtn", icon=get_icon("trash"), icon_size=QSize(16, 16))

        for b in [refresh_btn, cover_btn, clean_btn, folder_btn, delete_btn]:
            tb_layout.addWidget(b)

        # Integrated Library Stats Label
        stats_lbl = QLabel("")
        stats_lbl.setObjectName("secondary")
        stats_lbl.setStyleSheet("font-size: 13px; font-weight: 500; margin-left: 8px;")
        stats_lbl.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        tb_layout.addWidget(stats_lbl, 1)

        tb_layout.addStretch()

        # View Toggle Buttons
        view_stack = QStackedWidget()

        def _set_view(idx, is_fav=favorites):
            view_stack.setCurrentIndex(idx)
            list_toggle.setProperty("active", "true" if idx == 0 else "false")
            grid_toggle.setProperty("active", "true" if idx == 1 else "false")
            list_toggle.style().unpolish(list_toggle)
            list_toggle.style().polish(list_toggle)
            grid_toggle.style().unpolish(grid_toggle)
            grid_toggle.style().polish(grid_toggle)

            if idx == 1:
                if is_fav and getattr(self, "_fav_grid_dirty", False):
                    self._populate_grid(self.fav_grid, self.fav_model.rows)
                    self._fav_grid_dirty = False
                elif not is_fav and getattr(self, "_lib_grid_dirty", False):
                    self._populate_grid(self.lib_grid, self.lib_model.rows)
                    self._lib_grid_dirty = False

        list_toggle = self._button("Liste", lambda _=None: _set_view(0), obj_name="toolbarBtn", icon=get_icon("view-list"), icon_size=QSize(16, 16))
        grid_toggle = self._button("Raster", lambda _=None: _set_view(1), obj_name="toolbarBtn", icon=get_icon("view-grid"), icon_size=QSize(16, 16))
        list_toggle.setProperty("active", "true")
        grid_toggle.setProperty("active", "false")
        tb_layout.addWidget(list_toggle)
        tb_layout.addWidget(grid_toggle)

        # Live Search Field on Right
        search_input = QLineEdit()
        search_input.setObjectName("searchBar")
        search_input.setPlaceholderText("Suchen …")
        search_input.addAction(get_icon("search"), QLineEdit.LeadingPosition)
        search_input.setMinimumWidth(120)
        search_input.setMaximumWidth(260)
        search_input.textChanged.connect(self.on_search_changed)
        tb_layout.addWidget(search_input)

        layout.addWidget(toolbar)

        if not favorites:
            chip_frame = QFrame()
            chip_frame.setObjectName("chipBar")
            chip_layout = QHBoxLayout(chip_frame)
            chip_layout.setContentsMargins(0, 0, 0, 0)
            chip_layout.setSpacing(8)

            self.chip_buttons = {}
            chips_def = [
                ("Alle", "Alle", None),
                ("Favoriten", "Favoriten", "heart"),
                ("Zuletzt hinzugefügt", "Zuletzt hinzugefügt", "clock"),
                ("Nicht gehört", "Nicht gehört", "headphones"),
                ("Playlists", "Playlists", "playlist"),
                ("artist_menu", "Künstler ▾", "users"),
                ("year_menu", "Jahr ▾", "calendar"),
                ("genre_menu", "Genre ▾", "tag"),
            ]
            for key, label, icon_name in chips_def:
                btn = QPushButton(label)
                if icon_name:
                    btn.setIcon(get_icon(icon_name))
                    btn.setIconSize(QSize(14, 14))
                btn.setObjectName("chipBtn")
                btn.setProperty("active", "true" if key == "Alle" else "false")
                btn.clicked.connect(lambda _, k=key, b=btn: self._on_chip_clicked(k, b))
                chip_layout.addWidget(btn)
                self.chip_buttons[key] = btn

            chip_layout.addStretch()

            chip_scroll = QScrollArea()
            chip_scroll.setWidgetResizable(True)
            chip_scroll.setFrameShape(QFrame.NoFrame)
            chip_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            chip_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            chip_scroll.setFixedHeight(44)
            chip_scroll.setStyleSheet("background: transparent; border: none;")
            chip_scroll.wheelEvent = lambda ev: chip_scroll.horizontalScrollBar().setValue(
                chip_scroll.horizontalScrollBar().value() - ev.angleDelta().y()
            )
            chip_scroll.setWidget(chip_frame)
            layout.addWidget(chip_scroll)

        # Table View
        model = TrackModel(selectable=True)
        table = self._create_styled_table(model)
        table.setContextMenuPolicy(Qt.CustomContextMenu)
        table.customContextMenuRequested.connect(lambda p, t=table, m=model: self.context_menu(t, m, p))
        table.doubleClicked.connect(lambda idx, m=model: self.play(m.rows[idx.row()], idx.row(), m.rows) if 0 <= idx.row() < len(m.rows) else None)
        table.clicked.connect(lambda idx, m=model: self.show_track_details(m.rows[idx.row()]) if 0 <= idx.row() < len(m.rows) else None)

        # Grid View
        grid = QListWidget()
        grid.setViewMode(QListWidget.IconMode)
        grid.setIconSize(QSize(130, 130))
        grid.setGridSize(QSize(176, 216))
        grid.setResizeMode(QListWidget.Adjust)
        grid.setSpacing(0)
        grid.setViewportMargins(8, 8, 8, 8)
        grid.setItemDelegate(GridCardDelegate(grid))
        grid.itemDoubleClicked.connect(lambda item, m=model: self._on_grid_double_click(item, m))
        grid.itemClicked.connect(lambda item: self.show_track_details(item.data(Qt.UserRole)))

        grid.setAcceptDrops(True)
        grid.dragEnterEvent = self.dragEnterEvent
        grid.dragMoveEvent = self.dragMoveEvent
        grid.dropEvent = self.dropEvent
        grid.viewport().setAcceptDrops(True)
        grid.viewport().dragEnterEvent = self.dragEnterEvent
        grid.viewport().dragMoveEvent = self.dragMoveEvent
        grid.viewport().dropEvent = self.dropEvent

        view_stack.addWidget(table)
        view_stack.addWidget(grid)

        # Empty State View (replaces blank black void)
        empty_frame = QFrame()
        empty_layout = QVBoxLayout(empty_frame)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_layout.setSpacing(12)

        icon_label = QLabel()
        icon_pix = get_icon("library" if not favorites else "heart").pixmap(48, 48)
        icon_label.setPixmap(icon_pix)
        icon_label.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(icon_label)

        empty_title = QLabel("Deine Bibliothek ist noch leer" if not favorites else "Noch keine Favoriten vorhanden")
        empty_title.setStyleSheet("font-size: 18px; font-weight: 700; color: #F4F4F4;")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_title)

        empty_desc = QLabel(
            "Lade Musik über den Downloader herunter oder öffne deinen Musikordner."
            if not favorites else
            "Markiere Songs mit Rechtsklick in der Bibliothek als Favorit."
        )
        empty_desc.setObjectName("secondary")
        empty_desc.setAlignment(Qt.AlignCenter)
        empty_layout.addWidget(empty_desc)

        if not favorites:
            empty_btn_row = QHBoxLayout()
            empty_btn_row.setAlignment(Qt.AlignCenter)
            empty_btn_row.setSpacing(12)
            btn_dl = self._button("Zum Downloader", lambda: self.show_page(0), True, icon=get_icon("downloader"), icon_size=QSize(16, 16))
            btn_folder = self._button("Musikordner öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.music_root))), icon=get_icon("folder"), icon_size=QSize(16, 16))
            empty_btn_row.addWidget(btn_dl)
            empty_btn_row.addWidget(btn_folder)
            empty_layout.addLayout(empty_btn_row)

        content_stack = QStackedWidget()
        content_stack.addWidget(view_stack)   # 0: table/grid
        content_stack.addWidget(empty_frame)  # 1: empty state

        layout.addWidget(content_stack, 1)

        if favorites:
            self.fav_model, self.fav_table, self.fav_grid, self.fav_search = model, table, grid, search_input
            self.fav_view_stack = view_stack
            self.fav_list_btn, self.fav_grid_btn = list_toggle, grid_toggle
            self.fav_stats_lbl = stats_lbl
            self.fav_content_stack = content_stack
        else:
            self.lib_model, self.lib_table, self.lib_grid, self.lib_search = model, table, grid, search_input
            self.lib_view_stack = view_stack
            self.lib_list_btn, self.lib_grid_btn = list_toggle, grid_toggle
            self.lib_stats_lbl = stats_lbl
            self.lib_content_stack = content_stack
        return page

    def _on_chip_clicked(self, key: str, btn: QPushButton):
        if key in ("artist_menu", "year_menu", "genre_menu") and btn.text().endswith("✕"):
            self._apply_chip("Alle")
            return

        if key == "artist_menu":
            artists = self.db.values_for("artist")
            if not artists:
                return
            menu = QMenu(self)
            for a in artists[:30]:
                menu.addAction(a, lambda val=a: self._apply_custom_chip("artist_menu", f"Künstler: {val}", val))
            menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
            return

        if key == "year_menu":
            years = [y for y in self.db.values_for("year") if y and y.strip().isdigit()]
            years = sorted(set(years), reverse=True)
            if not years:
                return
            menu = QMenu(self)
            for y in years[:25]:
                menu.addAction(y, lambda val=y: self._apply_custom_chip("year_menu", f"Jahr: {val}", val))
            menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
            return

        if key == "genre_menu":
            genres = self.db.values_for("genre")
            if not genres:
                return
            menu = QMenu(self)
            for g in genres[:25]:
                menu.addAction(g, lambda val=g: self._apply_custom_chip("genre_menu", f"Genre: {val}", val))
            menu.exec(btn.mapToGlobal(btn.rect().bottomLeft()))
            return

        self._apply_chip(key)

    def _apply_chip(self, chip_name: str):
        self.current_chip = chip_name
        if hasattr(self, "chip_buttons"):
            if "artist_menu" in self.chip_buttons:
                self.chip_buttons["artist_menu"].setText("Künstler ▾")
            if "year_menu" in self.chip_buttons:
                self.chip_buttons["year_menu"].setText("Jahr ▾")
            if "genre_menu" in self.chip_buttons:
                self.chip_buttons["genre_menu"].setText("Genre ▾")

            for k, b in self.chip_buttons.items():
                is_act = (k == chip_name)
                b.setProperty("active", "true" if is_act else "false")
                b.style().unpolish(b)
                b.style().polish(b)

        self.refresh_library()

    def _apply_custom_chip(self, menu_key: str, chip_filter: str, display_text: str):
        self.current_chip = chip_filter
        if hasattr(self, "chip_buttons"):
            for k, b in self.chip_buttons.items():
                is_act = (k == menu_key)
                b.setProperty("active", "true" if is_act else "false")
                if k == menu_key:
                    b.setText(f"{display_text} ✕")
                elif k == "artist_menu" and menu_key != "artist_menu":
                    self.chip_buttons["artist_menu"].setText("Künstler ▾")
                elif k == "year_menu" and menu_key != "year_menu":
                    self.chip_buttons["year_menu"].setText("Jahr ▾")
                elif k == "genre_menu" and menu_key != "genre_menu":
                    self.chip_buttons["genre_menu"].setText("Genre ▾")
                b.style().unpolish(b)
                b.style().polish(b)

        self.refresh_library()

    def _create_styled_table(self, model: TrackModel) -> QTableView:
        table = QTableView()
        table.setModel(model)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.verticalHeader().setDefaultSectionSize(64)
        table.verticalHeader().setVisible(False)
        table.setSortingEnabled(True)

        header = table.horizontalHeader()
        header.setSortIndicator(-1, Qt.AscendingOrder)
        header.setSectionsClickable(True)
        header.sectionClicked.connect(lambda col: self._on_header_clicked(col, model, table))

        # Checkbox & Cover
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        table.setColumnWidth(0, 36)
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        table.setColumnWidth(1, 56)

        # Proportional balanced width distribution
        header.setSectionResizeMode(2, QHeaderView.Stretch)
        header.setSectionResizeMode(3, QHeaderView.Interactive)
        table.setColumnWidth(3, 170)
        header.setSectionResizeMode(4, QHeaderView.Interactive)
        table.setColumnWidth(4, 150)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        table.setColumnWidth(5, 65)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        table.setColumnWidth(6, 55)
        header.setSectionResizeMode(7, QHeaderView.Fixed)
        table.setColumnWidth(7, 70)
        header.setSectionResizeMode(8, QHeaderView.Fixed)
        table.setColumnWidth(8, 80)

        table.setAcceptDrops(True)
        table.dragEnterEvent = self.dragEnterEvent
        table.dragMoveEvent = self.dragMoveEvent
        table.dropEvent = self.dropEvent
        table.viewport().setAcceptDrops(True)
        table.viewport().dragEnterEvent = self.dragEnterEvent
        table.viewport().dragMoveEvent = self.dragMoveEvent
        table.viewport().dropEvent = self.dropEvent
        return table

    def _on_header_clicked(self, col: int, model: TrackModel, table: QTableView | None = None):
        if col < 2 and table is not None:
            prev_col = getattr(model, "_sort_col", None)
            prev_order = getattr(model, "_sort_order", Qt.AscendingOrder)
            table.horizontalHeader().setSortIndicator(prev_col if prev_col is not None else -1, prev_order)
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
        layout.setSpacing(14)

        header_row = QHBoxLayout()
        header_row.addWidget(QLabel("<h2>Aktive Downloads & Warteschlange</h2>"))
        header_row.addStretch()
        self.pause_btn = self._button("Pausieren", self.pause_download, icon=get_icon("pause"))
        self.retry_btn = self._button("Wiederholen", self.retry_failed_downloads, icon=get_icon("refresh"))
        self.cancel_btn = self._button("Abbrechen", self.cancel_download, obj_name="danger", icon=get_icon("trash"))
        header_row.addWidget(self.pause_btn)
        header_row.addWidget(self.retry_btn)
        header_row.addWidget(self.cancel_btn)
        layout.addLayout(header_row)

        # 4 Top Live Stat Badges (Priority 4)
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)

        self.stat_active_val = QLabel("0")
        self.stat_waiting_val = QLabel("0")
        self.stat_done_val = QLabel("0")
        self.stat_failed_val = QLabel("0")

        badge_configs = [
            (self.stat_active_val, "Aktiv", "#3DDC63"),
            (self.stat_waiting_val, "In Warteschlange", "#A0A6AD"),
            (self.stat_done_val, "Fertig", "#48E76E"),
            (self.stat_failed_val, "Fehlgeschlagen", "#E06C75"),
        ]
        for val_lbl, title_text, col in badge_configs:
            card = QFrame()
            card.setObjectName("dlStatCard")
            c_layout = QVBoxLayout(card)
            c_layout.setContentsMargins(16, 10, 16, 10)
            c_layout.setSpacing(2)
            val_lbl.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {col};")
            lbl_title = QLabel(title_text)
            lbl_title.setObjectName("secondary")
            lbl_title.setStyleSheet("font-size: 12px; font-weight: 500;")
            c_layout.addWidget(val_lbl)
            c_layout.addWidget(lbl_title)
            stats_row.addWidget(card)

        layout.addLayout(stats_row)

        self.queue_model = DownloadQueueModel()
        self.queue_table = QTableView()
        self.queue_table.setModel(self.queue_model)
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.queue_table.verticalHeader().setDefaultSectionSize(60)
        self.queue_table.verticalHeader().setVisible(False)
        header = self.queue_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.queue_table.setColumnWidth(0, 56)
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        header.setSectionResizeMode(2, QHeaderView.Interactive)
        self.queue_table.setColumnWidth(2, 140)
        header.setSectionResizeMode(3, QHeaderView.Fixed)
        self.queue_table.setColumnWidth(3, 110)
        header.setSectionResizeMode(4, QHeaderView.Fixed)
        self.queue_table.setColumnWidth(4, 60)
        header.setSectionResizeMode(5, QHeaderView.Fixed)
        self.queue_table.setColumnWidth(5, 80)
        header.setSectionResizeMode(6, QHeaderView.Fixed)
        self.queue_table.setColumnWidth(6, 60)
        layout.addWidget(self.queue_table, 1)

        self.queue_progress = QProgressBar()
        layout.addWidget(self.queue_progress)
        self.queue_summary = QLabel("Keine aktiven Downloads.")
        self.queue_summary.setObjectName("secondary")
        layout.addWidget(self.queue_summary)
        return page

    def update_queue_stats(self):
        db_stats = self.db.queue_stats()
        in_mem_aktiv = sum(1 for item in getattr(self, "queue_model", None).items if "Lädt" in item.get("status", "")) if hasattr(self, "queue_model") else 0
        in_mem_wartend = sum(1 for item in getattr(self, "queue_model", None).items if item.get("status") in ("In Warteschlange", "Bereit")) if hasattr(self, "queue_model") else 0
        in_mem_fertig = sum(1 for item in getattr(self, "queue_model", None).items if item.get("status") == "Fertig") if hasattr(self, "queue_model") else 0
        in_mem_failed = sum(1 for item in getattr(self, "queue_model", None).items if "Fehler" in item.get("status", "") or "Abgebrochen" in item.get("status", "")) if hasattr(self, "queue_model") else 0

        total_aktiv = max(db_stats.get("aktiv", 0), in_mem_aktiv)
        total_wartend = max(db_stats.get("wartend", 0), in_mem_wartend)
        total_fertig = db_stats.get("fertig", 0) + in_mem_fertig
        total_failed = db_stats.get("fehlgeschlagen", 0) + in_mem_failed

        if hasattr(self, "stat_active_val"):
            self.stat_active_val.setText(str(total_aktiv))
            self.stat_waiting_val.setText(str(total_wartend))
            self.stat_done_val.setText(str(total_fertig))
            self.stat_failed_val.setText(str(total_failed))

    def _playlists_page(self) -> QWidget:
        self.pl_stack = QStackedWidget()

        # Page 0: Cards Grid
        page_overview = QFrame()
        page_overview.setObjectName("card")
        ov_layout = QVBoxLayout(page_overview)
        ov_layout.setContentsMargins(20, 18, 20, 18)
        ov_layout.setSpacing(14)

        top_row = QHBoxLayout()
        top_title = QLabel("<h2>Playlists</h2>")
        top_row.addWidget(top_title)
        top_row.addStretch()
        top_row.addWidget(self._button("＋ Neue Playlist anlegen", self.new_playlist, True))
        ov_layout.addLayout(top_row)

        self.pl_cards = QListWidget()
        self.pl_cards.setObjectName("playlistGrid")
        self.pl_cards.setViewMode(QListWidget.IconMode)
        self.pl_cards.setIconSize(QSize(150, 150))
        self.pl_cards.setGridSize(QSize(210, 250))
        self.pl_cards.setResizeMode(QListWidget.Adjust)
        self.pl_cards.setSpacing(16)
        self.pl_cards.itemClicked.connect(self._on_playlist_card_clicked)
        ov_layout.addWidget(self.pl_cards, 1)

        self.pl_stack.addWidget(page_overview)

        # Page 1: Detail View
        page_detail = QFrame()
        page_detail.setObjectName("card")
        dt_layout = QVBoxLayout(page_detail)
        dt_layout.setContentsMargins(20, 18, 20, 18)
        dt_layout.setSpacing(12)

        back_btn = self._button("← Zurück zu allen Playlists", lambda: self.pl_stack.setCurrentIndex(0))
        back_btn.setFixedWidth(210)
        dt_layout.addWidget(back_btn)

        # Large Header Card
        header_card = QFrame()
        header_card.setObjectName("playlistHeaderCard")
        hc_layout = QHBoxLayout(header_card)
        hc_layout.setContentsMargins(16, 16, 16, 16)
        hc_layout.setSpacing(16)

        self.pl_detail_cover = QLabel()
        self.pl_detail_cover.setFixedSize(130, 130)
        self.pl_detail_cover.setPixmap(get_cover_pixmap("", 130))
        hc_layout.addWidget(self.pl_detail_cover)

        hc_info = QVBoxLayout()
        hc_info.setSpacing(4)
        type_lbl = QLabel("PLAYLIST")
        type_lbl.setObjectName("metaBadge")
        type_lbl.setFixedWidth(70)
        self.pl_detail_title = QLabel("Playlist Name")
        self.pl_detail_title.setStyleSheet("font-size: 22px; font-weight: 700; color: #F4F4F4;")
        self.pl_detail_meta = QLabel("0 Songs · 0:00 · 0 MB")
        self.pl_detail_meta.setObjectName("secondary")
        self.pl_detail_meta.setStyleSheet("font-size: 13px;")

        hc_btns = QHBoxLayout()
        hc_btns.setSpacing(10)
        self.pl_play_all_btn = self._button("Alle abspielen", self._play_all_playlist, True, icon=get_icon("play"))
        self.pl_sync_btn = self._button("Playlist synchronisieren", self._sync_current_playlist, icon=get_icon("sync"))
        self.pl_open_folder_btn = self._button("Ordner öffnen", self._open_playlist_dir, icon=get_icon("folder"))
        self.pl_del_btn = self._button("Playlist löschen", self.delete_current_playlist, obj_name="danger", icon=get_icon("trash"))

        hc_btns.addWidget(self.pl_play_all_btn)
        hc_btns.addWidget(self.pl_sync_btn)
        hc_btns.addWidget(self.pl_open_folder_btn)
        hc_btns.addWidget(self.pl_del_btn)
        hc_btns.addStretch()

        hc_info.addWidget(type_lbl)
        hc_info.addWidget(self.pl_detail_title)
        hc_info.addWidget(self.pl_detail_meta)
        hc_info.addLayout(hc_btns)
        hc_layout.addLayout(hc_info, 1)

        dt_layout.addWidget(header_card)

        # Track Table
        self.pl_track_model = TrackModel(selectable=True)
        self.pl_table = self._create_styled_table(self.pl_track_model)
        self.pl_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.pl_table.customContextMenuRequested.connect(lambda p: self.context_menu(self.pl_table, self.pl_track_model, p))
        self.pl_table.doubleClicked.connect(lambda idx: self.play(self.pl_track_model.rows[idx.row()], idx.row(), self.pl_track_model.rows))
        self.pl_table.clicked.connect(lambda idx: self.show_track_details(self.pl_track_model.rows[idx.row()]))
        dt_layout.addWidget(self.pl_table, 1)

        self.pl_stack.addWidget(page_detail)
        return self.pl_stack

    def _settings_page(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setObjectName("settingsScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        content = QFrame()
        content.setObjectName("card")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 22, 28, 22)
        layout.setSpacing(14)

        layout.addWidget(QLabel("<h2>Einstellungen</h2>"))

        # Musikordner
        layout.addWidget(QLabel("Musikordner"))
        folder_row = QHBoxLayout()
        folder_row.setSpacing(10)
        self.folder = QLineEdit(str(self.music_root))
        self.folder.setPlaceholderText("Pfad zum Musikordner")
        choose_btn = self._button("Ordner auswählen …", self.choose_folder, icon=get_icon("folder"))
        folder_row.addWidget(self.folder, 1)
        folder_row.addWidget(choose_btn)
        layout.addLayout(folder_row)

        # Dropdowns side-by-side
        self.quality = QComboBox()
        self.quality.addItems(["320", "256", "192"])
        self.quality.setCurrentText(self.settings.get("quality", "320"))
        self.parallel = QComboBox()
        self.parallel.addItems(["3", "2", "1", "4", "5"])
        self.parallel.setCurrentText(self.settings.get("parallel", "3"))

        drop_row = QHBoxLayout()
        drop_row.setSpacing(16)

        col_quality = QVBoxLayout()
        col_quality.setSpacing(6)
        col_quality.addWidget(QLabel("Standard-Audioqualität (kbps)"))
        col_quality.addWidget(self.quality)
        drop_row.addLayout(col_quality, 1)

        col_parallel = QVBoxLayout()
        col_parallel.setSpacing(6)
        col_parallel.addWidget(QLabel("Gleichzeitige Downloads (max. 3 empfohlen)"))
        col_parallel.addWidget(self.parallel)
        drop_row.addLayout(col_parallel, 1)

        layout.addLayout(drop_row)

        # 5 Settings Checkboxes (Priority 8)
        chk_group = QFrame()
        chk_group.setObjectName("metaBox")
        chk_layout = QVBoxLayout(chk_group)
        chk_layout.setContentsMargins(16, 14, 16, 14)
        chk_layout.setSpacing(10)

        self.chk_auto_cover = QCheckBox("Albumcover automatisch online laden (iTunes, Deezer)")
        self.chk_auto_cover.setChecked(self.settings.get("auto_cover", "1") == "1")

        self.chk_auto_meta = QCheckBox("Metadaten automatisch aktualisieren")
        self.chk_auto_meta.setChecked(self.settings.get("auto_metadata", "1") == "1")

        self.chk_only_new = QCheckBox("Nur neue Songs laden (Duplikate überspringen)")
        self.chk_only_new.setChecked(self.settings.get("only_new", "1") == "1")

        self.chk_cleanup_startup = QCheckBox("Fehlende Dateien beim Programmstart bereinigen")
        self.chk_cleanup_startup.setChecked(self.settings.get("cleanup_missing_startup", "0") == "1")

        self.chk_auto_sync_pl = QCheckBox("Playlists automatisch synchronisieren")
        self.chk_auto_sync_pl.setChecked(self.settings.get("auto_sync_playlist", "0") == "1")

        for chk in (self.chk_auto_cover, self.chk_auto_meta, self.chk_only_new, self.chk_cleanup_startup, self.chk_auto_sync_pl):
            chk.setMinimumHeight(24)
            chk_layout.addWidget(chk)

        layout.addWidget(chk_group)

        # Actions
        save_btn = self._button("Speichern", self.save_settings, True, icon=get_icon("check"))
        save_btn.setMinimumWidth(160)
        btn_row = QHBoxLayout()
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()

        try:
            from main import __version__
        except ImportError:
            __version__ = "v1.0.0"

        footer_lbl = QLabel(f"M-Player {__version__} • Made by marka87")
        footer_lbl.setObjectName("secondary")
        footer_lbl.setStyleSheet("font-size: 11px; color: #6a7282;")
        footer_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer_lbl)

        scroll.setWidget(content)
        return scroll

    def _player_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("playerBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(16)

        # Left Zone: Cover + Titles
        left_widget = QWidget()
        left_widget.setMinimumWidth(300)
        left = QHBoxLayout(left_widget)
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(12)

        self.bar_cover = QLabel()
        self.bar_cover.setFixedSize(56, 56)
        self.bar_cover.setPixmap(get_cover_pixmap("", 56))
        left.addWidget(self.bar_cover)

        meta_box = QVBoxLayout()
        meta_box.setSpacing(2)
        meta_box.setAlignment(Qt.AlignVCenter)
        self.now_title = QLabel("Kein Song ausgewählt")
        self.now_title.setStyleSheet("font-weight: 700; color: #F4F4F4; font-size: 13px;")
        
        self.now_artist = QLabel("Wähle einen Song aus der Bibliothek")
        self.now_artist.setObjectName("secondary")
        self.now_artist.setStyleSheet("font-size: 11px;")
        
        self.now_audio_info = QLabel("320 kbps | 44.1 kHz | Stereo")
        self.now_audio_info.setStyleSheet("color: #3DDC63; font-family: monospace; font-size: 10px;")
        self.now_audio_info.hide()
        
        meta_box.addWidget(self.now_title)
        meta_box.addWidget(self.now_artist)
        meta_box.addWidget(self.now_audio_info)
        
        left.addLayout(meta_box, 1)

        # Quick action buttons in mini player (reduced to just Favorite)
        self.bar_fav_btn = self._button("", self._toggle_current_fav, obj_name="playerBtn", icon=get_icon("heart"), icon_size=QSize(18, 18))
        self.bar_fav_btn.setToolTip("Zu Favoriten hinzufügen")

        left.addWidget(self.bar_fav_btn)
        layout.addWidget(left_widget, 1)

        # Center Zone: Playback Controls & Timeline
        center_widget = QWidget()
        center = QVBoxLayout(center_widget)
        center.setContentsMargins(0, 0, 0, 0)
        center.setSpacing(4)
        center.setAlignment(Qt.AlignCenter)

        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(8)
        ctrl_row.setAlignment(Qt.AlignCenter)

        self.shuffle_btn = self._button("", self.toggle_shuffle, obj_name="playerBtn", icon=get_icon("shuffle"), icon_size=QSize(18, 18))
        self.prev_btn = self._button("", lambda: self.skip(-1), obj_name="playerBtn", icon=get_icon("previous"), icon_size=QSize(20, 20))
        self.play_btn = self._button("", self.toggle_play, obj_name="playPauseBtn", icon=get_icon("play"), icon_size=QSize(24, 24))
        self.next_btn = self._button("", lambda: self.skip(1), obj_name="playerBtn", icon=get_icon("next"), icon_size=QSize(20, 20))
        self.repeat_btn = self._button("", self.toggle_repeat, obj_name="playerBtn", icon=get_icon("repeat"), icon_size=QSize(18, 18))

        if self.is_shuffle:
            self.shuffle_btn.setStyleSheet("color: #3DDC63;")
        if self.is_repeat:
            self.repeat_btn.setStyleSheet("color: #3DDC63;")

        for b in (self.shuffle_btn, self.prev_btn, self.play_btn, self.next_btn, self.repeat_btn):
            ctrl_row.addWidget(b)
        center.addLayout(ctrl_row)

        timeline = QHBoxLayout()
        timeline.setSpacing(10)
        self.time_cur = QLabel("0:00")
        self.time_cur.setObjectName("secondary")
        self.time_cur.setFixedWidth(36)
        self.time_cur.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.timeline_slider = ClickableSlider(Qt.Horizontal)
        self.timeline_slider.sliderMoved.connect(self.player.setPosition)

        self.time_total = QLabel("0:00")
        self.time_total.setObjectName("secondary")
        self.time_total.setFixedWidth(36)
        self.time_total.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        timeline.addWidget(self.time_cur)
        timeline.addWidget(self.timeline_slider, 1)
        timeline.addWidget(self.time_total)
        center.addLayout(timeline)
        
        layout.addWidget(center_widget, 0)

        # Right Zone: Volume Control
        right_widget = QWidget()
        right_widget.setMinimumWidth(180)
        right = QHBoxLayout(right_widget)
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(8)
        right.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        self.vol_btn = self._button("", self._toggle_mute, obj_name="playerBtn", icon=get_icon("volume"), icon_size=QSize(20, 20))
        self.vol_btn.setToolTip("Stummschalten / Wiederherstellen")

        saved_vol = int(float(self.settings.get("volume", "75")))
        self.vol_slider = ClickableSlider(Qt.Horizontal)
        self.vol_slider.setObjectName("volumeSlider")
        self.vol_slider.setRange(0, 100)
        self.vol_slider.setValue(saved_vol)
        self.vol_slider.setFixedWidth(110)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)

        self.mini_btn = self._button("", self.toggle_mini_player, obj_name="playerBtn", icon=get_icon("headphones"), icon_size=QSize(18, 18))
        self.mini_btn.setToolTip("Mini-Player (Immer im Vordergrund) [Ctrl+M]")

        right.addWidget(self.vol_btn)
        right.addWidget(self.vol_slider)
        right.addWidget(self.mini_btn)
        
        layout.addWidget(right_widget, 1)

        self.player.positionChanged.connect(self._on_position_changed)
        self.player.durationChanged.connect(self._on_duration_changed)
        return bar

    def show_page(self, index: int):
        self.pages.setCurrentIndex(index)
        if index in (2, 3):
            self.refresh_library()
        elif index == 4:
            self.refresh_playlists()

    def on_search_changed(self, text: str):
        self.search_timer.start()

    def analyze(self):
        urls = [u for u in self.links.text().split() if u.startswith("http")]
        if not urls:
            QMessageBox.warning(self, "Link fehlt", "Bitte einen gültigen YouTube- oder Spotify-Link eingeben.")
            return
        self.pre_status.setText("Playlist wird analysiert …")
        task = AnalyzeTask(urls, self.music_root, self.db)
        task.signals.done.connect(self._analysis_done)
        task.signals.error.connect(lambda err: self.pre_status.setText(f"Fehler: {err}"))
        self.start_task(task)

    def _analysis_done(self, tracks):
        self.pre_model.set_rows(tracks)
        self.pre_table.setColumnWidth(0, 36)
        self.pre_table.setColumnWidth(1, 56)
        self.pre_table.setColumnWidth(3, 260)
        self.pre_table.setColumnWidth(8, 105)
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
        self._batch_total = len(items)
        self._batch_remaining = len(items)
        self._batch_single_title = items[0][1].title if len(items) == 1 else None
        self.nav.setCurrentRow(5)

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
            self.start_task(task)

    def _on_download_progress(self, q_idx: int, ratio: float, title: str, speed: str, eta: str):
        status = "Fertig" if ratio >= 1.0 else "Lädt..."
        self.queue_model.update_task(q_idx, ratio, speed, eta, status)
        self.queue_progress.setValue(int(ratio * 100))
        self.queue_summary.setText(f"Aktuell: {title} | Speed: {speed} | Restzeit: {eta}")

    def _on_download_status(self, row_idx: int, status: str):
        if 0 <= row_idx < len(self.pre_model.rows):
            self.pre_model.status[row_idx] = status
            idx = self.pre_model.index(row_idx, 8)
            self.pre_model.dataChanged.emit(idx, idx)
        get_cover_pixmap.cache_clear()
        self.update_queue_stats()
        self.refresh_library()
        self.refresh_dashboard()

        if status == "Fertig":
            remaining = getattr(self, "_batch_remaining", 1) - 1
            self._batch_remaining = remaining
            total = getattr(self, "_batch_total", 1)
            if total == 1:
                title = getattr(self, "_batch_single_title", None)
                if not title and 0 <= row_idx < len(self.pre_model.rows):
                    title = getattr(self.pre_model.rows[row_idx], "title", "Song")
                self.notify("Download abgeschlossen", f"'{title}' wurde erfolgreich heruntergeladen." if title else "Song erfolgreich heruntergeladen.")
            elif remaining <= 0:
                self.notify("Download abgeschlossen", f"{total} Songs erfolgreich heruntergeladen.")

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
                    self.start_task(task)
                    retries += 1
        self.queue_summary.setText(f"{retries} Download(s) werden erneut versucht.")

    def run_sync_library(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Bibliothek synchronisieren")
        dialog.setFixedSize(440, 160)
        d_layout = QVBoxLayout(dialog)
        d_layout.setContentsMargins(22, 18, 22, 18)
        d_layout.setSpacing(12)

        lbl = QLabel("Dateisystem wird mit SQLite abgeglichen …")
        lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #F4F4F4;")
        pbar = QProgressBar()
        pbar.setRange(0, 0)
        pbar.setFixedHeight(10)
        d_layout.addWidget(lbl)
        d_layout.addWidget(pbar)

        cancel_btn = self._button("Schließen", dialog.reject)
        cancel_btn.setFixedWidth(100)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        d_layout.addLayout(btn_row)

        dialog.show()

        task = SyncLibraryTask(self.db, self.music_root)
        def on_prog(i, tot, name):
            pbar.setRange(0, tot)
            pbar.setValue(i)
            lbl.setText(f"Importiere ({i}/{tot}): {name}")

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
        self.start_task(task)

    def run_cover_search(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Albumcover suchen")
        dialog.setFixedSize(440, 160)
        d_layout = QVBoxLayout(dialog)
        d_layout.setContentsMargins(22, 18, 22, 18)
        d_layout.setSpacing(12)

        lbl = QLabel("Durchsuche iTunes, Deezer und MusicBrainz …")
        lbl.setStyleSheet("font-size: 13px; font-weight: 600; color: #F4F4F4;")
        pbar = QProgressBar()
        pbar.setFixedHeight(10)
        d_layout.addWidget(lbl)
        d_layout.addWidget(pbar)

        cancel_btn = self._button("Schließen", dialog.reject)
        cancel_btn.setFixedWidth(100)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        d_layout.addLayout(btn_row)

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
        self.start_task(task)

    def delete_selected_track(self, favorites: bool = False):
        model = self.fav_model if favorites else self.lib_model
        selected = model.selected()
        if not selected:
            QMessageBox.information(self, "Auswahl fehlt", "Bitte mindestens einen Song per Checkbox auswählen.")
            return

        titles = ", ".join(t["title"] for t in selected[:3])
        more = f" und {len(selected) - 3} weitere" if len(selected) > 3 else ""
        dlg = DeleteTrackDialog(f"{titles}{more}", count=len(selected), parent=self)
        if dlg.exec():
            delete_file = (dlg.choice == "disk")
            for track in selected:
                self.db.delete_track(track["id"], delete_file=delete_file)
            self.refresh_library()
            self.refresh_dashboard()

    def refresh_library(self):
        cur_page = self.pages.currentIndex() if hasattr(self, "pages") else 2
        is_fav_page = (cur_page == 3)

        lib_query = self.lib_search.text().strip() if hasattr(self, "lib_search") else ""
        fav_query = self.fav_search.text().strip() if hasattr(self, "fav_search") else ""

        if is_fav_page:
            fav_tracks = self.db.tracks(fav_query, favorites=True)
            self.fav_model.set_rows(fav_tracks)
            if hasattr(self, "fav_view_stack") and self.fav_view_stack.currentIndex() == 1:
                self._populate_grid(self.fav_grid, fav_tracks)
                self._fav_grid_dirty = False
            else:
                self._fav_grid_dirty = True
            if hasattr(self, "fav_content_stack"):
                self.fav_content_stack.setCurrentIndex(1 if len(fav_tracks) == 0 else 0)
        else:
            all_tracks = self.db.tracks(lib_query, filter_chip=self.current_chip)
            self.lib_model.set_rows(all_tracks)
            if hasattr(self, "lib_view_stack") and self.lib_view_stack.currentIndex() == 1:
                self._populate_grid(self.lib_grid, all_tracks)
                self._lib_grid_dirty = False
            else:
                self._lib_grid_dirty = True
            if hasattr(self, "lib_content_stack"):
                self.lib_content_stack.setCurrentIndex(1 if len(all_tracks) == 0 else 0)

        if not getattr(self, "current_track", None):
            self._update_sidebar_mini_card(None)

    def _populate_grid(self, grid: QListWidget, tracks: list):
        grid.clear()
        for t in tracks:
            item = QListWidgetItem()
            item.setText("")  # Delegate paints everything, omit text layout computations
            pix = get_cover_pixmap(t["file_path"], 130)
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
            total_size = sum(f.stat().st_size for f in p_dir.glob("*.mp3")) if p_dir.exists() else 0
            total_dur = sum(t["duration"] for t in tracks if t["duration"])

            card_item = QListWidgetItem()
            dur_str = f" • {time_text(total_dur)}" if total_dur > 0 else ""
            card_item.setText(f"{name}\n{count} Songs{dur_str}\n{format_size(total_size)}")
            cov_path = str(p_dir / "cover.jpg") if (p_dir / "cover.jpg").exists() else ""
            card_item.setIcon(QIcon(get_cover_pixmap(cov_path, 150)))
            card_item.setData(Qt.UserRole, name)
            self.pl_cards.addItem(card_item)

    def _on_playlist_card_clicked(self, item: QListWidgetItem):
        name = item.data(Qt.UserRole)
        if name:
            self._open_playlist_detail(name)

    def _open_playlist_detail(self, name: str):
        self.selected_playlist_name = name
        self.pl_detail_title.setText(name)
        p_dir = self.music_root / safe_name(name, "playlist")
        tracks = self.db.playlist_tracks(name)
        self.pl_track_model.set_rows(tracks)

        count = len(tracks)
        total_dur = sum(t["duration"] for t in tracks if t["duration"])
        total_size = sum(f.stat().st_size for f in p_dir.glob("*.mp3")) if p_dir.exists() else 0

        cov_path = str(p_dir / "cover.jpg") if (p_dir / "cover.jpg").exists() else ""
        self.pl_detail_cover.setPixmap(get_cover_pixmap(cov_path, 130))

        dur_text = f"{int(total_dur // 60)} Min {int(total_dur % 60)} Sek" if total_dur > 0 else "0 Min"
        self.pl_detail_meta.setText(f"{count} Songs · {dur_text} · {format_size(total_size)}")
        self.pl_stack.setCurrentIndex(1)

    def _play_all_playlist(self):
        if self.pl_track_model.rows:
            self.play(self.pl_track_model.rows[0], 0, self.pl_track_model.rows)

    def _open_playlist_dir(self):
        if hasattr(self, "selected_playlist_name") and self.selected_playlist_name:
            p_dir = self.music_root / safe_name(self.selected_playlist_name, "playlist")
            p_dir.mkdir(parents=True, exist_ok=True)
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(p_dir)))

    def _sync_current_playlist(self):
        if not hasattr(self, "selected_playlist_name") or not self.selected_playlist_name:
            return
        name = self.selected_playlist_name
        added, removed = self.db.sync_library(self.music_root)
        self.refresh_library()
        self.refresh_playlists()
        self._open_playlist_detail(name)
        QMessageBox.information(self, "Playlist synchronisiert",
                                f"Playlist '{name}' abgeglichen:\n+ {added} neu importiert\n- {removed} bereinigt.")

    def new_playlist(self):
        name, ok = QInputDialog.getText(self, "Neue Playlist", "Playlist-Name:")
        if ok and name.strip():
            self.db.create_playlist(name.strip())
            self.refresh_playlists()
            self.refresh_dashboard()

    def delete_current_playlist(self):
        name = getattr(self, "selected_playlist_name", "")
        if not name:
            item = self.pl_cards.currentItem()
            name = item.data(Qt.UserRole) if item else ""
        if not name:
            QMessageBox.information(self, "Keine Auswahl", "Bitte wähle eine Playlist aus.")
            return
        ret = QMessageBox.question(
            self, "Playlist löschen",
            f"Möchtest du die Playlist '{name}' und den gesamten zugehörigen Ordner von der Festplatte löschen?",
            QMessageBox.Yes | QMessageBox.No
        )
        if ret == QMessageBox.Yes:
            self.db.delete_playlist(name, self.music_root)
            self.pl_track_model.set_rows([])
            self.pl_stack.setCurrentIndex(0)
            self.refresh_playlists()
            self.refresh_library()
            self.refresh_dashboard()

    def play(self, track, index: int | None = None, model: list | None = None):
        self.active_rows = model or self.lib_model.rows
        self.current_idx = index if index is not None else (
            self.active_rows.index(track) if track in self.active_rows else 0
        )
        self.current_track = track

        t_title = track["title"] if hasattr(track, "keys") else (track.get("title", "") if isinstance(track, dict) else getattr(track, "title", ""))
        t_artist = track["artist"] if hasattr(track, "keys") else (track.get("artist", "") if isinstance(track, dict) else getattr(track, "artist", ""))
        f_path = track["file_path"] if hasattr(track, "keys") else (track.get("file_path", "") if isinstance(track, dict) else getattr(track, "file_path", ""))
        coll = track["collection"] if hasattr(track, "keys") and "collection" in track.keys() else getattr(track, "collection", "")
        fav = track["favorite"] if hasattr(track, "keys") and "favorite" in track.keys() else getattr(track, "favorite", 0)
        t_id = track["id"] if hasattr(track, "keys") and "id" in track.keys() else getattr(track, "id", None)

        if not t_title and f_path:
            t_title = Path(f_path).stem
        if not t_artist:
            t_artist = "Unbekannter Interpret"

        if t_id:
            self.db.increment_play_count(t_id)

        self.now_title.setText(t_title or "Unbekannter Titel")
        self.now_artist.setText(t_artist)
        self.bar_cover.setPixmap(get_cover_pixmap(f_path, 56))
        
        bitrate = track["bitrate"] if hasattr(track, "keys") and "bitrate" in track.keys() else getattr(track, "bitrate", 320)
        br = int(bitrate) if bitrate else 320
        self.now_audio_info.setText(f"{br} kbps | MP3")
        self.now_audio_info.show()

        if hasattr(self, "bar_fav_btn"):
            self.bar_fav_btn.setIcon(get_icon("heart-filled" if fav else "heart"))

        self._update_sidebar_mini_card(track)

        if coll and coll not in ("Einzeltitel", "Single") and hasattr(self, "bar_pl_badge"):
            self.bar_pl_badge.setText(coll)
            self.bar_pl_badge.show()
            self.current_playlist_name = coll
        elif hasattr(self, "bar_pl_badge"):
            self.bar_pl_badge.hide()
            self.current_playlist_name = ""

        if hasattr(self, "details_panel") and self.details_panel.isVisible():
            self.show_track_details(track)

        if not f_path or not Path(f_path).is_file():
            self.play_btn.setIcon(get_icon("play"))
            return

        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(str(Path(f_path).resolve())))
        self.player.play()
        self.play_btn.setIcon(get_icon("pause"))

        if hasattr(self, "mini_player"):
            self.mini_player.update_track(track)
            self.mini_player.set_playing(True)

        self._load_recommendations_for_track(track)

    def _toggle_current_fav(self):
        if not self.current_track:
            return
        t_id = self.current_track["id"] if hasattr(self.current_track, "keys") else getattr(self.current_track, "id", None)
        if t_id:
            self.db.toggle_favorite(t_id)
            updated = [t for t in self.db.tracks() if t["id"] == t_id]
            if updated:
                self.current_track = updated[0]
                is_fav = bool(self.current_track["favorite"])
                if hasattr(self, "bar_fav_btn"):
                    self.bar_fav_btn.setIcon(get_icon("heart-filled" if is_fav else "heart"))
                if hasattr(self, "sb_fav_btn"):
                    self.sb_fav_btn.setIcon(get_icon("heart-filled" if is_fav else "heart"))
                self._update_sidebar_mini_card(self.current_track)
            self.refresh_library()
            self.refresh_dashboard()

    def _open_current_folder(self):
        if not self.current_track:
            return
        fp = self.current_track["file_path"] if hasattr(self.current_track, "keys") else getattr(self.current_track, "file_path", "")
        if fp and Path(fp).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(fp).parent)))

    def _jump_to_current_playlist(self):
        if self.current_playlist_name:
            self.nav.setCurrentRow(4)
            self._open_playlist_detail(self.current_playlist_name)

    def _toggle_mute(self):
        cur_vol = int(self.audio.volume() * 100)
        if cur_vol > 0:
            self.prev_volume = self.audio.volume()
            self.vol_slider.setValue(0)
        else:
            restore_val = int(self.prev_volume * 100) if self.prev_volume > 0 else 75
            self.vol_slider.setValue(restore_val)

    def _on_volume_changed(self, val: int):
        self.audio.setVolume(val / 100.0)
        self.db.set_setting("volume", str(val))
        if val == 0:
            self.vol_btn.setIcon(get_icon("volume-mute"))
        else:
            self.vol_btn.setIcon(get_icon("volume"))

    def toggle_play(self):
        if self.player.playbackState() == QMediaPlayer.PlayingState:
            self.player.pause()
            self.play_btn.setIcon(get_icon("play"))
            if hasattr(self, "mini_player"):
                self.mini_player.set_playing(False)
        else:
            self.player.play()
            self.play_btn.setIcon(get_icon("pause"))
            if hasattr(self, "mini_player"):
                self.mini_player.set_playing(True)

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
        self.db.set_setting("shuffle", "1" if self.is_shuffle else "0")

    def toggle_repeat(self):
        self.is_repeat = not self.is_repeat
        self.repeat_btn.setStyleSheet("color: #3DDC63;" if self.is_repeat else "")
        self.db.set_setting("repeat", "1" if self.is_repeat else "0")

    def _on_media_status(self, status):
        if status == QMediaPlayer.EndOfMedia:
            # Prevent infinite skipping if a file failed decoding immediately
            if self.player.position() < 500 and self.player.duration() > 3000:
                self.play_btn.setIcon(get_icon("play"))
                return
            if self.is_repeat:
                self.player.setPosition(0)
                self.player.play()
            else:
                self.skip(1)

    def _on_position_changed(self, pos):
        self.timeline_slider.setValue(pos)
        self.time_cur.setText(time_text(pos / 1000))
        if hasattr(self, "mini_player") and self.mini_player.isVisible():
            self.mini_player.update_position(pos, self.player.duration())

    def _on_duration_changed(self, dur):
        self.timeline_slider.setMaximum(dur)
        self.time_total.setText(time_text(dur / 1000))
        if hasattr(self, "mini_player") and self.mini_player.isVisible():
            self.mini_player.update_position(self.player.position(), dur)

    def context_menu(self, table: QTableView, model: TrackModel, point):
        idx = table.indexAt(point)
        if not idx.isValid():
            return
        track = model.rows[idx.row()]
        file_path = Path(track["file_path"])
        menu = QMenu(self)

        menu.addAction(get_icon("play"), "Abspielen", lambda: self.play(track, idx.row(), model.rows))

        pl_menu = menu.addMenu(get_icon("playlist"), "Zu Playlist hinzufügen …")
        for pl_name in self.db.playlist_names():
            pl_menu.addAction(get_icon("playlist"), pl_name, lambda n=pl_name, tid=track["id"]: (
                self.db.add_to_playlist(n, tid),
                self.notify("Playlist", f"Song zu '{n}' hinzugefügt.")
            ))

        menu.addAction(get_icon("folder"), "Im Datei-Explorer anzeigen", lambda: self._show_in_explorer(file_path))

        menu.addSeparator()
        menu.addAction(get_icon("tag"), "Details anzeigen", lambda: self.show_track_details(track))
        menu.addAction(get_icon("heart"), "Favorit umschalten", lambda: (self.db.toggle_favorite(track["id"]), self.refresh_library()))
        menu.addAction(get_icon("edit"), "Tags bearbeiten", lambda: self._edit_tags(track))
        menu.addAction(get_icon("zap"), "Tags bereinigen (Auto-Clean)", lambda: self.clean_single_track(track))
        menu.addAction(get_icon("covers"), "Albumcover aktualisieren", lambda: self._refresh_single_cover(track))

        menu.addSeparator()
        menu.addAction(get_icon("trash"), "Löschen", lambda: self._prompt_delete_track(track))

        menu.exec(table.viewport().mapToGlobal(point))

    def _prompt_delete_track(self, track):
        dlg = DeleteTrackDialog(track["title"], count=1, parent=self)
        if dlg.exec():
            delete_file = (dlg.choice == "disk")
            self.db.delete_track(track["id"], delete_file=delete_file)
            if hasattr(self, "selected_detail_track") and self.selected_detail_track and self.selected_detail_track.get("id") == track["id"]:
                self.details_panel.hide()
            self.refresh_library()
            self.refresh_dashboard()

    def _refresh_single_cover(self, track):
        file_path = Path(track["file_path"])
        if not file_path.is_file():
            QMessageBox.warning(self, "Datei fehlt", f"Die Datei {file_path.name} wurde nicht gefunden.")
            return

        from cover_enricher import CoverEnricher
        enricher = CoverEnricher()
        src_url = track["source_url"] if "source_url" in track.keys() else getattr(track, "source_url", "")
        ok = enricher.enrich_file(file_path, force=True, music_root=self.music_root, source_url=src_url)
        if ok:
            get_cover_pixmap.cache_clear()
            self.refresh_library()
            if self.current_track and self.current_track.get("id") == track["id"]:
                self.bar_cover.setPixmap(get_cover_pixmap(str(file_path), 48))
            if hasattr(self, "selected_detail_track") and self.selected_detail_track and self.selected_detail_track.get("id") == track["id"]:
                self.show_track_details(track)
            QMessageBox.information(self, "Cover aktualisiert", f"Neues Cover für '{track['title']}' erfolgreich eingebettet!")
        else:
            QMessageBox.information(self, "Kein Cover gefunden", f"Für '{track['title']}' konnte online kein neues Cover gefunden werden.")

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
        new_settings = {
            "music_folder": str(self.music_root),
            "quality": self.quality.currentText(),
            "parallel": self.parallel.currentText(),
            "auto_cover": "1" if self.chk_auto_cover.isChecked() else "0",
            "auto_metadata": "1" if self.chk_auto_meta.isChecked() else "0",
            "only_new": "1" if self.chk_only_new.isChecked() else "0",
            "cleanup_missing_startup": "1" if self.chk_cleanup_startup.isChecked() else "0",
            "auto_sync_playlist": "1" if self.chk_auto_sync_pl.isChecked() else "0",
        }
        self.settings.update(new_settings)
        self.db.save_settings_dict(new_settings)
        self.pool.setMaxThreadCount(int(self.parallel.currentText()))
        self.refresh_dashboard()
        QMessageBox.information(self, "Gespeichert", "Einstellungen erfolgreich gespeichert.")

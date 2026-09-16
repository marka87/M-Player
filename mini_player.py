"""Compact, Always-on-Top floating Mini-Player window for M-Player."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QIcon, QPainter, QPainterPath
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPushButton, QSlider,
                             QVBoxLayout, QWidget)

from metadata import safe_name


class MiniPlayerWindow(QWidget):
    """A frameless, draggable, always-on-top compact music controller."""

    def __init__(self, main_win):
        super().__init__(None)
        self.main_win = main_win

        self.setWindowFlags(
            Qt.Window |
            Qt.WindowStaysOnTopHint |
            Qt.FramelessWindowHint |
            Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(340, 88)

        self._drag_pos = QPoint()
        self._build_ui()

    def _build_ui(self):
        container = QFrame(self)
        container.setObjectName("miniPlayerFrame")
        container.setFixedSize(340, 88)
        container.setStyleSheet("""
            QFrame#miniPlayerFrame {
                background-color: rgba(22, 26, 32, 0.96);
                border: 1px solid #3DDC63;
                border-radius: 12px;
            }
            QLabel {
                color: #FFFFFF;
            }
            QLabel#secondary {
                color: #A0A6AD;
            }
            QPushButton {
                background: transparent;
                border: none;
                border-radius: 4px;
                color: #E0E0E0;
            }
            QPushButton:hover {
                background-color: #222933;
                color: #3DDC63;
            }
            QSlider::groove:horizontal {
                height: 3px;
                background: #262E38;
                border-radius: 1px;
            }
            QSlider::sub-page:horizontal {
                background: #3DDC63;
                border-radius: 1px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 8px;
                height: 8px;
                margin: -3px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal:hover {
                background: #3DDC63;
            }
        """)

        layout = QHBoxLayout(container)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        # 1. Album Cover
        self.cover_lbl = QLabel()
        self.cover_lbl.setFixedSize(48, 48)
        self.cover_lbl.setScaledContents(True)
        layout.addWidget(self.cover_lbl)

        # 2. Middle info: Title, Artist, Timeline
        mid_layout = QVBoxLayout()
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(3)
        mid_layout.setAlignment(Qt.AlignVCenter)

        self.title_lbl = QLabel("Kein Song")
        self.title_lbl.setStyleSheet("font-size: 12px; font-weight: 700;")

        self.artist_lbl = QLabel("Bereit")
        self.artist_lbl.setObjectName("secondary")
        self.artist_lbl.setStyleSheet("font-size: 10px;")

        self.progress_slider = QSlider(Qt.Horizontal)
        self.progress_slider.setRange(0, 1000)
        self.progress_slider.setValue(0)
        self.progress_slider.sliderMoved.connect(self._on_seek)

        mid_layout.addWidget(self.title_lbl)
        mid_layout.addWidget(self.artist_lbl)
        mid_layout.addWidget(self.progress_slider)
        layout.addLayout(mid_layout, 1)

        # 3. Right control cluster: Top action (restore), Bottom controls
        right_layout = QVBoxLayout()
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(4)
        right_layout.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        # Window controls: Restore, Close
        win_ctrls = QHBoxLayout()
        win_ctrls.setSpacing(4)
        win_ctrls.setAlignment(Qt.AlignRight)

        restore_btn = QPushButton("⤢")
        restore_btn.setFixedSize(20, 20)
        restore_btn.setToolTip("Hauptfenster wiederherstellen")
        restore_btn.clicked.connect(self.restore_main_window)

        close_btn = QPushButton("✕")
        close_btn.setFixedSize(20, 20)
        close_btn.setToolTip("Schließen")
        close_btn.clicked.connect(self.restore_main_window)

        win_ctrls.addWidget(restore_btn)
        win_ctrls.addWidget(close_btn)
        right_layout.addLayout(win_ctrls)

        # Playback controls: Prev, Play, Next
        play_ctrls = QHBoxLayout()
        play_ctrls.setSpacing(4)
        play_ctrls.setAlignment(Qt.AlignRight)

        self.prev_btn = QPushButton()
        self.prev_btn.setFixedSize(24, 24)
        from ui import get_icon
        self.prev_btn.setIcon(get_icon("previous"))
        self.prev_btn.clicked.connect(lambda: self.main_win.skip(-1))

        self.play_btn = QPushButton()
        self.play_btn.setFixedSize(28, 28)
        self.play_btn.setIcon(get_icon("play"))
        self.play_btn.setStyleSheet("background-color: #3DDC63; border-radius: 14px; color: #121212;")
        self.play_btn.clicked.connect(self.main_win.toggle_play)

        self.next_btn = QPushButton()
        self.next_btn.setFixedSize(24, 24)
        self.next_btn.setIcon(get_icon("next"))
        self.next_btn.clicked.connect(lambda: self.main_win.skip(1))

        play_ctrls.addWidget(self.prev_btn)
        play_ctrls.addWidget(self.play_btn)
        play_ctrls.addWidget(self.next_btn)
        right_layout.addLayout(play_ctrls)

        layout.addLayout(right_layout)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            self._drag_pos = pos - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.LeftButton and hasattr(self, "_drag_pos"):
            pos = event.globalPosition().toPoint() if hasattr(event, "globalPosition") else event.globalPos()
            self.move(pos - self._drag_pos)
            event.accept()

    def mouseDoubleClickEvent(self, event):
        self.restore_main_window()

    def restore_main_window(self):
        self.hide()
        self.main_win.showNormal()
        self.main_win.activateWindow()

    def update_track(self, track):
        if not track:
            self.title_lbl.setText("Kein Song")
            self.artist_lbl.setText("Bereit")
            from ui import get_cover_pixmap
            self.cover_lbl.setPixmap(get_cover_pixmap("", 48))
            return

        t_title = track["title"] if hasattr(track, "keys") else (track.get("title", "") if isinstance(track, dict) else getattr(track, "title", ""))
        t_artist = track["artist"] if hasattr(track, "keys") else (track.get("artist", "") if isinstance(track, dict) else getattr(track, "artist", ""))
        f_path = track["file_path"] if hasattr(track, "keys") else (track.get("file_path", "") if isinstance(track, dict) else getattr(track, "file_path", ""))

        from pathlib import Path
        if not t_title and f_path:
            t_title = Path(f_path).stem
        if not t_artist:
            t_artist = "Unbekannter Interpret"

        fm = QFontMetrics(self.title_lbl.font())
        elided_title = fm.elidedText(t_title, Qt.ElideRight, 150)
        self.title_lbl.setText(elided_title)

        fm_a = QFontMetrics(self.artist_lbl.font())
        elided_artist = fm_a.elidedText(t_artist, Qt.ElideRight, 150)
        self.artist_lbl.setText(elided_artist)

        from ui import get_cover_pixmap
        self.cover_lbl.setPixmap(get_cover_pixmap(f_path, 48))

    def update_position(self, pos_ms: int, dur_ms: int):
        if dur_ms > 0:
            val = int((pos_ms / dur_ms) * 1000)
            self.progress_slider.blockSignals(True)
            self.progress_slider.setValue(val)
            self.progress_slider.blockSignals(False)

    def set_playing(self, is_playing: bool):
        from ui import get_icon
        self.play_btn.setIcon(get_icon("pause" if is_playing else "play"))

    def _on_seek(self, value: int):
        dur = self.main_win.player.duration()
        if dur > 0:
            target_ms = int((value / 1000.0) * dur)
            self.main_win.player.setPosition(target_ms)

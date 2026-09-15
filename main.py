from pathlib import Path

from PySide6.QtWidgets import QApplication

from database import MusicDatabase
from ui import MusicWindow


if __name__ == "__main__":
    base = Path(__file__).resolve().parent
    app = QApplication([])
    app.setStyleSheet((base / "style.qss").read_text(encoding="utf-8"))
    window = MusicWindow(MusicDatabase(base / "music_library.db"), base / "Music")
    window.show()
    app.exec()

from pathlib import Path
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from database import MusicDatabase
from ui import MusicWindow


if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mplayer.musicapp.app.1.0")
        except Exception:
            pass

    base = Path(__file__).resolve().parent
    app = QApplication([])
    ico_path = base / "assets" / "icon.ico"
    if ico_path.exists():
        app.setWindowIcon(QIcon(str(ico_path)))
    app.setStyleSheet((base / "style.qss").read_text(encoding="utf-8"))
    window = MusicWindow(MusicDatabase(base / "music_library.db"), base / "Music")
    window.show()
    app.exec()

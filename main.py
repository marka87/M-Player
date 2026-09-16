from pathlib import Path
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from database import MusicDatabase
from ui import MusicWindow

__version__ = "v1.0.0"

if __name__ == "__main__":
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mplayer.musicapp.app.1.0")
        except Exception:
            pass

    base = Path(__file__).resolve().parent

    import time
    import traceback

    def excepthook(exc_type, exc_val, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        try:
            log_file = base / "crash.log"
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Uncaught Exception:\n{msg}\n")
        except Exception:
            pass
        sys.__excepthook__(exc_type, exc_val, exc_tb)

    sys.excepthook = excepthook

    app = QApplication([])
    
    from PySide6.QtGui import QPixmap, QPainter, QColor
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QSplashScreen

    pix = QPixmap(400, 300)
    pix.fill(QColor("#12161A"))
    painter = QPainter(pix)
    logo_path = base / "assets" / "logo.svg"
    if logo_path.exists():
        logo = QIcon(str(logo_path)).pixmap(100, 100)
        painter.drawPixmap(150, 80, logo)
    painter.setPen(QColor("#F4F4F4"))
    font = painter.font()
    font.setPixelSize(22)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pix.rect().adjusted(0, 0, 0, -60), Qt.AlignBottom | Qt.AlignHCenter, "M-Player")
    painter.end()

    splash = QSplashScreen(pix, Qt.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()

    ico_path = base / "assets" / "icon.ico"
    if ico_path.exists():
        app.setWindowIcon(QIcon(str(ico_path)))
    
    db = MusicDatabase(base / "music_library.db")
    theme_path = base / "assets" / "themes" / "dark.qss"
    if theme_path.exists():
        app.setStyleSheet(theme_path.read_text(encoding="utf-8"))
    
    window = MusicWindow(db, base / "Music")
    QTimer.singleShot(1000, lambda: (window.show(), splash.finish(window)))
    
    app.exec()

"""Build script for creating an all-in-one portable Windows distribution of M-Player."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
PORTABLE_DIR = DIST_DIR / "M-Player-Portable"
VERSION = "v1.0.1"


def find_tool(tool_name: str) -> Path | None:
    """Find a binary in PATH or common WinGet installation locations."""
    found = shutil.which(tool_name)
    if found and Path(found).is_file():
        return Path(found)

    winget_root = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    if winget_root.is_dir():
        for cand in winget_root.glob(f"**/{tool_name}.exe"):
            if cand.is_file():
                return cand
        for cand in winget_root.glob(f"**/{tool_name}"):
            if cand.is_file():
                return cand
    return None


def clean_previous_builds():
    """Remove previous build and dist directories."""
    print("[1/5] Bereinige alte Build-Artefakte ...")
    for d in (PORTABLE_DIR, BUILD_DIR):
        if d.exists():
            try:
                shutil.rmtree(d)
                print(f"  - Geloescht: {d}")
            except Exception as err:
                print(f"  ! Warnung: Konnte {d} nicht vollstaendig loeschen: {err}")


def run_pyinstaller():
    """Run PyInstaller with optimized settings for PySide6 M-Player."""
    exe_file = PORTABLE_DIR / "M-Player.exe"
    if exe_file.is_file() and "--skip-compile" in sys.argv:
        print("[2/5] Ueberspringe Kompilierung (--skip-compile aktiv).")
        return

    print("[2/5] Baue M-Player.exe mit PyInstaller ...")
    import PyInstaller.__main__

    icon_path = BASE_DIR / "assets" / "icon.ico"
    assets_src = BASE_DIR / "assets"

    pyinstaller_args = [
        str(BASE_DIR / "main.py"),
        "--name=M-Player",
        "--noconsole",
        "--onedir",
        "--clean",
        f"--distpath={DIST_DIR}",
        f"--workpath={BUILD_DIR}",
        f"--icon={icon_path}",
        f"--add-data={assets_src}{os.pathsep}assets",
        "--hidden-import=PySide6.QtMultimedia",
        "--hidden-import=PySide6.QtSvg",
        "--hidden-import=PySide6.QtNetwork",
        "--hidden-import=mutagen",
        "--hidden-import=mutagen.id3",
        "--hidden-import=mutagen.mp3",
        "--hidden-import=mutagen.easyid3",
        "--hidden-import=yt_dlp",
        "--hidden-import=spotipy",
        "--hidden-import=requests",
        "--hidden-import=urllib.request",
        "--hidden-import=urllib.parse",
        "--hidden-import=sqlite3",
        "--noconfirm",
    ]

    PyInstaller.__main__.run(pyinstaller_args)

    # Rename dist/M-Player to dist/M-Player-Portable if needed
    default_out = DIST_DIR / "M-Player"
    if default_out.is_dir() and default_out != PORTABLE_DIR:
        if PORTABLE_DIR.exists():
            shutil.rmtree(PORTABLE_DIR)
        default_out.rename(PORTABLE_DIR)

    if not (PORTABLE_DIR / "M-Player.exe").is_file():
        raise RuntimeError("M-Player.exe wurde nicht erfolgreich erstellt!")
    print("  [OK] M-Player.exe erfolgreich kompiliert.")


def bundle_assets_and_tools():
    """Bundle assets, ffmpeg, ffprobe, and deno into the portable directory."""
    print("[3/5] Buendle externe Tools und Assets ...")
    bin_dir = PORTABLE_DIR / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    # Copy external binaries: ffmpeg, ffprobe, deno
    tools_to_copy = ["ffmpeg", "ffprobe", "deno"]
    for tool in tools_to_copy:
        tool_exe = find_tool(tool)
        if tool_exe and tool_exe.is_file():
            dst = bin_dir / f"{tool}.exe"
            shutil.copy2(tool_exe, dst)
            print(f"  [OK] {tool}.exe kopiert ({tool_exe.stat().st_size // (1024 * 1024)} MB)")
        else:
            print(f"  ! Hinweis: {tool}.exe nicht im System gefunden (wird im Portable-Paket uebersprungen)")

    # Ensure assets directory is present and complete
    assets_dest = PORTABLE_DIR / "assets"
    if not assets_dest.exists():
        shutil.copytree(BASE_DIR / "assets", assets_dest)
        print("  [OK] assets/ Verzeichnis vollstaendig kopiert.")
    else:
        # Update / verify themes and icons
        for sub in ("icons", "themes"):
            src_sub = BASE_DIR / "assets" / sub
            dst_sub = assets_dest / sub
            if src_sub.exists() and not dst_sub.exists():
                shutil.copytree(src_sub, dst_sub)
        # Ensure icon.ico is copied
        if (BASE_DIR / "assets" / "icon.ico").is_file():
            shutil.copy2(BASE_DIR / "assets" / "icon.ico", assets_dest / "icon.ico")
        print("  [OK] assets/ Verzeichnis aktualisiert.")

    # Write README_PORTABLE.txt
    readme_path = PORTABLE_DIR / "README_PORTABLE.txt"
    readme_content = f"""====================================================
M-Player — Portable Edition {VERSION}
Offline Music Manager & YouTube Downloader
====================================================

Starten:
  Doppelklick auf 'M-Player.exe'.

Portabilitaet:
  - Vollstaendig portabel: Kann direkt vom USB-Stick oder
    aus jedem beliebigen Ordner gestartet werden.
  - Alle Daten, Playlists und Einstellungen werden lokal
    in 'music_library.db' im selben Ordner gespeichert.
  - Heruntergeladene Musik wird standardmaessig im Ordner
    'Music/' direkt neben der .exe abgelegt.
  - Integrierte Tools (FFmpeg, ffprobe) liegen im 'bin/'-Ordner.
    Es muss keinerlei Software oder Python installiert werden!

Viel Spass mit deiner Musik!
====================================================
"""
    readme_path.write_text(readme_content, encoding="utf-8")
    print("  [OK] README_PORTABLE.txt erstellt.")


def create_portable_zip():
    """Create a clean .zip distribution archive."""
    print("[4/5] Erstelle komprimiertes ZIP-Archiv ...")
    zip_path = DIST_DIR / f"M-Player-Portable-{VERSION}.zip"
    if zip_path.exists():
        zip_path.unlink()

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for file in PORTABLE_DIR.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(DIST_DIR)
                zf.write(file, arcname)

    zip_size_mb = zip_path.stat().st_size / (1024 * 1024)
    print(f"  [OK] {zip_path.name} erstellt ({zip_size_mb:.1f} MB).")
    return zip_path


def main():
    start_time = time.time()
    print("====================================================")
    print("   M-Player Portable Windows Build-System")
    print("====================================================")

    if "--skip-compile" not in sys.argv:
        clean_previous_builds()
    run_pyinstaller()
    bundle_assets_and_tools()
    zip_file = create_portable_zip()

    elapsed = time.time() - start_time
    print("[5/5] Fertig!")
    print("====================================================")
    print(f"Build erfolgreich abgeschlossen in {elapsed:.1f} Sekunden!")
    print(f"Ordner: {PORTABLE_DIR}")
    print(f"Archiv: {zip_file}")
    print("====================================================")


if __name__ == "__main__":
    main()


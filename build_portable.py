"""Cross-platform build script for creating standalone portable distributions of M-Player (Windows & Linux)."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

# Ensure UTF-8 output on consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

BASE_DIR = Path(__file__).resolve().parent
DIST_DIR = BASE_DIR / "dist"
BUILD_DIR = BASE_DIR / "build"
VERSION = "v1.0.2"

IS_WINDOWS = sys.platform == "win32"
EXE_NAME = "M-Player.exe" if IS_WINDOWS else "M-Player"
PORTABLE_DIR = DIST_DIR / ("M-Player-Portable" if IS_WINDOWS else "M-Player-Linux")


def find_tool(tool_name: str) -> Path | None:
    """Find a binary in PATH or common WinGet installation locations."""
    # Check direct name first (or .exe on Windows)
    cand_names = [f"{tool_name}.exe", tool_name] if IS_WINDOWS else [tool_name]
    for name in cand_names:
        found = shutil.which(name)
        if found and Path(found).is_file():
            return Path(found)

    if IS_WINDOWS:
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
    exe_file = PORTABLE_DIR / EXE_NAME
    if exe_file.is_file() and "--skip-compile" in sys.argv:
        print("[2/5] Ueberspringe Kompilierung (--skip-compile aktiv).")
        return

    print(f"[2/5] Baue {EXE_NAME} mit PyInstaller ({sys.platform}) ...")
    import PyInstaller.__main__

    icon_path = BASE_DIR / "assets" / ("icon.ico" if IS_WINDOWS else "icon.png")
    if not icon_path.is_file():
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

    # Rename dist/M-Player to target portable dir if needed
    default_out = DIST_DIR / "M-Player"
    if default_out.is_dir() and default_out != PORTABLE_DIR:
        if PORTABLE_DIR.exists():
            shutil.rmtree(PORTABLE_DIR)
        default_out.rename(PORTABLE_DIR)

    bin_path = PORTABLE_DIR / EXE_NAME
    if not bin_path.is_file():
        raise RuntimeError(f"{EXE_NAME} wurde nicht erfolgreich erstellt!")

    if not IS_WINDOWS:
        current_mode = bin_path.stat().st_mode
        bin_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    print(f"  [OK] {EXE_NAME} erfolgreich kompiliert.")


def bundle_assets_and_tools():
    """Bundle assets, tools, launcher, and desktop integration."""
    print("[3/5] Buendle externe Tools, Assets und Starter ...")
    bin_dir = PORTABLE_DIR / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    # Copy external binaries: ffmpeg, ffprobe, deno
    tools_to_copy = ["ffmpeg", "ffprobe", "deno"]
    for tool in tools_to_copy:
        tool_bin = find_tool(tool)
        if tool_bin and tool_bin.is_file():
            dst_name = f"{tool}.exe" if IS_WINDOWS else tool
            dst = bin_dir / dst_name
            shutil.copy2(tool_bin, dst)
            if not IS_WINDOWS:
                dst.chmod(dst.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            print(f"  [OK] {dst_name} kopiert ({tool_bin.stat().st_size // (1024 * 1024)} MB)")
        else:
            print(f"  ! Hinweis: {tool} nicht im System gefunden (wird im Portable-Paket uebersprungen)")

    # Ensure assets directory is present and complete
    assets_dest = PORTABLE_DIR / "assets"
    if not assets_dest.exists():
        shutil.copytree(BASE_DIR / "assets", assets_dest)
        print("  [OK] assets/ Verzeichnis vollstaendig kopiert.")
    else:
        for sub in ("icons", "themes"):
            src_sub = BASE_DIR / "assets" / sub
            dst_sub = assets_dest / sub
            if src_sub.exists() and not dst_sub.exists():
                shutil.copytree(src_sub, dst_sub)
        for icon_file in ("icon.ico", "icon.png", "logo.svg"):
            src_icon = BASE_DIR / "assets" / icon_file
            if src_icon.is_file():
                shutil.copy2(src_icon, assets_dest / icon_file)
        print("  [OK] assets/ Verzeichnis aktualisiert.")

    # Linux-specific integrations
    if not IS_WINDOWS:
        # 1. Launcher script: run.sh
        run_sh = PORTABLE_DIR / "run.sh"
        run_sh_content = """#!/usr/bin/env bash
set -e
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export PATH="$HERE/bin:$PATH"
exec "$HERE/M-Player" "$@"
"""
        run_sh.write_text(run_sh_content, encoding="utf-8")
        run_sh.chmod(run_sh.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        print("  [OK] Linux-Launcher 'run.sh' erstellt.")

        # 2. Desktop file
        desktop_file = PORTABLE_DIR / "M-Player.desktop"
        desktop_content = """[Desktop Entry]
Type=Application
Name=M-Player
GenericName=Music Player
Comment=Offline Music Manager & YouTube Downloader
Exec=sh -c '"$(dirname "%k")/run.sh"'
Icon=icon
Terminal=false
Categories=AudioVideo;Audio;Player;Qt;
"""
        desktop_file.write_text(desktop_content, encoding="utf-8")
        print("  [OK] 'M-Player.desktop' Datei erstellt.")

        # 3. Copy icon.png to root of bundle for desktop managers
        src_png = BASE_DIR / "assets" / "icon.png"
        if src_png.is_file():
            shutil.copy2(src_png, PORTABLE_DIR / "icon.png")

    # Readme file
    readme_name = "README_PORTABLE.txt" if IS_WINDOWS else "README_LINUX.txt"
    readme_path = PORTABLE_DIR / readme_name
    if IS_WINDOWS:
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
    else:
        readme_content = f"""====================================================
M-Player — Linux Portable Edition {VERSION}
Offline Music Manager & YouTube Downloader
====================================================

Starten:
  Ausfuehren von './run.sh' oder './M-Player' im Terminal
  oder Doppelklick auf 'run.sh' / 'M-Player.desktop'.

Portabilitaet:
  - Vollstaendig portabel: Laeuft unabhaengig von systemweiten
    Python-Paketen auf modernen Linux-Distributionen (Ubuntu, Debian, Fedora, Arch, etc.).
  - Daten und Einstellungen werden in 'music_library.db'
    direkt im Anwendungsverzeichnis gespeichert.
  - Musik wird standardmaessig im Unterordner 'Music/' gespeichert.
  - FFmpeg / ffprobe im 'bin/'-Ordner (oder aus System-PATH)
    werden automatisch verwendet.

Viel Spass mit deiner Musik!
====================================================
"""
    readme_path.write_text(readme_content, encoding="utf-8")
    print(f"  [OK] {readme_name} erstellt.")


def create_portable_archive() -> Path:
    """Create a clean distribution archive (.zip on Windows, .tar.gz on Linux)."""
    print("[4/5] Erstelle komprimiertes Distributions-Archiv ...")

    if IS_WINDOWS:
        archive_path = DIST_DIR / f"M-Player-Portable-{VERSION}.zip"
        if archive_path.exists():
            archive_path.unlink()

        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            for file in PORTABLE_DIR.rglob("*"):
                if file.is_file():
                    arcname = file.relative_to(DIST_DIR)
                    zf.write(file, arcname)
    else:
        archive_path = DIST_DIR / f"M-Player-Linux-{VERSION}.tar.gz"
        if archive_path.exists():
            archive_path.unlink()

        with tarfile.open(archive_path, "w:gz") as tar:
            tar.add(PORTABLE_DIR, arcname=PORTABLE_DIR.name)

    size_mb = archive_path.stat().st_size / (1024 * 1024)
    print(f"  [OK] {archive_path.name} erstellt ({size_mb:.1f} MB).")
    return archive_path


def main():
    start_time = time.time()
    os_label = "Windows" if IS_WINDOWS else "Linux"
    print("====================================================")
    print(f"   M-Player Portable {os_label} Build-System")
    print("====================================================")

    if "--skip-compile" not in sys.argv:
        clean_previous_builds()
    run_pyinstaller()
    bundle_assets_and_tools()
    archive = create_portable_archive()

    elapsed = time.time() - start_time
    print("[5/5] Fertig!")
    print("====================================================")
    print(f"Build erfolgreich abgeschlossen in {elapsed:.1f} Sekunden!")
    print(f"Ordner: {PORTABLE_DIR}")
    print(f"Archiv: {archive}")
    print("====================================================")


if __name__ == "__main__":
    main()

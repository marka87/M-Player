#!/usr/bin/env bash
set -e

# ==============================================================================
# M-Player Linux Build & Packaging Script
# Produces:
#   1. dist/M-Player-Linux-vX.X.X.tar.gz (Portable Linux Bundle)
#   2. dist/M-Player-vX.X.X-x86_64.AppImage (Single-file AppImage)
# ==============================================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$BASE_DIR"

VERSION=$(grep -o '__version__ = "[^"]*"' src/__init__.py 2>/dev/null | cut -d'"' -f2 || echo "v1.0.2")
DIST_DIR="$BASE_DIR/dist"
BUILD_DIR="$BASE_DIR/build"
APPDIR="$BUILD_DIR/AppDir"

echo "===================================================="
echo "   M-Player Linux Build-System ($VERSION)"
echo "===================================================="

# 1. Detect Python executable
PYTHON="python"
if ! command -v python >/dev/null 2>&1; then
    if command -v python3 >/dev/null 2>&1; then
        PYTHON="python3"
    elif [ -x ".venv/bin/python" ]; then
        PYTHON=".venv/bin/python"
    fi
fi

echo "[1/4] Starte PyInstaller und Portable Tarball Build via $PYTHON ..."
$PYTHON "$SCRIPT_DIR/build_portable.py" "$@"

LINUX_DIST="$DIST_DIR/M-Player-Linux"
if [ ! -d "$LINUX_DIST" ]; then
    echo "FEHLER: $LINUX_DIST wurde nicht erzeugt!"
    exit 1
fi

echo "[2/4] Erstelle AppDir-Struktur fuer AppImage ..."
rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
mkdir -p "$APPDIR/usr/share/applications"
mkdir -p "$APPDIR/usr/share/icons/hicolor/256x256/apps"

# Copy all application binaries & assets into usr/bin
cp -r "$LINUX_DIST"/* "$APPDIR/usr/bin/"

# Setup desktop file
cat << 'EOF' > "$APPDIR/m-player.desktop"
[Desktop Entry]
Type=Application
Name=M-Player
GenericName=Music Player
Comment=Offline Music Manager & YouTube Downloader
Exec=M-Player
Icon=m-player
Terminal=false
Categories=AudioVideo;Audio;Player;Qt;
EOF

cp "$APPDIR/m-player.desktop" "$APPDIR/usr/share/applications/m-player.desktop"

# Setup icon
if [ -f "$BASE_DIR/assets/icon.png" ]; then
    cp "$BASE_DIR/assets/icon.png" "$APPDIR/m-player.png"
    cp "$BASE_DIR/assets/icon.png" "$APPDIR/usr/share/icons/hicolor/256x256/apps/m-player.png"
else
    echo "Warnung: assets/icon.png nicht gefunden!"
fi

# Setup AppRun
cat << 'EOF' > "$APPDIR/AppRun"
#!/bin/sh
set -e
HERE="$(dirname "$(readlink -f "${0}")")"
export PATH="${HERE}/usr/bin:${HERE}/usr/bin/bin:${PATH}"
export LD_LIBRARY_PATH="${HERE}/usr/bin:${HERE}/usr/bin/_internal:${LD_LIBRARY_PATH}"
export QT_PLUGIN_PATH="${HERE}/usr/bin/PySide6/plugins:${QT_PLUGIN_PATH}"
exec "${HERE}/usr/bin/M-Player" "$@"
EOF
chmod +x "$APPDIR/AppRun"

echo "[3/4] Baue AppImage ..."
APPIMAGE_TOOL=""
if command -v appimagetool >/dev/null 2>&1; then
    APPIMAGE_TOOL="$(command -v appimagetool)"
elif [ -x "$SCRIPT_DIR/appimagetool" ]; then
    APPIMAGE_TOOL="$SCRIPT_DIR/appimagetool"
fi

APPIMAGE_OUT="$DIST_DIR/M-Player-${VERSION}-x86_64.AppImage"

if [ -n "$APPIMAGE_TOOL" ]; then
    export ARCH=x86_64
    "$APPIMAGE_TOOL" "$APPDIR" "$APPIMAGE_OUT" || "$APPIMAGE_TOOL" --appimage-extract-and-run "$APPDIR" "$APPIMAGE_OUT"
    if [ -f "$APPIMAGE_OUT" ]; then
        chmod +x "$APPIMAGE_OUT"
        echo "  [OK] AppImage erfolgreich erzeugt: $APPIMAGE_OUT"
    fi
else
    echo "  ! Hinweis: appimagetool nicht gefunden. Das Portable-Archiv (.tar.gz) ist jedoch einsatzbereit!"
fi

echo "[4/4] Linux-Build erfolgreich abgeschlossen!"
echo "===================================================="
echo "Erstellte Artefakte in dist/:"
ls -lh "$DIST_DIR"
echo "===================================================="

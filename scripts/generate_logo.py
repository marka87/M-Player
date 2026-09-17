"""Generate modern M-Player SVG logo and multi-resolution Windows ICO."""

from pathlib import Path
import struct
from PySide6.QtCore import QByteArray, QBuffer
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

SVG_CONTENT = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" width="128" height="128">
  <defs>
    <linearGradient id="brandGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#1ED760" />
      <stop offset="100%" stop-color="#1DB954" />
    </linearGradient>
    <linearGradient id="bgGrad" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#171C22" />
      <stop offset="100%" stop-color="#0F1215" />
    </linearGradient>
  </defs>
  <!-- Squircle tile background with subtle border -->
  <rect x="6" y="6" width="116" height="116" rx="28" fill="url(#bgGrad)" stroke="#262D37" stroke-width="2"/>
  <!-- 4 Audio Equalizer / Soundwave bars forming letter 'M' -->
  <rect x="25" y="28" width="12" height="72" rx="6" fill="url(#brandGrad)"/>
  <rect x="47" y="46" width="12" height="40" rx="6" fill="url(#brandGrad)"/>
  <rect x="69" y="46" width="12" height="40" rx="6" fill="url(#brandGrad)"/>
  <rect x="91" y="28" width="12" height="72" rx="6" fill="url(#brandGrad)"/>
</svg>'''


def create_multi_ico(images: list[tuple[int, int, bytes]], out_path: Path):
    """Write standard multi-resolution Windows ICO with embedded PNGs."""
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + len(images) * 16
    entries = []
    blobs = []
    for w, h, png_bytes in images:
        b_w = 0 if w == 256 else w
        b_h = 0 if h == 256 else h
        size = len(png_bytes)
        entry = struct.pack("<BBBBHHII", b_w, b_h, 0, 0, 1, 32, size, offset)
        entries.append(entry)
        blobs.append(png_bytes)
        offset += size

    with open(out_path, "wb") as f:
        f.write(header)
        for e in entries:
            f.write(e)
        for b in blobs:
            f.write(b)


def main():
    base = Path(__file__).resolve().parent.parent
    assets = base / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    logo_svg = assets / "logo.svg"
    logo_svg.write_text(SVG_CONTENT, encoding="utf-8")
    print(f"Wrote {logo_svg}")

    renderer = QSvgRenderer(QByteArray(SVG_CONTENT.encode("utf-8")))
    sizes = [16, 24, 32, 48, 64, 128, 256]
    png_images = []

    for s in sizes:
        img = QImage(s, s, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        renderer.render(p)
        p.end()

        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.WriteOnly)
        img.save(buf, "PNG")
        png_images.append((s, s, bytes(ba)))

    ico_path = assets / "icon.ico"
    create_multi_ico(png_images, ico_path)
    print(f"Wrote {ico_path} with sizes: {sizes}")

    # Write 256x256 PNG for Linux desktops and AppImage
    png_256 = next(b for s, _, b in png_images if s == 256)
    png_path = assets / "icon.png"
    png_path.write_bytes(png_256)
    print(f"Wrote {png_path} (256x256 PNG)")


if __name__ == "__main__":
    main()


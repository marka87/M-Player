"""Tests for precomputed cover thumbnails and disk caching."""

import sys
import tempfile
from pathlib import Path

# Ensure project root is in sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor
from mutagen.id3 import ID3, APIC
from src.services.cover_enricher import get_or_create_thumbnail, extract_raw_cover, get_thumbnail_cache_dir
from src.ui.ui import get_cover_pixmap


def test_thumbnail_pregeneration_and_caching():
    app = QApplication.instance() or QApplication(sys.argv)

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)

        # 1. Create a dummy test image (300x300, solid red)
        img_file = tmp_path / "original_cover.jpg"
        img = QImage(300, 300, QImage.Format_RGB32)
        img.fill(QColor(255, 0, 0))
        img.save(str(img_file), "JPG", quality=90)
        assert img_file.exists()

        # 2. Test get_or_create_thumbnail for image file
        thumb_64 = get_or_create_thumbnail(img_file, 64)
        assert thumb_64 is not None
        assert thumb_64.is_file()
        assert thumb_64.stat().st_size > 0
        assert thumb_64.stat().st_size < img_file.stat().st_size

        # Verify dimensions of cached thumbnail
        loaded_thumb = QImage(str(thumb_64))
        assert loaded_thumb.width() == 64
        assert loaded_thumb.height() == 64

        # 3. Test caching hit (instant return of same path)
        second_call = get_or_create_thumbnail(img_file, 64)
        assert second_call == thumb_64

        # 4. Test MP3 with embedded APIC frame
        mp3_file = tmp_path / "track_with_cover.mp3"
        # Write minimal valid MPEG frame header + padding
        mp3_file.write_bytes(b"\xff\xfb\x90\x44" + b"\x00" * 300)

        # Embed ID3 cover
        tags = ID3()
        tags.add(APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,
            desc="Cover",
            data=img_file.read_bytes()
        ))
        tags.save(str(mp3_file))

        # Extract raw cover without Qt
        raw = extract_raw_cover(mp3_file)
        assert raw is not None
        assert len(raw) == img_file.stat().st_size

        # Generate 48x48 thumbnail for MP3
        thumb_mp3_48 = get_or_create_thumbnail(mp3_file, 48)
        assert thumb_mp3_48 is not None
        assert thumb_mp3_48.is_file()

        img_48 = QImage(str(thumb_mp3_48))
        assert img_48.width() == 48
        assert img_48.height() == 48

        # 5. Verify get_cover_pixmap integration in UI
        get_cover_pixmap.cache_clear()
        pix = get_cover_pixmap(str(mp3_file), 48)
        assert not pix.isNull()
        assert pix.width() == 48
        assert pix.height() == 48

        print("All thumbnail pregeneration & cache tests passed successfully!")


if __name__ == "__main__":
    test_thumbnail_pregeneration_and_caching()

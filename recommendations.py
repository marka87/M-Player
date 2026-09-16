"""Discovery / Radio recommendations fetcher using YouTube Radio Mix."""

from __future__ import annotations

import functools
import re
import yt_dlp
from metadata import clean_artist_title


@functools.lru_cache(maxsize=128)
def fetch_recommendations(artist: str, title: str, source_url: str = "", limit: int = 8) -> list[dict]:
    """Fetch 5-10 similar song recommendations based on artist/title or source_url."""
    v_id = None

    if source_url:
        m = re.search(r'(?:v=|youtu\.be/)([0-9A-Za-z_-]{11})', source_url)
        if m:
            v_id = m.group(1)

    opts = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
        "no_warnings": True,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            if not v_id:
                clean_t, clean_a = clean_artist_title(title, artist)
                query = f"{clean_a} {clean_t}".strip()
                if not query or query in ("Unbekannter Artist", "Unbekannt"):
                    query = clean_t
                if not query:
                    return []
                s_info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                entries = s_info.get("entries", []) if isinstance(s_info, dict) else []
                if not entries:
                    return []
                v_id = entries[0].get("id")

            if not v_id:
                return []

            radio_url = f"https://www.youtube.com/watch?v={v_id}&list=RD{v_id}"
            ydl.params["playlistend"] = limit + 2
            info = ydl.extract_info(radio_url, download=False)
            raw_entries = info.get("entries", []) if isinstance(info, dict) else []

            results = []
            seen_ids = {v_id}
            for e in raw_entries:
                if not e:
                    continue
                cand_id = e.get("id")
                if not cand_id or cand_id in seen_ids:
                    continue
                seen_ids.add(cand_id)

                raw_t = e.get("title") or "Unbekannter Titel"
                raw_a = e.get("uploader") or e.get("channel") or "Unbekannter Interpret"
                clean_t, clean_a = clean_artist_title(raw_t, raw_a)
                thumb = ""
                thumbs = e.get("thumbnails", [])
                if thumbs:
                    thumb = thumbs[-1].get("url", "")
                elif cand_id:
                    thumb = f"https://img.youtube.com/vi/{cand_id}/hqdefault.jpg"

                results.append({
                    "id": cand_id,
                    "title": clean_t,
                    "artist": clean_a,
                    "duration": e.get("duration", 0),
                    "url": f"https://www.youtube.com/watch?v={cand_id}",
                    "cover_url": thumb,
                    "type": "Song",
                })
                if len(results) >= limit:
                    break

            return results
    except Exception:
        return []


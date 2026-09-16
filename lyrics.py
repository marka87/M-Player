"""Live-Synced Lyrics fetcher and parser using the free, keyless LRCLIB API."""

from __future__ import annotations

import functools
import json
import re
import urllib.parse
import urllib.request


@functools.lru_cache(maxsize=256)
def fetch_lyrics(artist: str, title: str, duration: float = 0.0) -> dict | None:
    """Fetch synced and plain lyrics from lrclib.net API."""
    if not title:
        return None

    # Clean query for higher match rate
    from metadata import clean_artist_title
    clean_t, clean_a = clean_artist_title(title, artist)

    params = {
        "track_name": clean_t,
        "artist_name": clean_a if clean_a != "Unbekannter Artist" else "",
    }
    if duration > 10:
        params["duration"] = str(int(duration))

    query_str = urllib.parse.urlencode({k: v for k, v in params.items() if v})
    url = f"https://lrclib.net/api/get?{query_str}"

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "M-Player v1.1"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except Exception:
        # Fallback: search endpoint if exact get fails
        try:
            s_url = f"https://lrclib.net/api/search?q={urllib.parse.quote(f'{clean_a} {clean_t}')}"
            req = urllib.request.Request(s_url, headers={"User-Agent": "M-Player v1.1"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                results = json.loads(resp.read().decode("utf-8"))
                if results and isinstance(results, list):
                    return results[0]
        except Exception:
            pass
        return None


def parse_lrc(lrc_text: str) -> list[tuple[float, str]]:
    """Parse LRC timestamped string into a sorted list of (seconds, text) tuples."""
    if not lrc_text:
        return []

    lines = []
    # Pattern: [mm:ss.xx] or [mm:ss]
    pattern = re.compile(r'\[(\d{1,2}):(\d{1,2}(?:\.\d+)?)\](.*)')

    for raw_line in lrc_text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        match = pattern.match(raw_line)
        if match:
            minutes = int(match.group(1))
            seconds = float(match.group(2))
            total_sec = minutes * 60 + seconds
            text = match.group(3).strip()
            lines.append((total_sec, text))

    lines.sort(key=lambda x: x[0])
    return lines

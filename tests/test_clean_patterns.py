import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.services.metadata import clean_artist_title


def test_artist_patterns():
    cases = [
        # (raw_title, raw_artist, expected_title, expected_artist)
        ("Song", "Solomun (Official)", "Song", "Solomun"),
        ("Song", "U2 - Topic", "Song", "U2"),
        ("Song", "U2 – Topic", "Song", "U2"),
        ("Song", "TheWeekndVEVO", "Song", "TheWeeknd"),
        ("Song", "Artist VEVO", "Song", "Artist"),
        ("Song", "Artist - VEVO", "Song", "Artist"),
        ("Song", "EminemMusic", "Song", "EminemMusic"),  # Don't strip valid name
        ("Song", "Coldplay [Official Channel]", "Song", "Coldplay"),
        ("Song", "Artist (Official Video)", "Song", "Artist"),
        ("Song", "Queen Official", "Song", "Queen"),
        ("Song", "Artist - Channel", "Song", "Artist"),
        ("Song", "Artist [Topic]", "Song", "Artist"),
    ]
    for raw_title, raw_artist, exp_title, exp_artist in cases:
        t, a = clean_artist_title(raw_title, raw_artist)
        assert a == exp_artist, f"Expected artist '{exp_artist}', got '{a}' for input '{raw_artist}'"
        assert t == exp_title, f"Expected title '{exp_title}', got '{t}' for input '{raw_title}'"
    print("test_artist_patterns passed!")


def test_title_patterns():
    cases = [
        ("Song Name (Official Video)", "Artist", "Song Name", "Artist"),
        ("Song Name [Official Music Video]", "Artist", "Song Name", "Artist"),
        ("Song Name (Lyric Video)", "Artist", "Song Name", "Artist"),
        ("Song Name [HD] [1080p]", "Artist", "Song Name", "Artist"),
        ("Song Name (Audio)", "Artist", "Song Name", "Artist"),
        ("Song Name (Visualizer)", "Artist", "Song Name", "Artist"),
        ("Song Name - Official Video", "Artist", "Song Name", "Artist"),
        ("Song Name | Official Video", "Artist", "Song Name", "Artist"),
        ("Song Name (Free Download)", "Artist", "Song Name", "Artist"),
        ("Song Name (Out Now)", "Artist", "Song Name", "Artist"),
    ]
    for raw_title, raw_artist, exp_title, exp_artist in cases:
        t, a = clean_artist_title(raw_title, raw_artist)
        assert t == exp_title, f"Expected title '{exp_title}', got '{t}' for input '{raw_title}'"
    print("test_title_patterns passed!")


def test_combined_artist_title_split():
    cases = [
        # Combined title with video tags and channel as artist
        ("Solomun - Customer Is King (Official Video)", "Solomun (Official)", "Customer Is King", "Solomun"),
        ("Rick Astley - Never Gonna Give You Up [HD]", "RickAstleyVEVO", "Never Gonna Give You Up", "Rick Astley"),
        ("Daft Punk - One More Time", "Daft Punk - Topic", "One More Time", "Daft Punk"),
        ("U2 - With Or Without You (Audio)", "Unbekannter Artist", "With Or Without You", "U2"),
        # Band names that shouldn't break
        ("The Cinematic Orchestra - Arrival of the Birds", "The Cinematic Orchestra", "Arrival of the Birds", "The Cinematic Orchestra"),
    ]
    for raw_title, raw_artist, exp_title, exp_artist in cases:
        t, a = clean_artist_title(raw_title, raw_artist)
        assert a == exp_artist, f"Expected artist '{exp_artist}', got '{a}' for input ({raw_title}, {raw_artist})"
        assert t == exp_title, f"Expected title '{exp_title}', got '{t}' for input ({raw_title}, {raw_artist})"
    print("test_combined_artist_title_split passed!")


if __name__ == "__main__":
    test_artist_patterns()
    test_title_patterns()
    test_combined_artist_title_split()
    print("All cleaning pattern tests passed successfully!")


from pathlib import Path
from tempfile import TemporaryDirectory

from database import MusicDatabase
from metadata import TrackMetadata, safe_name, target_path


def run() -> None:
    assert safe_name('A/B:*?', 'x') == 'A_B___'
    with TemporaryDirectory() as directory:
        root = Path(directory)
        track = TrackMetadata('Titel', 'Artist', 'Album', track_number=1, genre='Rock')
        assert target_path(root, track) == root / 'Artist' / 'Album' / '01 - Titel.mp3'
        database = MusicDatabase(root / 'library.db')
        database.upsert(track, target_path(root, track))
        assert database.search(artist='Artist')[0]['title'] == 'Titel'
        database.create_playlist('TestListe')
        database.add_to_playlist('TestListe', 1)
        assert len(database.playlist_tracks('TestListe')) == 1


if __name__ == '__main__':
    run()
    print('Smoke test passed.')

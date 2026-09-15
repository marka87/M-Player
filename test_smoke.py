import json
from pathlib import Path
from tempfile import TemporaryDirectory

from database import MusicDatabase
from metadata import TrackMetadata, safe_name, target_path, save_playlist_json


def run() -> None:
    assert safe_name('A/B:*?', 'x') == 'A_B___'
    with TemporaryDirectory() as directory:
        root = Path(directory)
        track = TrackMetadata('Titel', 'Artist', 'Album', track_number=1, genre='Rock', collection='PartyHits')
        expected_path = root / 'PartyHits' / '001 - Artist - Titel.mp3'
        assert target_path(root, track) == expected_path

        # Test playlist.json saving
        save_playlist_json(expected_path.parent, 'PartyHits', 'https://youtube.com/...', 1)
        json_file = expected_path.parent / 'playlist.json'
        assert json_file.exists()
        data = json.loads(json_file.read_text(encoding='utf-8'))
        assert data['playlist_name'] == 'PartyHits'
        assert data['song_count'] == 1

        # Test database operations & migrations
        database = MusicDatabase(root / 'library.db')
        database.upsert(track, expected_path, duration=180, bitrate=320)
        assert database.search(artist='Artist')[0]['title'] == 'Titel'

        # Test playlist management
        database.create_playlist('TestListe')
        database.add_to_playlist('TestListe', 1)
        assert len(database.playlist_tracks('TestListe')) == 1

        # Test tag updating
        database.update_track_tags(1, 'Neuer Titel', 'Neuer Artist', 'Neues Album')
        updated = database.tracks('Neuer Titel')[0]
        assert updated['title'] == 'Neuer Titel'

        # Test downloads queue table
        database.record_download('https://youtube.com/test', 'Test Track', 'Test Artist')
        assert len(database.get_downloads()) == 1


if __name__ == '__main__':
    run()
    print('Smoke test passed.')

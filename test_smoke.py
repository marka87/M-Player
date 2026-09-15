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

        # Test downloads queue table & retry
        database.record_download('https://youtube.com/test', 'Test Track', 'Test Artist')
        dl_list = database.get_downloads()
        assert len(dl_list) == 1
        database.update_download('https://youtube.com/test', 'Fehlgeschlagen')
        database.retry_download(dl_list[0]['id'])
        assert database.get_downloads()[0]['status'] == 'Bereit'

        # Test dashboard_stats
        stats = database.dashboard_stats(root)
        assert stats['songs'] >= 1
        assert 'size_bytes' in stats
        assert 'playlists' in stats

        # Test delete_track (both tiers: keep file vs delete file)
        dummy_file = root / 'dummy.mp3'
        dummy_file.write_text('dummy audio data')
        dummy_track = TrackMetadata('Dummy', 'ArtistX', 'AlbumY')
        database.upsert(dummy_track, dummy_file, duration=120, bitrate=320)
        assert dummy_file.exists()
        d_row = database.tracks('Dummy')[0]
        # Tier 1: Library only (keep file)
        del_res = database.delete_track(d_row['id'], delete_file=False)
        assert del_res is True
        assert dummy_file.exists()
        assert len(database.tracks('Dummy')) == 0
        # Tier 2: Delete from disk
        database.upsert(dummy_track, dummy_file, duration=120, bitrate=320)
        d_row2 = database.tracks('Dummy')[0]
        del_res2 = database.delete_track(d_row2['id'], delete_file=True)
        assert del_res2 is True
        assert not dummy_file.exists()

        # Test sync_library cleanup (removing missing files)
        database.upsert(dummy_track, root / 'nonexistent.mp3')
        added, removed = database.sync_library(root)
        assert removed >= 1

        # Test delete_playlist
        pl_dir = root / 'DeleteMe'
        pl_dir.mkdir(parents=True, exist_ok=True)
        (pl_dir / 'test.mp3').write_text('temp')
        database.create_playlist('DeleteMe')
        del_pl_res = database.delete_playlist('DeleteMe', root)
        assert del_pl_res is True
        assert not pl_dir.exists()
        assert 'DeleteMe' not in database.playlist_names()

        # Test find_or_fetch_cover with local cover.jpg
        from metadata import find_or_fetch_cover
        cover_dir = root / 'AlbumCoverTest'
        cover_dir.mkdir(parents=True, exist_ok=True)
        local_cover = cover_dir / 'cover.jpg'
        local_cover.write_bytes(b'\xff\xd8\xff\xe0\x00\x10JFIF')
        dummy_song = cover_dir / 'song.mp3'
        found = find_or_fetch_cover('ArtistZ', 'AlbumZ', root, dummy_song)
        assert found == local_cover

        # Test CoverEnricher embedding & tag reading
        from cover_enricher import CoverEnricher
        enricher = CoverEnricher()
        from mutagen.id3 import ID3, TIT2, TPE1, TALB
        test_mp3 = root / 'enrich_test.mp3'
        test_mp3.write_bytes(b'\xff\xfb\x90\x44' + b'\x00' * 500)
        tags = ID3()
        tags['TIT2'] = TIT2(encoding=3, text='Song')
        tags['TPE1'] = TPE1(encoding=3, text='Artist')
        tags['TALB'] = TALB(encoding=3, text='Album')
        tags.save(test_mp3)

        artist, album, has_cover = enricher.read_tags(test_mp3)
        assert artist == 'Artist'
        assert album == 'Album'
        assert has_cover is False

        ok = enricher.embed_cover(test_mp3, b'\xff\xd8\xff\xe0\x00\x10JFIF')
        assert ok is True
        _, _, has_cover_now = enricher.read_tags(test_mp3)
        assert has_cover_now is True


if __name__ == '__main__':
    run()
    print('Smoke test passed.')

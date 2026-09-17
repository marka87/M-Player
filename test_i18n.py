from i18n import LANGUAGES, TRANSLATIONS, set_language, get_language, tr, DEFAULT_LANGUAGE

def test_languages_defined():
    assert "de" in LANGUAGES
    assert "en" in LANGUAGES
    assert "hu" in LANGUAGES

def test_translation_coverage():
    for key, lang_map in TRANSLATIONS.items():
        assert "de" in lang_map, f"Missing 'de' for key {key}"
        assert "en" in lang_map, f"Missing 'en' for key {key}"
        assert "hu" in lang_map, f"Missing 'hu' for key {key}"
        assert len(lang_map["de"].strip()) > 0
        assert len(lang_map["en"].strip()) > 0
        assert len(lang_map["hu"].strip()) > 0

def test_switching_and_fallback():
    set_language("de")
    assert get_language() == "de"
    assert tr("nav_library") == "Bibliothek"

    set_language("en")
    assert get_language() == "en"
    assert tr("nav_library") == "Library"

    set_language("hu")
    assert get_language() == "hu"
    assert tr("nav_library") == "Könyvtár"

    # Test unknown key
    assert tr("non_existent_key", default="Fallback") == "Fallback"
    assert tr("non_existent_key") == "non_existent_key"

    # Reset
    set_language(DEFAULT_LANGUAGE)

def test_formatting():
    set_language("de")
    assert tr("stats_tracks_time", tracks=5, time="12:30") == "5 Songs • 12:30"

    set_language("en")
    assert tr("stats_tracks_time", tracks=5, time="12:30") == "5 songs • 12:30"

    set_language("hu")
    assert tr("stats_tracks_time", tracks=5, time="12:30") == "5 dal • 12:30"

    set_language(DEFAULT_LANGUAGE)


if __name__ == "__main__":
    test_languages_defined()
    test_translation_coverage()
    test_switching_and_fallback()
    test_formatting()
    print("ALL I18N TESTS PASSED!")

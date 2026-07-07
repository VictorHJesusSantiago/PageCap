from file_types import ALL_EXTENSIONS, category_of, conversions_for, get_info


def test_known_extension_has_category():
    assert category_of(".pdf") == "text"


def test_font_category_registered():
    assert category_of(".woff2") == "font"
    assert category_of(".ttf") == "font"


def test_unknown_extension_returns_other_category():
    assert category_of(".not-a-real-ext-xyz") == "other"


def test_get_info_by_extension():
    info = get_info(".jpg")
    assert info is not None
    assert info.category == "image"
    assert info.mime.startswith("image/")


def test_get_info_by_mime():
    info = get_info("image/png")
    assert info is not None
    assert info.ext == ".png"


def test_get_info_unknown_returns_none():
    assert get_info(".totally-fake-extension") is None


def test_conversions_for_video_includes_mp3():
    assert ".mp3" in conversions_for(".mp4")


def test_conversions_for_unknown_extension_is_empty():
    assert conversions_for(".not-a-real-ext-xyz") == []


def test_all_extensions_start_with_dot():
    for ext in ALL_EXTENSIONS:
        assert ext.startswith("."), f"{ext} should start with a dot"

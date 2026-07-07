from utils import unique_filename, build_cookie_header


def test_unique_filename_no_collision():
    assert unique_filename("photo.jpg", set()) == "photo.jpg"


def test_unique_filename_collision_appends_suffix():
    seen = {"photo.jpg"}
    result = unique_filename("photo.jpg", seen)
    assert result == "photo_1.jpg"


def test_unique_filename_multiple_collisions():
    seen = {"photo.jpg", "photo_1.jpg", "photo_2.jpg"}
    assert unique_filename("photo.jpg", seen) == "photo_3.jpg"


def test_build_cookie_header_basic():
    cookies = [{"name": "a", "value": "1"}, {"name": "b", "value": "2"}]
    assert build_cookie_header(cookies) == "a=1; b=2"


def test_build_cookie_header_strips_crlf_injection():
    cookies = [{"name": "a\r\nX-Evil: 1", "value": "1"}]
    header = build_cookie_header(cookies)
    assert "\r" not in header
    assert "\n" not in header

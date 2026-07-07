from pathlib import Path

from security import sniff_category, verify_mime

_JPEG_HEADER = b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 100
_PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
_HTML_BODY = b"<!DOCTYPE html><html><body>error page</body></html>"


def test_sniff_category_jpeg(tmp_path: Path):
    p = tmp_path / "x.bin"
    p.write_bytes(_JPEG_HEADER)
    assert sniff_category(p) == "image"


def test_sniff_category_png(tmp_path: Path):
    p = tmp_path / "x.bin"
    p.write_bytes(_PNG_HEADER)
    assert sniff_category(p) == "image"


def test_sniff_category_unknown_returns_none(tmp_path: Path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"\x01\x02\x03\x04")
    assert sniff_category(p) is None


def test_verify_mime_matching_jpeg(tmp_path: Path):
    p = tmp_path / "photo.jpg"
    p.write_bytes(_JPEG_HEADER)
    assert verify_mime(".jpg", p) is True


def test_verify_mime_spoofed_extension_detected(tmp_path: Path):
    # An HTML error page saved with a .jpg extension — the classic
    # "download failed silently and we saved the error page" bug this
    # check exists to catch.
    p = tmp_path / "photo.jpg"
    p.write_bytes(_HTML_BODY)
    assert verify_mime(".jpg", p) is False


def test_verify_mime_inconclusive_sniff_is_permissive(tmp_path: Path):
    p = tmp_path / "data.bin"
    p.write_bytes(b"\x01\x02\x03\x04" * 10)
    # No signature matched — verify_mime must not produce false positives.
    assert verify_mime(".bin", p) is True

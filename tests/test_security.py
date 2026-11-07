import socket

import pytest

from downloader.security import UnsafeURL, outbound_guard, validate_url


@pytest.mark.parametrize("url", [
    "file:///etc/passwd", "http://127.0.0.1/", "http://localhost/",
    "http://192.168.1.1/", "https://youtube.com:8080/watch?v=a",
    "https://person:secret@youtube.com/watch?v=a", "https://youtube.com.evil.test/watch",
])
def test_rejects_unsafe_urls(url):
    with pytest.raises(UnsafeURL):
        validate_url(url, resolve=False)


def test_accepts_public_platform_url():
    assert validate_url("  https://www.youtube.com/watch?v=abc  ", resolve=False) == "https://www.youtube.com/watch?v=abc"


def test_rejects_private_dns_answer(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("10.0.0.2", 443))])
    with pytest.raises(UnsafeURL):
        validate_url("https://youtube.com/watch?v=abc")


def test_blocks_private_redirect_destination():
    from downloader.security import _check_destination
    with outbound_guard():
        with pytest.raises(UnsafeURL):
            _check_destination(("169.254.169.254", 80))

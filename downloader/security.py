"""Conservative URL and outbound socket validation."""

import ipaddress
import socket
import threading
from urllib.parse import urlsplit


class UnsafeURL(ValueError):
    pass


# Generic extractors can follow arbitrary user supplied redirects. Version 1 only
# accepts known public video services; CDN requests are still checked by socket guard.
ALLOWED_DOMAINS = (
    "tiktok.com", "facebook.com", "fb.watch", "instagram.com",
    "youtube.com", "youtu.be", "x.com", "twitter.com", "reddit.com", "redd.it",
)


def _public_ip(address: str) -> bool:
    try:
        return ipaddress.ip_address(address.split("%", 1)[0]).is_global
    except ValueError:
        return False


def validate_url(raw: str, resolve: bool = True) -> str:
    url = raw.strip()
    if len(url) > 2048 or any(ord(c) < 32 for c in url):
        raise UnsafeURL("URL is too long or contains control characters")
    try:
        parts = urlsplit(url)
        host = (parts.hostname or "").rstrip(".").lower()
        port = parts.port
    except ValueError as exc:
        raise UnsafeURL("Malformed URL") from exc
    if parts.scheme not in ("http", "https") or not host:
        raise UnsafeURL("Use a full http:// or https:// video URL")
    if parts.username or parts.password or port not in (None, 80, 443):
        raise UnsafeURL("Credentials and nonstandard ports are not supported")
    if not any(host == domain or host.endswith("." + domain) for domain in ALLOWED_DOMAINS):
        raise UnsafeURL("This site is not enabled in the local safety allowlist")
    if resolve:
        try:
            addresses = socket.getaddrinfo(host, port or (443 if parts.scheme == "https" else 80))
        except OSError as exc:
            raise UnsafeURL("Could not resolve the video host") from exc
        if not addresses or any(not _public_ip(item[4][0]) for item in addresses):
            raise UnsafeURL("The video host resolves to a private or unsafe address")
    return url


_thread = threading.local()
_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_guard_installed = False


def _check_destination(address):
    if not getattr(_thread, "guard", False):
        return
    if not isinstance(address, tuple) or not address:
        return
    host = address[0]
    if _public_ip(host):
        return
    # Resolve hostnames at connection time too. Numeric IPs are handled above.
    try:
        infos = socket.getaddrinfo(host, address[1])
    except OSError as exc:
        raise UnsafeURL("Could not resolve outbound host") from exc
    if not infos or any(not _public_ip(info[4][0]) for info in infos):
        raise UnsafeURL("Redirect to a private or unsafe address was blocked")


def _safe_connect(self, address):
    _check_destination(address)
    return _original_connect(self, address)


def _safe_connect_ex(self, address):
    _check_destination(address)
    return _original_connect_ex(self, address)


def install_socket_guard():
    global _guard_installed
    if not _guard_installed:
        socket.socket.connect = _safe_connect
        socket.socket.connect_ex = _safe_connect_ex
        _guard_installed = True


class outbound_guard:
    def __enter__(self):
        install_socket_guard()
        _thread.guard = True

    def __exit__(self, *_):
        _thread.guard = False

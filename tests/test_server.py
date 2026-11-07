import socket

from fastapi.testclient import TestClient

from downloader.main import _loopback, choose_port, create_app, single_instance
from downloader.queue import JobQueue


def test_local_only_and_api(tmp_path):
    queue = JobQueue(tmp_path, lambda *args: None, resolve_urls=False)
    app = create_app(tmp_path, queue)
    try:
        with TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000)) as client:
            assert client.get("/api/jobs").status_code == 200
            assert "Local Video Downloader" in client.get("/").text
            assert client.get("/app.js").status_code == 200
            assert client.get("/style.css").status_code == 200
            assert client.post("/api/jobs", json={"urls": "https://youtu.be/a", "quality": "best"}).json()["added"]
            assert client.post("/api/jobs", json={"urls": "https://youtu.be/b"},
                               headers={"origin": "http://evil.example"}).status_code == 403
            assert client.get("/api/jobs", headers={"host": "evil.example"}).status_code == 403
    finally:
        queue.close()


def test_loopback_launcher_configuration():
    assert _loopback("127.0.0.1")
    assert _loopback("::1")
    assert not _loopback("192.168.0.1")
    port = choose_port(18000, 18010)
    assert 18000 <= port <= 18010


def test_second_instance_is_rejected(tmp_path):
    import pytest
    with single_instance(tmp_path):
        with pytest.raises(RuntimeError, match="already running"):
            with single_instance(tmp_path):
                pass


def test_port_conflict_selects_next_port():
    with socket.socket() as occupied:
        occupied.bind(("127.0.0.1", 0))
        port = occupied.getsockname()[1]
        assert choose_port(port, port + 10) != port

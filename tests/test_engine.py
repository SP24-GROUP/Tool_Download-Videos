from pathlib import Path

import pytest

from downloader import engine


class FakeYDL:
    def __init__(self, options):
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def extract_info(self, url, download=False):
        assert download is False
        return {"title": "Clip Test", "id": "abc", "ext": "mp4", "protocol": "https",
                "extractor_key": "YouTube"}

    def process_info(self, info):
        path = Path(self.options["outtmpl"]["default"].replace("%(title).100s", info["title"]).replace("%(id)s", info["id"]).replace("%(ext)s", "mp4"))
        path.write_bytes(b"sample")
        self.options["progress_hooks"][0]({"status": "downloading", "downloaded_bytes": 5, "total_bytes": 5})
        self.options["progress_hooks"][0]({"status": "finished"})


def test_download_saves_unique_file_and_progress(tmp_path, monkeypatch):
    monkeypatch.setattr(engine.yt_dlp, "YoutubeDL", FakeYDL)
    job = {"id": "job1", "url": "https://youtu.be/a", "quality": "best"}
    updates = []
    first = engine.download(job, lambda status, **fields: updates.append((status, fields)), lambda: False,
                            tmp_path / "downloads", tmp_path / "work")
    second = engine.download(job, lambda *args, **kwargs: None, lambda: False,
                             tmp_path / "downloads", tmp_path / "work")
    assert first != second
    assert Path(first).read_bytes() == b"sample"
    assert Path(second).read_bytes() == b"sample"
    assert [status for status, _ in updates] == ["fetching", "downloading", "downloading", "processing"]


def test_unsupported_protocol_has_useful_error(tmp_path, monkeypatch):
    class UnsafeYDL(FakeYDL):
        def extract_info(self, *args, **kwargs):
            result = super().extract_info(*args, **kwargs)
            result["protocol"] = "m3u8"
            return result
    monkeypatch.setattr(engine.yt_dlp, "YoutubeDL", UnsafeYDL)
    with pytest.raises(RuntimeError, match="media protocol"):
        engine.download({"id": "job2", "url": "https://youtu.be/a", "quality": "best"},
                        lambda *args, **kwargs: None, lambda: False,
                        tmp_path / "downloads", tmp_path / "work")

import threading
import time

import pytest

from downloader.engine import DownloadCancelled, safe_filename
from downloader.queue import JobQueue, parse_batch


def wait_until(predicate, timeout=3):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("Timed out waiting for job state")


def test_parse_batch_deduplicates_and_reports_invalid():
    valid, invalid = parse_batch("\n https://youtu.be/a \n\nhttps://youtu.be/a\nnot-a-url\n", resolve=False)
    assert valid == ["https://youtu.be/a"]
    assert [item["line"] for item in invalid] == [4, 5]
    assert "Duplicate" in invalid[0]["error"]
    with pytest.raises(ValueError):
        parse_batch("https://youtu.be/a\n" * 101, resolve=False)


def test_safe_filenames():
    assert safe_filename('  CON: <> "bad" / name.  ') == 'CON bad name'
    assert safe_filename("... ") == "video"
    assert safe_filename("CON") == "_CON"
    assert safe_filename("NUL.txt") == "_NUL.txt"


def test_concurrency_and_failure_isolation(tmp_path):
    lock = threading.Lock()
    release = threading.Event()
    current = 0
    maximum = 0
    calls = []

    def runner(job, update, cancelled, downloads, scratch):
        nonlocal current, maximum
        with lock:
            current += 1
            maximum = max(maximum, current)
            calls.append(job["url"])
        update("downloading", percent=10)
        release.wait(2)
        with lock:
            current -= 1
        if job["url"].endswith("/2"):
            raise RuntimeError("Mock failure")
        return str(downloads / (job["id"] + ".mp4"))

    queue = JobQueue(tmp_path, runner, resolve_urls=False)
    try:
        queue.configure(2)
        queue.add("\n".join(f"https://youtu.be/{n}" for n in range(3)), "best")
        queue.start()
        wait_until(lambda: queue.snapshot()["active"] == 2)
        assert maximum == 2
        queue.add("https://youtu.be/3", "best")
        assert queue.snapshot()["counts"]["queued"] == 2
        release.set()
        wait_until(lambda: sum(queue.snapshot()["counts"][s] for s in ("completed", "failed")) == 4)
        assert maximum == 2
        assert len(calls) == 4
        assert queue.snapshot()["counts"]["failed"] == 1
        assert queue.snapshot()["counts"]["completed"] == 3
    finally:
        release.set()
        queue.close()


def test_cancel_queued_and_active_then_retry_failed(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def runner(job, update, cancelled, downloads, scratch):
        entered.set()
        update("downloading")
        release.wait(2)
        if cancelled():
            raise DownloadCancelled()
        raise RuntimeError("Temporary failure")

    queue = JobQueue(tmp_path, runner, resolve_urls=False)
    try:
        queue.configure(1)
        ids = queue.add("https://youtu.be/a\nhttps://youtu.be/b", "720")["added"]
        queue.start()
        assert entered.wait(2)
        queue.cancel(ids[1])
        queue.cancel(ids[0])
        release.set()
        wait_until(lambda: queue.snapshot()["counts"]["cancelled"] == 2)
        with pytest.raises(ValueError):
            queue.retry(ids[0])
        failed = queue.add("https://youtu.be/c", "best")["added"][0]
        wait_until(lambda: queue.snapshot()["counts"]["failed"] == 1)
        queue.retry(failed)
        wait_until(lambda: queue.snapshot()["counts"]["failed"] == 1)
    finally:
        release.set()
        queue.close()


def test_restart_marks_interrupted_and_does_not_autostart(tmp_path):
    queue = JobQueue(tmp_path, lambda *args: None, resolve_urls=False)
    ids = queue.add("https://youtu.be/a\nhttps://youtu.be/b", "best")["added"]
    with queue.lock:
        queue.jobs[0]["status"] = "downloading"
        queue._save()
    queue.close()
    restarted = JobQueue(tmp_path, lambda *args: None, resolve_urls=False)
    try:
        snapshot = restarted.snapshot()
        assert snapshot["started"] is False
        assert snapshot["counts"]["failed"] == 1
        assert snapshot["counts"]["queued"] == 1
        assert "Interrupted" in snapshot["jobs"][0]["error"]
    finally:
        restarted.close()

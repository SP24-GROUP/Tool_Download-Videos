"""Bounded, persistent download queue."""

import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .engine import DownloadCancelled, download
from .security import UnsafeURL, validate_url


TERMINAL = {"completed", "failed", "cancelled"}
ACTIVE = {"fetching", "downloading", "processing"}
QUALITY = {"best", "1080", "720", "480"}


def parse_batch(text: str, *, resolve: bool = True):
    lines = [(number, line.strip()) for number, line in enumerate(text.splitlines(), 1) if line.strip()]
    if len(lines) > 100:
        raise ValueError("Submit at most 100 nonblank URLs per batch")
    valid, invalid, seen = [], [], set()
    for number, url in lines:
        if url in seen:
            invalid.append({"line": number, "url": url, "error": "Duplicate in this batch"})
            continue
        seen.add(url)
        try:
            valid.append(validate_url(url, resolve=resolve))
        except UnsafeURL as exc:
            invalid.append({"line": number, "url": url, "error": str(exc)})
    return valid, invalid


class JobQueue:
    def __init__(self, root: Path, runner=download, *, resolve_urls=True):
        self.root = Path(root)
        self.downloads = self.root / "downloads"
        self.scratch = self.root / ".state" / "work"
        self.state_file = self.root / ".state" / "jobs.json"
        self.downloads.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(self.scratch, ignore_errors=True)
        self.scratch.mkdir(parents=True, exist_ok=True)
        self.runner = runner
        self.resolve_urls = resolve_urls
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.jobs = []
        self.running = set()
        self.concurrency = 3
        self.started = False
        self.closed = False
        self._load()
        self.scheduler = threading.Thread(target=self._schedule, daemon=True, name="download-scheduler")
        self.scheduler.start()

    def _load(self):
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            self.concurrency = max(1, min(5, int(data.get("concurrency", 3))))
            self.jobs = data.get("jobs", [])
            for job in self.jobs:
                if job["status"] in ACTIVE:
                    job.update(status="failed", error="Interrupted by application restart; retry to download again")
                    job["cancel_requested"] = False
            self._save()
        except (OSError, ValueError, KeyError, TypeError):
            self.jobs = []

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps({"concurrency": self.concurrency, "jobs": self.jobs}, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self.state_file)

    def snapshot(self):
        with self.lock:
            jobs = [dict(job) for job in self.jobs]
            counts = {status: sum(job["status"] == status for job in jobs)
                      for status in ("queued", "fetching", "downloading", "processing", "completed", "failed", "cancelled")}
            return {"jobs": jobs, "counts": counts, "active": len(self.running),
                    "concurrency": self.concurrency, "started": self.started,
                    "download_folder": str(self.downloads.resolve())}

    def add(self, text: str, quality: str):
        if quality not in QUALITY:
            raise ValueError("Choose a valid quality")
        valid, invalid = parse_batch(text, resolve=self.resolve_urls)
        with self.condition:
            added = []
            for url in valid:
                job = {"id": uuid.uuid4().hex, "url": url, "quality": quality,
                       "title": "Waiting for information", "platform": "—", "status": "queued",
                       "percent": None, "downloaded_bytes": None, "total_bytes": None,
                       "speed": None, "eta": None, "file_path": None, "error": None,
                       "cancel_requested": False, "created_at": datetime.now(timezone.utc).isoformat()}
                self.jobs.append(job)
                added.append(job["id"])
            if added:
                self._save()
                self.condition.notify_all()
        return {"added": added, "invalid": invalid}

    def configure(self, concurrency: int):
        if not isinstance(concurrency, int) or not 1 <= concurrency <= 5:
            raise ValueError("Concurrent downloads must be from 1 to 5")
        with self.condition:
            self.concurrency = concurrency
            self._save()
            self.condition.notify_all()

    def start(self):
        with self.condition:
            self.started = True
            self.condition.notify_all()

    def _find(self, job_id):
        return next((job for job in self.jobs if job["id"] == job_id), None)

    def cancel(self, job_id):
        with self.condition:
            job = self._find(job_id)
            if not job:
                raise KeyError(job_id)
            if job["status"] == "queued":
                job["status"] = "cancelled"
            elif job["status"] in ACTIVE:
                job["cancel_requested"] = True
            else:
                raise ValueError("Only queued or active jobs can be cancelled")
            self._save()
            self.condition.notify_all()

    def retry(self, job_id):
        with self.condition:
            job = self._find(job_id)
            if not job:
                raise KeyError(job_id)
            if job["status"] != "failed":
                raise ValueError("Only failed jobs can be retried")
            job.update(status="queued", error=None, percent=None, downloaded_bytes=None,
                       total_bytes=None, speed=None, eta=None, file_path=None,
                       cancel_requested=False)
            self._save()
            self.condition.notify_all()

    def clear_completed(self):
        with self.condition:
            self.jobs = [job for job in self.jobs if job["status"] != "completed"]
            self._save()

    def _schedule(self):
        while True:
            with self.condition:
                self.condition.wait_for(lambda: self.closed or (self.started and len(self.running) < self.concurrency
                                        and any(j["status"] == "queued" for j in self.jobs)))
                if self.closed:
                    return
                job = next(j for j in self.jobs if j["status"] == "queued")
                job["status"] = "fetching"
                self.running.add(job["id"])
                self._save()
                job_copy = dict(job)
            threading.Thread(target=self._run, args=(job_copy,), daemon=True,
                             name=f"download-{job_copy['id'][:8]}").start()

    def _run(self, job):
        job_id = job["id"]

        def cancelled():
            with self.lock:
                current = self._find(job_id)
                return self.closed or current["cancel_requested"]

        def update(status, **fields):
            with self.lock:
                current = self._find(job_id)
                if current["status"] in TERMINAL:
                    return
                current.update(status=status, **fields)
                self._save()

        try:
            path = self.runner(job, update, cancelled, self.downloads, self.scratch)
            with self.lock:
                current = self._find(job_id)
                if current["cancel_requested"]:
                    Path(path).unlink(missing_ok=True)
                current.update(status="cancelled" if current["cancel_requested"] else "completed",
                               file_path=None if current["cancel_requested"] else path,
                               percent=None if current["cancel_requested"] else 100)
                self._save()
        except DownloadCancelled:
            update("cancelled", error=None)
        except Exception as exc:
            update("cancelled" if cancelled() else "failed",
                   error=None if cancelled() else str(exc)[:400])
        finally:
            with self.condition:
                self.running.discard(job_id)
                self.condition.notify_all()

    def close(self):
        with self.condition:
            self.closed = True
            self.condition.notify_all()
        self.scheduler.join(timeout=2)

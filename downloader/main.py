"""FastAPI app and local-only launcher."""

import ipaddress
import os
import socket
import threading
import time
import webbrowser
from contextlib import asynccontextmanager
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from .queue import JobQueue


ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


class BatchInput(BaseModel):
    urls: str
    quality: str = "best"


class SettingsInput(BaseModel):
    concurrency: int


def _loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def create_app(root: Path = ROOT, queue: JobQueue | None = None) -> FastAPI:
    manager = queue or JobQueue(root)

    @asynccontextmanager
    async def lifespan(_app):
        try:
            yield
        finally:
            manager.close()

    app = FastAPI(title="Local Video Downloader", docs_url=None, redoc_url=None, lifespan=lifespan)
    app.state.queue = manager

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        client = request.client.host if request.client else ""
        host = request.headers.get("host", "")
        origin = request.headers.get("origin")
        if not _loopback(client) or not _loopback(urlsplit("//" + host).hostname or ""):
            return JSONResponse({"detail": "Local access only"}, status_code=403)
        if origin:
            parsed = urlsplit(origin)
            if not _loopback(parsed.hostname or "") or parsed.scheme != "http" or parsed.netloc != host:
                return JSONResponse({"detail": "Cross-origin requests are blocked"}, status_code=403)
        return await call_next(request)

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/style.css")
    def css():
        return FileResponse(STATIC / "style.css", media_type="text/css")

    @app.get("/app.js")
    def js():
        return FileResponse(STATIC / "app.js", media_type="text/javascript")

    @app.get("/api/jobs")
    def jobs():
        return manager.snapshot()

    @app.post("/api/jobs")
    def add(payload: BatchInput):
        try:
            return manager.add(payload.urls, payload.quality)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/start")
    def start():
        manager.start()
        return manager.snapshot()

    @app.post("/api/settings")
    def settings(payload: SettingsInput):
        try:
            manager.configure(payload.concurrency)
            return manager.snapshot()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel(job_id: str):
        try:
            manager.cancel(job_id)
            return manager.snapshot()
        except KeyError as exc:
            raise HTTPException(404, "Job not found") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/jobs/{job_id}/retry")
    def retry(job_id: str):
        try:
            manager.retry(job_id)
            return manager.snapshot()
        except KeyError as exc:
            raise HTTPException(404, "Job not found") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/clear-completed")
    def clear_completed():
        manager.clear_completed()
        return manager.snapshot()

    @app.post("/api/open-folder")
    def open_folder():
        if os.name != "nt":
            raise HTTPException(501, "Open Folder is available on Windows")
        os.startfile(str(manager.downloads.resolve()))
        return {"ok": True}

    return app


def choose_port(start=8000, end=8010):
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError(f"Ports {start}-{end} are busy. Close another local server and try again.")


def _open_when_ready(port):
    for _ in range(50):
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                webbrowser.open(f"http://127.0.0.1:{port}")
                return
        except OSError:
            time.sleep(0.2)


@contextmanager
def single_instance(root: Path):
    """Hold a process lock so two local servers cannot share one queue."""
    lock_path = root / ".state" / "instance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError("This app folder is already running. Use its existing browser window.") from exc
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def main():
    try:
        with single_instance(ROOT):
            port = choose_port()
            app = create_app(ROOT)
            print(f"Local Video Downloader: http://127.0.0.1:{port}")
            threading.Thread(target=_open_when_ready, args=(port,), daemon=True).start()
            uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
    except RuntimeError as exc:
        print(exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()

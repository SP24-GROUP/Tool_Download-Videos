"""One yt-dlp job, isolated in its own temporary folder."""

import re
import shutil
from pathlib import Path

import yt_dlp

from .security import outbound_guard


class DownloadCancelled(Exception):
    pass


def safe_filename(value: str, fallback: str = "video") -> str:
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", value)
    value = re.sub(r"\s+", " ", value).strip(" .")
    value = value[:100].rstrip(" .")
    value = value or fallback
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)),
                *(f"LPT{n}" for n in range(1, 10))}
    if value.split(".", 1)[0].upper() in reserved:
        value = "_" + value
    return value


def _format(quality: str) -> str:
    limit = {"best": "", "1080": "[height<=1080]", "720": "[height<=720]", "480": "[height<=480]"}[quality]
    return f"bestvideo[ext=mp4]{limit}+bestaudio[ext=m4a]/best[ext=mp4]{limit}"


def _error(exc: Exception) -> str:
    message = str(exc).replace("ERROR: ", "").strip()
    return message[:400] or type(exc).__name__


def download(job, update, cancelled, downloads: Path, scratch: Path):
    """Download a single video and return final path. update receives status and fields."""
    work = scratch / job["id"]
    work.mkdir(parents=True, exist_ok=True)

    def check():
        if cancelled():
            raise DownloadCancelled("Cancelled by user")

    def progress(data):
        check()
        state = data.get("status")
        if state == "downloading":
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            current = data.get("downloaded_bytes") or 0
            update("downloading", percent=round(current * 100 / total, 1) if total else None,
                   downloaded_bytes=current, total_bytes=total,
                   speed=data.get("speed"), eta=data.get("eta"))
        elif state == "finished":
            update("processing", percent=100)

    options = {
        "format": _format(job["quality"]),
        "outtmpl": {"default": str(work / "%(title).100s [%(id)s].%(ext)s")},
        "noplaylist": True,
        "ignoreerrors": False,
        "continuedl": False,
        "overwrites": False,
        "nopart": False,
        "retries": 2,
        "fragment_retries": 2,
        "extractor_retries": 2,
        "retry_sleep_functions": {"http": lambda n: min(2 ** n, 8),
                                  "fragment": lambda n: min(2 ** n, 8),
                                  "extractor": lambda n: min(2 ** n, 8)},
        "socket_timeout": 20,
        "merge_output_format": "mp4",
        "hls_prefer_native": True,
        "progress_hooks": [progress],
        "postprocessor_hooks": [lambda _data: check()],
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": False,
        "js_runtimes": {"deno": {}, "node": {}},
    }
    try:
        with outbound_guard(), yt_dlp.YoutubeDL(options) as ydl:
            check()
            update("fetching")
            info = ydl.extract_info(job["url"], download=False)
            check()
            if not info or info.get("_type") in ("playlist", "multi_video") or info.get("entries"):
                raise ValueError("Playlist or channel URLs are not supported")
            title = safe_filename(str(info.get("title") or "Video"))
            platform = str(info.get("extractor_key") or info.get("extractor") or "Video")[:60]
            update("downloading", title=title, platform=platform)
            formats = info.get("requested_formats") or []
            selected = formats or [info]
            supported_protocols = {"http", "https", "m3u8_native", "http_dash_segments", "dash"}
            if any(item.get("protocol") not in supported_protocols for item in selected):
                raise RuntimeError("This video requires a media protocol that is not enabled for safe local downloads")
            if len(formats) > 1 and not shutil.which("ffmpeg"):
                raise RuntimeError("FFmpeg is required to merge this video's audio and video")
            # process_info uses the already extracted single-video metadata.
            ydl.process_info(info)
            check()
        files = [p for p in work.iterdir() if p.is_file() and p.suffix.lower() == ".mp4"]
        if len(files) != 1:
            raise RuntimeError("No MP4-compatible video was produced for this URL")
        downloads.mkdir(parents=True, exist_ok=True)
        base = safe_filename(files[0].stem)
        for number in range(10000):
            name = f"{base}.mp4" if number == 0 else f"{base} ({number}).mp4"
            destination = downloads / name
            try:
                # Exclusive create reserves the destination; a failed copy removes it.
                with destination.open("xb") as target, files[0].open("rb") as source:
                    while chunk := source.read(1024 * 1024):
                        check()
                        target.write(chunk)
                check()
                return str(destination.resolve())
            except FileExistsError:
                continue
            except Exception:
                destination.unlink(missing_ok=True)
                raise
        raise RuntimeError("Could not choose an unused filename")
    except DownloadCancelled:
        raise
    except Exception as exc:
        if cancelled():
            raise DownloadCancelled("Cancelled by user") from exc
        raise RuntimeError(_error(exc)) from exc
    finally:
        shutil.rmtree(work, ignore_errors=True)

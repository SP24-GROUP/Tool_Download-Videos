# Local Video Downloader

A small, local-only batch video downloader for Windows 10/11. FastAPI serves a plain HTML/CSS/JavaScript interface on `127.0.0.1`; yt-dlp downloads public videos, and FFmpeg merges MP4-compatible streams. Up to three downloads run at once by default (configurable from one to five).

**Windows users:** Follow [WINDOWS_INSTALL.md](WINDOWS_INSTALL.md), then double-click `setup.bat` and `start.bat`.

## Project layout

```text
downloader/          API, queue, download engine, URL security
static/              Browser interface
tests/               Mocked automated tests
downloads/           Saved videos (created locally)
.state/              Queue history and temporary files (created locally)
setup.bat            One-time Windows setup
start.bat            Daily Windows launcher
```

## Operation

Submit one URL per line, up to 100 per batch. Blank lines are ignored and duplicates in the same submission are reported. Click **Add to queue** to stage links, or **Start downloads** to stage and start them. New links submitted during a running batch start automatically when a slot opens. Each job has progress, status, error, cancellation, and retry controls. Clearing completed queue records does not delete video files.

On restart, queued items remain queued, active items become failed with an interruption message, and downloads do not start automatically. Retry failed items and click **Start downloads**.

Only one copy of the app can run from a given folder at a time. A second start prints an error so it cannot corrupt queue history. Temporary work files from an interrupted run are removed at the next start; completed videos are kept.

Only public TikTok, Facebook, Instagram, YouTube, X/Twitter, and Reddit domains are accepted in version 1. Other yt-dlp sites are disabled until their URL and redirect behavior can be validated safely. The application rejects local/private target addresses and non-HTTP schemes. It does not use browser cookies, credentials, or a remote service. MP4 output requires an MP4-compatible source; some videos or qualities will be unavailable.

## Development and tests

Developers can install test dependencies with `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt`, then run `.venv\Scripts\python.exe -m pytest -q` from the app folder. Tests mock external downloads; they do not fetch media. For a manual check, use publicly available videos you have permission to download, paste ten different URLs, start the queue, and confirm the active count never exceeds the selected concurrency and completed files appear in `downloads`.

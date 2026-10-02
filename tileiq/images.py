"""Local thumbnail cache.

Source images run 300-500 KB each, so a gallery of them would crawl. Every
image is fetched once, resized to a square thumbnail and stored under
data/images/. The UI then reads local files: fast, and it still renders if a
source site is slow or offline.
"""
from __future__ import annotations

import hashlib
import io
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "images"
SIZE = 400
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) TileIQ-thumbnailer"}
_FAILURES: list[tuple[str, str]] = []


def path_for(url: str) -> Path:
    return CACHE / f"{hashlib.sha1(url.encode()).hexdigest()[:20]}.jpg"


def thumb(url: str | None, download: bool = False) -> str | None:
    """Return a local thumbnail path, fetching it if asked and not cached."""
    if not url or not isinstance(url, str) or not url.startswith("http"):
        return None
    p = path_for(url)
    if p.exists():
        return str(p)
    if not download:
        return None
    return str(p) if _fetch(url) else None


def _fetch(url: str, attempts: int = 3) -> bool:
    p = path_for(url)
    if p.exists():
        return True
    CACHE.mkdir(parents=True, exist_ok=True)
    last = None
    for attempt in range(attempts):
        try:
            r = requests.get(url, timeout=45, headers=HEADERS)
            r.raise_for_status()
            im = Image.open(io.BytesIO(r.content)).convert("RGB")
            im.thumbnail((SIZE, SIZE), Image.LANCZOS)
            im.save(p, "JPEG", quality=82, optimize=True)
            return True
        except Exception as exc:  # hosts throttle bursts; back off and retry
            last = exc
            time.sleep(1.5 * (attempt + 1))
    _FAILURES.append((url, f"{type(last).__name__}: {last}"[:120]))
    return False


def prefetch(urls, workers: int = 4, label: str = "images") -> int:
    """Download any thumbnails not already cached. Returns how many were added."""
    todo = [u for u in dict.fromkeys(urls) if isinstance(u, str) and u.startswith("http")
            and not path_for(u).exists()]
    if not todo:
        return 0
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, ok in enumerate(pool.map(_fetch, todo), 1):
            done += bool(ok)
            if i % 200 == 0:
                print(f"  {label}: {i}/{len(todo)} fetched", flush=True)
    print(f"  {label}: {done} new thumbnails ({len(todo) - done} failed)", flush=True)
    for url, why in _FAILURES[:5]:
        print(f"    failed: {why} {url[:80]}", flush=True)
    return done

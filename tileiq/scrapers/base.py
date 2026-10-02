"""Polite HTTP fetching shared by all scrapers.

Rules baked in: public pages only, one request at a time, a fixed delay between
requests, a descriptive user agent, and every raw response cached to disk so a
re-run of the pipeline doesn't hit the source again unless asked to.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = ROOT / "data" / "raw"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128 Safari/537.36 TileIQ-research"
)
DELAY_SECONDS = 1.0

_session = requests.Session()
_session.headers["User-Agent"] = USER_AGENT
# YouTube serves a consent interstitial (and localised text) without this.
_session.cookies.set("CONSENT", "YES+1", domain=".youtube.com")
_last_request = 0.0


def fetch(url: str, source: str, refresh: bool = False, timeout: int = 40) -> requests.Response | None:
    """GET a URL with caching and rate limiting. Returns None on failure."""
    cache_dir = RAW_DIR / source
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode()).hexdigest()[:16]
    body_path = cache_dir / f"{key}.body"
    meta_path = cache_dir / f"{key}.json"

    if not refresh and body_path.exists() and meta_path.exists():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        resp = requests.Response()
        resp._content = body_path.read_bytes()
        resp.status_code = meta["status"]
        resp.headers.update(meta["headers"])
        resp.url = url
        resp.encoding = "utf-8"
        return resp

    global _last_request
    wait = DELAY_SECONDS - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    try:
        resp = _session.get(url, timeout=timeout)
    except requests.RequestException as exc:
        print(f"  ! {source}: {url} failed: {exc}")
        return None
    finally:
        _last_request = time.time()

    body_path.write_bytes(resp.content)
    meta_path.write_text(
        json.dumps({"url": url, "status": resp.status_code, "fetched_at": time.time(),
                    "headers": {k: v for k, v in resp.headers.items() if k.lower().startswith("x-wp")}}),
        encoding="utf-8",
    )
    resp.encoding = "utf-8"
    return resp

from __future__ import annotations

import hashlib
import re
import time
import urllib.robotparser
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

import requests

USER_AGENT = "hackreport/0.1 (UK student hackathon research; contact: set-your-email)"
CACHE_DIR = Path("data/cache")
DELAY_SECONDS = 1.5
WAYBACK_API = "https://archive.org/wayback/available"

_robots: Dict[str, urllib.robotparser.RobotFileParser] = {}
_last_request = 0.0


def _allowed(url: str) -> bool:
    parts = urlparse(url)
    root = f"{parts.scheme}://{parts.netloc}"
    if root not in _robots:
        rp = urllib.robotparser.RobotFileParser()
        try:
            resp = requests.get(root + "/robots.txt", headers={"User-Agent": USER_AGENT}, timeout=15)
            rp.parse(resp.text.splitlines() if resp.ok else [])
        except requests.RequestException:
            rp.parse([])
        _robots[root] = rp
    return _robots[root].can_fetch(USER_AGENT, url)


def _throttle() -> None:
    global _last_request
    wait = DELAY_SECONDS - (time.time() - _last_request)
    if wait > 0:
        time.sleep(wait)
    _last_request = time.time()


def _cache_path(key: str) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return CACHE_DIR / (hashlib.sha1(key.encode()).hexdigest() + ".html")


def _wayback(url: str, season: int) -> Optional[str]:
    """Closest archived copy of url from within the season (Sep of season-1 to Aug of season)."""
    cached = _cache_path(f"wayback|{season}|{url}")
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    _throttle()
    try:
        meta = requests.get(WAYBACK_API, params={"url": url, "timestamp": f"{season}0301"},
                            headers={"User-Agent": USER_AGENT}, timeout=30).json()
        snap = meta.get("archived_snapshots", {}).get("closest")
        if not snap or not snap.get("available"):
            return None
        stamp = snap["timestamp"]
        if not (f"{season - 1}0901" <= stamp[:8] <= f"{season}0831"):
            return None
        # id_ returns the original page without the Wayback toolbar markup.
        raw = re.sub(r"/web/(\d+)/", r"/web/\1id_/", snap["url"]).replace("http://", "https://", 1)
        _throttle()
        resp = requests.get(raw, headers={"User-Agent": USER_AGENT}, timeout=60)
    except (requests.RequestException, ValueError):
        return None
    if resp.status_code != 200:
        return None
    print(f"  wayback ({stamp[:8]}): {url}")
    cached.write_text(resp.text, encoding="utf-8")
    return resp.text


def get_html(url: str, season: Optional[int] = None) -> Optional[str]:
    """Fetch a page politely: robots.txt respected, rate limited, cached on disk.

    If the live page is unavailable and a season is given, falls back to the Wayback Machine
    copy from that season. Returns None if neither works or robots.txt disallows the page.
    """
    cached = _cache_path(url)
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    if not _allowed(url):
        print(f"  skipped (robots.txt): {url}")
        return None
    _throttle()
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
        if resp.status_code == 200:
            cached.write_text(resp.text, encoding="utf-8")
            return resp.text
        print(f"  HTTP {resp.status_code}: {url}")
    except requests.RequestException as exc:
        print(f"  failed: {url} ({type(exc).__name__})")
    return _wayback(url, season) if season else None

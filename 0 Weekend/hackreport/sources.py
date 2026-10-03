from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .fetch import get_html

FIRST_YEAR = 2015
LAST_YEAR = 2026
CHUNK_CHARS = 6000


@dataclass
class Doc:
    source: str
    url: str
    year_hint: int
    text: str
    event_name: Optional[str] = None  # set for single-event pages
    context: str = ""


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "svg"]):
        tag.decompose()
    text = soup.get_text("\n")
    return re.sub(r"\n\s*\n+", "\n", text).strip()


def chunk(text: str, size: int = CHUNK_CHARS) -> List[str]:
    """Split on line boundaries so an event entry is rarely cut in half."""
    chunks, current = [], ""
    for line in text.splitlines():
        if len(current) + len(line) + 1 > size and current:
            chunks.append(current)
            current = ""
        current += line + "\n"
    if current.strip():
        chunks.append(current)
    return chunks


def _event_sites(html: str, year: int) -> Iterator[Doc]:
    """Follow each listing card's external link and read the organiser's own site (home + about/team page)."""
    soup = BeautifulSoup(html, "html.parser")
    seen = set()
    for a in soup.find_all("a"):
        href = a.get("href", "")
        if "Learn More" not in a.get_text() or not href.startswith("http") or href in seen:
            continue
        seen.add(href)
        card = a
        for _ in range(4):
            card = card.parent
        heading = card.find(["h1", "h2", "h3", "h4", "h5"])
        name = heading.get_text(" ", strip=True) if heading else None
        context = " ".join(card.get_text(" ").split())
        home = get_html(href, year)
        if not home:
            continue
        texts = [html_to_text(home)]
        extra = BeautifulSoup(home, "html.parser").find(
            "a", href=re.compile(r"about|team|who-we-are|organi[sz]ers", re.I))
        if extra and extra.get("href"):
            page = get_html(urljoin(href, extra["href"]), year)
            if page:
                texts.append(html_to_text(page))
        yield Doc("event_site", href, year, "\n".join(texts)[:CHUNK_CHARS], event_name=name, context=context)


def hackathons_uk(years: Iterable[int]) -> Iterator[Doc]:
    for year in years:
        url = f"https://hackathons.org.uk/events/{year}/"
        html = get_html(url)
        if html:
            yield Doc("hackathons.org.uk", url, year, html_to_text(html))
            yield from _event_sites(html, year)


def mlh(years: Iterable[int]) -> Iterator[Doc]:
    for year in years:
        url = f"https://www.mlh.com/seasons/{year}/events"
        html = get_html(url)
        if html:
            yield Doc("mlh", url, year, html_to_text(html))


def devpost_saved(years: Iterable[int], folder: str = "data/devpost") -> Iterator[Doc]:
    """Devpost blocks scripted access, so read pages saved from a browser (File > Save Page As).

    Name files like 2024-anything.html where 2024 is the season (Sep 2023 to Aug 2024).
    """
    for path in sorted(Path(folder).glob("*.htm*")):
        match = re.match(r"(\d{4})", path.name)
        year = int(match.group(1)) if match else 0
        if year and year not in set(years):
            continue
        yield Doc("devpost", path.name, year, html_to_text(path.read_text(encoding="utf-8", errors="ignore")))


SOURCES = {"hackathons_uk": hackathons_uk, "mlh": mlh, "devpost": devpost_saved}

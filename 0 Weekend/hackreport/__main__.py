from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from . import gemma
from .sources import FIRST_YEAR, LAST_YEAR, SOURCES, chunk

OUT = Path("data")
RAW = OUT / "events_raw.jsonl"
SEASON_PAGES = {"hackathons.org.uk", "mlh", "event_site"}


def _tokens(s: str) -> set:
    return set(re.findall(r"[a-z0-9]+", (s or "").lower()))


def _best_match(events: List[Dict[str, Any]], name: str) -> List[Dict[str, Any]]:
    if not events:
        return []
    return [max(events, key=lambda e: len(_tokens(e.get("name")) & _tokens(name)))]


def collect(source_names: List[str], years: List[int]) -> None:
    OUT.mkdir(exist_ok=True)
    with RAW.open("w", encoding="utf-8") as fh:
        for name in source_names:
            print(f"[{name}]")
            for doc in SOURCES[name](years):
                for i, piece in enumerate(chunk(doc.text)):
                    events = gemma.extract(piece, doc.year_hint, doc.context)
                    if doc.event_name:  # single-event site: keep only the matching event under the listing's name
                        events = _best_match(events, doc.event_name)
                    print(f"  {doc.url} chunk {i}: {len(events)} UK events")
                    for ev in events:
                        if doc.source in SEASON_PAGES:  # the page's season beats a year in the event name
                            ev["year"] = doc.year_hint
                        if doc.event_name:
                            ev["name"] = doc.event_name
                        ev.update(source=doc.source, source_url=doc.url)
                        fh.write(json.dumps(ev) + "\n")


def _key(ev: Dict[str, Any]) -> str:
    return re.sub(r"[^a-z0-9]", "", (ev.get("name") or "").lower()) + str(ev.get("year"))


def load_deduped() -> List[Dict[str, Any]]:
    """Merge the same event seen in several sources, keeping the first non-null value per field."""
    merged: Dict[str, Dict[str, Any]] = {}
    rows = [json.loads(line) for line in RAW.read_text(encoding="utf-8").splitlines()]
    rows.sort(key=lambda r: r["source"] != "event_site")  # organiser's own site wins over listings
    for ev in rows:
        if not ev.get("year"):
            continue
        cur = merged.setdefault(_key(ev), {"sources": []})
        for k, v in ev.items():
            if v is not None and v != "unknown" and cur.get(k) is None:
                cur[k] = v
        cur["sources"].append(ev["source"])
    return list(merged.values())


def report() -> None:
    events = sorted(load_deduped(), key=lambda e: (e["year"], e["name"]))
    fields = ["year", "name", "city", "university", "organiser", "organiser_type", "student_led",
              "attendees", "projects", "sources", "source_url", "evidence"]
    with (OUT / "events.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for ev in events:
            w.writerow({**ev, "sources": ";".join(sorted(set(ev["sources"])))})

    by_year: Dict[int, List[Dict[str, Any]]] = defaultdict(list)
    for ev in events:
        by_year[ev["year"]].append(ev)

    lines = ["# UK student-led hackathons by season", "",
             "Seasons run September to August and are named by the ending year (2024 = Sep 2023 to Aug 2024). "
             "Extracted by Gemma from public pages. Blank means not stated in the source; verify against `evidence` in events.csv.", "",
             "| Season | Events found | Student-led | Unclear | With attendee figure | With project figure |", "|---|---|---|---|---|---|"]
    for year in sorted(by_year):
        evs = by_year[year]
        led = [e for e in evs if e.get("student_led") is True]
        unclear = [e for e in evs if e.get("student_led") is None]
        lines.append(f"| {year} | {len(evs)} | {len(led)} | {len(unclear)} | "
                     f"{sum(1 for e in led if e.get('attendees'))} | {sum(1 for e in led if e.get('projects'))} |")
    for year in sorted(by_year):
        led = [e for e in by_year[year] if e.get("student_led") is True]
        if not led:
            continue
        lines += ["", f"## {year} season", "", "| Event | Organiser | Attendees | Projects | Sources |", "|---|---|---|---|---|"]
        for e in led:
            lines.append(f"| {e['name']} | {e.get('organiser') or ''} | {e.get('attendees') or ''} | "
                         f"{e.get('projects') or ''} | {', '.join(sorted(set(e['sources'])))} |")
    (OUT / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT / 'events.csv'} and {OUT / 'report.md'}")


def main() -> None:
    p = argparse.ArgumentParser(prog="hackreport")
    p.add_argument("command", choices=["collect", "report", "all"])
    p.add_argument("--sources", nargs="+", choices=list(SOURCES), default=["hackathons_uk", "mlh"])
    p.add_argument("--years", nargs="+", type=int, default=list(range(FIRST_YEAR, LAST_YEAR + 1)))
    args = p.parse_args()
    if args.command in ("collect", "all"):
        collect(args.sources, args.years)
    if args.command in ("report", "all"):
        report()


if __name__ == "__main__":
    main()

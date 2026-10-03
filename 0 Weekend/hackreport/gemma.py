from __future__ import annotations

import json
import re
from typing import Any, Dict, List

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma3:4b"

ORGANISER_TYPES = ["student_society", "university", "student_union", "company", "charity", "mlh", "other", "unknown"]

SCHEMA = {
    "type": "object",
    "properties": {
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "year": {"type": ["integer", "null"]},
                    "city": {"type": ["string", "null"]},
                    "university": {"type": ["string", "null"]},
                    "organiser": {"type": ["string", "null"]},
                    "organiser_type": {"type": "string", "enum": ORGANISER_TYPES},
                    "student_led": {"type": ["boolean", "null"]},
                    "attendees": {"type": ["integer", "null"]},
                    "projects": {"type": ["integer", "null"]},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "organiser_type", "student_led", "evidence"],
            },
        }
    },
    "required": ["events"],
}

PROMPT = """You extract UK hackathons from web page text.

Rules:
- Include only hackathons physically or primarily held in the United Kingdom. Skip everything else.
- Use ONLY facts stated in the text. If a value is not stated, use null. Never estimate attendees or projects.
- organiser: the named entity running the event (e.g. "University of Bath Computing Society"). null if not stated.
- organiser_type: one of {types}.
- student_led: true ONLY if the text names a student society, club or union as organiser, or says the event is student-run. False if run by a company, charity or council. Otherwise null. A university name or venue alone is NOT evidence: use null.
- evidence: a short verbatim quote from the text supporting organiser and student_led.{single}
- year: the season the event belongs to. A season runs September of the previous year to August of that year, so an event on 4 Nov 2023 is season 2024 and one on 2 Mar 2024 is also season 2024. Page hint (a season): {year}.

Return JSON matching the schema. If there are no UK hackathons in the text, return {{"events": []}}.

TEXT:
{text}
"""


STUDENT_WORDS = re.compile(r"student|society|soc\b|club|union|gdsc|dsc\b|hoppers", re.I)
COMPANY_WORDS = re.compile(r"\bltd\b|limited|\binc\b|plc|company|charity|council|foundation|agency", re.I)


def extract(text: str, year_hint: int, context: str = "") -> List[Dict[str, Any]]:
    single = (f"\n- This text is the website of ONE event, listed as: {context!r}. Return exactly that one event."
              if context else "")
    body = {
        "model": MODEL,
        "stream": False,
        "format": SCHEMA,
        "options": {"temperature": 0, "num_ctx": 8192},
        "messages": [
            {"role": "user", "content": PROMPT.format(types=", ".join(ORGANISER_TYPES), year=year_hint or "unknown", text=text, single=single)}
        ],
    }
    resp = requests.post(OLLAMA_URL, json=body, timeout=600)
    resp.raise_for_status()
    try:
        events = json.loads(resp.json()["message"]["content"]).get("events", [])
    except (json.JSONDecodeError, KeyError):
        return []
    for ev in events:
        # Venue-only evidence is a guess either way; demote to unknown.
        evidence = ev.get("evidence") or ""
        if ev.get("student_led") is True and not STUDENT_WORDS.search(evidence):
            ev["student_led"] = None
        if ev.get("student_led") is False and not COMPANY_WORDS.search(evidence):
            ev["student_led"] = None
    return events

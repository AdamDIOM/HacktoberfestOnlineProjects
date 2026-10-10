"""Offline planespotting chatbot: local aircraft DB retrieval + a local Ollama model."""

from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "aircraft.json"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.environ.get("PLANE_MODEL", "llama3.2:3b")
TOP_K = 4

# Plain-language terms mapped to the vocabulary used in the database.
SYNONYMS = {
    "four": ["4"], "two": ["2"], "twin": ["2"], "one": ["1"], "single": ["1"],
    "propellor": ["propeller"], "props": ["propeller"], "prop": ["propeller"],
    "turboprop": ["propeller"], "jet": ["jet"], "chopper": ["helicopter"],
    "hump": ["hump", "upper", "deck"], "bump": ["hump"], "humpback": ["hump"],
    "double": ["double", "deck"], "huge": ["huge", "largest", "large"],
    "big": ["large", "huge"], "tiny": ["small"], "little": ["small"],
    "fighter": ["fighter", "military"], "army": ["military"],
    "private": ["private", "business"], "cargo": ["cargo", "freighter"],
    "tail": ["tail"], "wingtips": ["winglets"], "winglet": ["winglets"],
}
STOPWORDS = {
    "a", "an", "the", "it", "is", "was", "with", "and", "of", "on", "in", "i", "saw",
    "that", "this", "plane", "aircraft", "looked", "like", "had", "has", "very", "kind",
    "some", "what", "its", "to", "at", "for", "my", "there", "were", "just",
}

SYSTEM_PROMPT = (
    "You are an offline planespotting guide for beginners. The user vaguely describes "
    "an aircraft they saw. You are given CANDIDATES from a local database. Pick the most "
    "likely match, name 1-3 possibilities in order of likelihood, and explain which "
    "visible features to check (engine count, wing position, tail, size). Prefer the "
    "database facts. If the description is too vague, ask one short follow-up question. "
    "Never invent facts not supported by the candidates or general well-known knowledge. "
    "Keep the answer short and friendly."
)


def load_db() -> list[dict]:
    return json.loads(DB_PATH.read_text(encoding="utf-8"))


def tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    out: list[str] = []
    for w in words:
        if w in STOPWORDS:
            continue
        out.append(w)
        out.extend(SYNONYMS.get(w, []))
    return out


def rank(query: str, db: list[dict], k: int = TOP_K) -> list[tuple[float, dict]]:
    q = tokens(query)
    scored = []
    for plane in db:
        # Weight engine/feature text above airline/name text.
        weighted = [
            (plane["engines"], 2.0), (plane["features"], 2.0), (plane["size"], 1.5),
            (plane["category"], 1.5), (plane["name"], 1.0), (plane["airlines"], 0.5),
        ]
        score = 0.0
        for text, weight in weighted:
            hay = set(tokens(text))
            score += weight * sum(1 for t in q if t in hay)
        if score > 0:
            scored.append((score, plane))
    scored.sort(key=lambda s: s[0], reverse=True)
    return scored[:k]


def format_candidates(ranked: list[tuple[float, dict]]) -> str:
    return "\n\n".join(
        f"- {p['name']} ({p['category']}, {p['size']}). Engines: {p['engines']}. "
        f"Features: {p['features']} Airlines: {p['airlines']}."
        for _, p in ranked
    )


def ask_model(history: list[dict]) -> str | None:
    body = json.dumps({"model": MODEL, "messages": history, "stream": True}).encode()
    req = urllib.request.Request(OLLAMA_URL, body, {"Content-Type": "application/json"})
    reply = []
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            for line in resp:
                chunk = json.loads(line)
                piece = chunk.get("message", {}).get("content", "")
                print(piece, end="", flush=True)
                reply.append(piece)
    except (urllib.error.URLError, ConnectionError, TimeoutError):
        return None
    print()
    return "".join(reply)


def fallback(ranked: list[tuple[float, dict]]) -> None:
    print("(Model unavailable - showing database matches only.)")
    for _, p in ranked:
        print(f"\n* {p['name']} - {p['size']}\n  {p['engines']}\n  {p['features']}")


def main() -> None:
    db = load_db()
    print(f"Planespotter (offline) - model: {MODEL}. Describe a plane, or 'quit' to exit.")
    history: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    context = ""
    while True:
        try:
            text = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if text.lower() in {"quit", "exit", "q"}:
            return
        if not text:
            continue

        # Include earlier user turns so follow-up answers keep the earlier clues.
        context = f"{context} {text}".strip() if len(context) < 600 else text
        ranked = rank(context, db)
        if not ranked:
            ranked = [(0.0, p) for p in db[:TOP_K]]
        history.append({
            "role": "user",
            "content": f"CANDIDATES:\n{format_candidates(ranked)}\n\nUSER DESCRIPTION: {text}",
        })
        print("Spotter: ", end="", flush=True)
        reply = ask_model(history)
        if reply is None:
            history.pop()
            print()
            fallback(ranked)
        else:
            history.append({"role": "assistant", "content": reply})


if __name__ == "__main__":
    sys.exit(main())

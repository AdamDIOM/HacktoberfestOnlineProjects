from __future__ import annotations

import json
from typing import Any, Optional

import httpx
from pydantic import ValidationError

from .models import Classification
from .taxonomy import CATEGORY_RUBRIC, URGENCY_RUBRIC


class OllamaError(RuntimeError):
    pass


class Classifier:
    def __init__(self, host: str, model: str, timeout: float = 90.0) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def health(self) -> dict[str, Any]:
        try:
            response = httpx.get(f"{self.host}/api/tags", timeout=3.0)
            response.raise_for_status()
            models = [item["name"] for item in response.json().get("models", [])]
            return {
                "ok": True,
                "models": models,
                "has_model": any(
                    name == self.model or name.startswith(f"{self.model}:")
                    for name in models
                )
                or self.model in models,
            }
        except httpx.HTTPError as exc:
            return {"ok": False, "models": [], "has_model": False, "error": str(exc)}

    def classify(
        self,
        *,
        title: str,
        details: str,
        impact: str,
        team: str,
    ) -> Classification:
        schema = Classification.model_json_schema()
        prompt = self._prompt(title=title, details=details, impact=impact, team=team)
        last_error: Optional[str] = None
        messages = [
            {
                "role": "system",
                "content": (
                    "You triage internal technical requests for an organisation. "
                    "Return JSON that matches the schema. No prose, no code fences. "
                    "Pick exactly one category and one urgency. "
                    "urgency_score is 1–100 and must agree with urgency "
                    "(critical 86–100, high 61–85, medium 31–60, low 1–30). "
                    "suggested_owner is a team that should take the ticket, not a person."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        for attempt in range(1, 4):
            if attempt > 1 and last_error:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Your previous output failed validation: {last_error}\n"
                            "Fix it to match the schema exactly."
                        ),
                    }
                )
            raw = self._chat(messages, schema)
            try:
                parsed = _defensive_parse(raw)
                result = Classification.model_validate(parsed)
                result = self._align_score(result)
                return result
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = str(exc)

        raise OllamaError(
            f"Could not classify after 3 attempts. Last error: {last_error}"
        )

    def _chat(self, messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
        try:
            response = httpx.post(
                f"{self.host}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": schema,
                    "options": {"temperature": 0},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise OllamaError(f"Ollama is unreachable or returned an error: {exc}") from exc

        payload = response.json()
        content = payload.get("message", {}).get("content", "")
        if not content:
            raise OllamaError("Ollama returned an empty classification.")
        return content

    def _prompt(self, *, title: str, details: str, impact: str, team: str) -> str:
        return (
            "Classify this internal technical request.\n\n"
            f"Requester team: {team}\n"
            f"Title: {title}\n"
            f"Details: {details}\n"
            f"Impact they reported: {impact}\n\n"
            f"Categories:\n{CATEGORY_RUBRIC}\n"
            f"Urgency:\n{URGENCY_RUBRIC}\n"
            "Write a one-sentence summary in plain English for the IT inbox. "
            "Rationale should cite the facts in the request, not invent outages."
        )

    @staticmethod
    def _align_score(result: Classification) -> Classification:
        bands = {
            "critical": (86, 100),
            "high": (61, 85),
            "medium": (31, 60),
            "low": (1, 30),
        }
        low, high = bands[result.urgency]
        if result.urgency_score < low or result.urgency_score > high:
            midpoint = (low + high) // 2
            return result.model_copy(update={"urgency_score": midpoint})
        return result


def _defensive_parse(content: str) -> Any:
    cleaned = content.strip()
    fence = "```"
    if cleaned.startswith(fence):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.rstrip().endswith(fence):
            cleaned = cleaned.rstrip()[:-3]
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1:
        cleaned = cleaned[start : end + 1]
    return json.loads(cleaned)

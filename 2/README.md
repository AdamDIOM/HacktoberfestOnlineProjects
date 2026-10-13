# OpenTriage

Internal technical request desk. People in the organisation submit what is broken or needed. A local [Ollama](https://ollama.com) model classifies each request by type and urgency so IT can work the queue in order. Request text never leaves the machine that runs Ollama.

## What it does

- Submit name, work email, team, title, details, and impact.
- `llama3.2:3b` (configurable) returns a category, urgency band, 1–100 score, one-line summary, rationale, and a suggested owning team.
- IT inbox sorts by urgency, filters by type/status, updates workflow, and can re-run classification.
- If Ollama is down, the request is still saved and marked unclassified.

Categories: access & accounts, hardware, software & apps, network, security, data & backup, infrastructure, feature/project, other.

Urgency: critical, high, medium, low — with a written rubric in `backend/taxonomy.py`.

## Run it

1. Install [Ollama](https://ollama.com/download) and pull a model:

```bash
ollama pull llama3.2:3b
```

2. Create a virtualenv and start the app:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn backend.app:app --reload --port 8000
```

3. Open [http://127.0.0.1:8000](http://127.0.0.1:8000). The IT inbox is [http://127.0.0.1:8000/#/inbox](http://127.0.0.1:8000/#/inbox).

Optional in `.env`:

- `ORG_EMAIL_DOMAIN=acme.com` — only that domain can submit.
- `OLLAMA_MODEL=gemma3:4b` — use another local model you have pulled.
- `ORG_TEAMS` — comma-separated team names on the form.

## Why local models

Classification is an extraction job, not a chat. The API sends Ollama a JSON Schema on `/api/chat` (`format`) so decoding is constrained to the Pydantic contract, then validates and retries up to three times. That keeps tickets out of a third-party LLM and keeps JSON parseable.

## License

MIT

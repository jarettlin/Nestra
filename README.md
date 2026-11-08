# Nestra

A voice-controlled smart home dashboard. Natural-language commands like
"lower the fan to a comfortable speed" are parsed into intents, and a fuzzy
logic engine turns vague words ("comfortable", "a bit", "cozy") into concrete
settings for simulated appliances.

| Part | Stack | Status |
|---|---|---|
| [backend/](backend/) | Python, FastAPI, NumPy | Simulator, fuzzy engine, NLU, REST + WebSocket API |
| [app/](app/) | Flutter | In-wall tablet dashboard with live updates and a command box |

## Quick start

```bash
cd backend && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
cd ../app && flutter build web
cd ../backend && .venv/bin/uvicorn nestra.main:app
```

Open http://localhost:8000 for the dashboard (API docs at /docs).
See [backend/README.md](backend/README.md) and [app/README.md](app/README.md) for details.

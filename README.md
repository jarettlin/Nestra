# Nestra

A voice-controlled smart home dashboard. Natural-language commands like
"lower the fan to a comfortable speed" are parsed into intents, and a fuzzy
logic engine turns vague words ("comfortable", "a bit", "cozy") into concrete
settings for simulated appliances.

| Part | Stack | Status |
|---|---|---|
| [backend/](backend/) | Python, FastAPI, NumPy | Simulator, fuzzy engine, NLU, REST + WebSocket API |
| app/ | Flutter | Planned: in-wall tablet dashboard |

See [backend/README.md](backend/README.md) to run the backend.

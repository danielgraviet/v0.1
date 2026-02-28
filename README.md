# Alpha SRE

A multi-agent AI system for site reliability engineering. Alpha accepts a structured incident payload, dispatches parallel AI agents to analyze it, and returns a ranked list of root-cause hypotheses.

---

## Alpha High-Level Flow

![Alpha Overview](assets/alpha_overview_flowchart.svg)

Edit the source diagram: [assets/alpha_overview_flowchart.drawio](assets/alpha_overview_flowchart.drawio)
Team onboarding guide: [ENGINEERING_ONBOARDING.md](ENGINEERING_ONBOARDING.md)

---

## How It Works

1. An incident payload arrives (logs, metrics, recent commits, config snapshot)
2. A signal extractor pulls out verified facts (e.g. "DB pool 100% saturated")
3. Four specialized agents run in parallel, each reasoning over the signals
4. A judge validates every agent output before it moves forward
5. An aggregator ranks hypotheses — cross-agent agreement boosts confidence scores
6. A final `ExecutionResult` is returned with ranked hypotheses and a human review flag

---

## Prerequisites

| Tool | Version | Install |
|------|---------|---------|
| Python | 3.13+ | [python.org](https://www.python.org/downloads/) or `brew install python@3.13` |
| uv | latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |

Verify before continuing:

```bash
python --version   # must be 3.13+
uv --version
```

---

## Setup

**1. Clone the repo**
```bash
git clone https://github.com/danielgraviet/v0.1.git
cd v0.1
```

**Quick commands (canonical)**
```bash
make setup      # install dependencies
make serve      # start web dashboard at http://127.0.0.1:8000
make test       # run offline tests (no network)
make test-live  # run live API tests (requires OPENROUTER_API_KEY + network)
make run        # run CLI entrypoint
make verify     # compile check + tests
```

**Tooling commands (what they do)**
- `make setup`: runs `uv sync --dev` to install app + dev dependencies into `.venv` (preferred onboarding path).
- `make serve`: starts the FastAPI dashboard server with hot reload at `http://127.0.0.1:8000`.
- `make run`: runs `main.py` using the project virtualenv.
- `make test`: runs deterministic/offline pytest only (`-m "not live"`), so it works in CI and no-network environments.
- `make test-live`: runs only live API tests (`-m "live"`), intended for explicit OpenRouter connectivity checks.
- `make check`: runs `python -m compileall -q .` to catch syntax/import-level issues quickly.
- `make verify`: runs `check` then `test` as the default pre-commit sanity check.

**2. Install dependencies**

Use:
```bash
make setup
```

This creates a `.venv/` directory and installs all dependencies pinned in `uv.lock`.

Manual equivalent (optional):
```bash
uv sync --dev
```

**3. Configure your API key**

Copy the example env file and fill in your real key:
```bash
cp .env.example .env
```

Open `.env` and replace the placeholder:
```
OPENROUTER_API_KEY=your_openrouter_key_here
```

Get an API key at [openrouter.ai](https://openrouter.ai). OpenRouter gives access to Anthropic, Google, and other models through a single key.

> `.env` is gitignored — your key will never be committed. `.env.example` is committed and shows teammates which variables are required.

**4. Verify the setup**

```bash
.venv/bin/python -c "from schemas.signal import Signal; print('Setup complete.')"
```

---

## Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `openai` | ≥2.24.0 | OpenRouter API client (OpenAI-compatible) |
| `pydantic` | ≥2.12.5 | Typed schemas and runtime validation |
| `python-dotenv` | ≥1.2.1 | Loads `OPENROUTER_API_KEY` from `.env` |
| `rich` | ≥14.3.3 | Live terminal display — one panel per agent |
| `fastapi` | ≥0.134.0 | Web dashboard server |
| `uvicorn` | ≥0.41.0 | ASGI server for FastAPI |

To add a new dependency:
```bash
uv add <package-name>
```

This updates both `pyproject.toml` and `uv.lock`. Commit both files.

---

## Project Structure

```
.
├── schemas/              # Pydantic models shared across all layers
│   ├── signal.py         # Signal — a verified fact from the incident
│   ├── hypothesis.py     # Hypothesis — an agent's candidate root cause
│   ├── incident.py       # IncidentInput — the raw payload entering the system
│   ├── result.py         # AgentResult, ExecutionResult — pipeline outputs
│   └── events.py         # AgentEvent — emitted during execution for the display layer
│
├── llm/                  # LLM provider abstraction
│   ├── base.py           # LLMClient abstract base — the interface all providers implement
│   └── openrouter.py     # OpenRouterClient — one key, all models
│
├── agents/               # Agent base class
│   └── base.py           # BaseAgent — abstract class all SRE agents extend
│
├── core/                 # Runtime orchestration
│   ├── runtime.py        # AlphaRuntime — the top-level pipeline
│   ├── executor.py       # ParallelExecutor — runs agents concurrently with asyncio
│   ├── registry.py       # AgentRegistry — tracks registered agents
│   └── memory.py         # StructuredMemory — typed in-RAM store for one execution
│
├── judge/
│   └── judge.py          # JudgeLayer — validates agent output before aggregation
│
├── aggregation/
│   └── aggregator.py     # Aggregator — ranks and deduplicates hypotheses
│
├── display/
│   └── live.py           # Rich live display — real-time agent panels in terminal
│
├── sre/                  # SRE vertical (imports from runtime, never the reverse)
│   ├── agents/           # LogAgent, MetricsAgent, CommitAgent, ConfigAgent, SynthesisAgent
│   ├── extractors/       # Signal extraction from raw incident data
│   ├── integrations/     # Sentry (live) and GitHub (stub → live) clients
│   └── scenarios/        # Demo payloads — incident_b.py for hackathon
│
├── tasks/                # Implementation phases and learning objectives
│   ├── phase_0.md        # Vision, problem statement, non-goals
│   ├── phase_1.md        # Data contracts — schemas locked before any code
│   ├── phase_2.md        # Runtime engine — this phase
│   ├── phase_3.md        # Signal extraction layer
│   └── phase_4.md        # SRE agents with live LLM calls
│
├── frontend/             # Web dashboard
│   ├── index.html        # Dashboard UI
│   └── static/
│       ├── style.css     # Engineering-first dark theme
│       └── app.js        # Agent status, signals, and hypothesis rendering
│
├── server.py             # FastAPI server — run with `make serve`
├── pyproject.toml        # Project metadata and direct dependencies
├── uv.lock               # Pinned dependency tree — always commit this
├── .env.example          # Required variable names with placeholders — commit this
└── .env                  # Your real API keys — never commit this (gitignored)
```

---

## Running the Smoke Test

Once Phase 2 is complete, verify the full pipeline with stub agents:

```bash
.venv/bin/python -m pytest tests/test_smoke.py
```

Or run directly:

```bash
.venv/bin/python tests/smoke.py
```

Expected output:
```
Pipeline smoke test passed.
ranked_hypotheses: 1
execution_id: <uuid>
```

---

## Architecture Notes

- **Runtime layer** (`schemas/`, `llm/`, `agents/`, `core/`, `judge/`, `aggregation/`, `display/`) — generic, knows nothing about SRE
- **SRE vertical** (`sre/`) — imports from the runtime layer, never the other way around
- **Signals = facts, Hypotheses = interpretations** — agents reason over signals, they never create them
- **OpenRouter** routes different agents to different models via a single API key — swapping a model is changing one string

# Phase 2 — Minimal Alpha Runtime (Core Engine)

**Goal:** Build only what the SRE vertical requires. A working orchestration engine that accepts a structured input payload, dispatches parallel agents, and returns ranked hypotheses.

This is not a general framework yet. Build just enough to make Phase 3 and 4 work.

---

## Learning Objectives

By the end of this phase, you should be able to:

- [ ] Explain what a "runtime" is in this context, and how it differs from a library or framework
- [ ] Build a base `Agent` class with typed input/output schemas using Pydantic
- [ ] Use `asyncio.TaskGroup` to run multiple agents concurrently and collect results
- [ ] Explain why structured memory (typed, in-RAM) is sufficient for a single execution
- [ ] Build a judge layer that validates agent output schemas before aggregation
- [ ] Build an aggregator that ranks hypotheses by confidence, with an agreement bonus for cross-agent convergence
- [ ] Wire all components into a single `AlphaRuntime.execute()` pipeline that works end-to-end
- [ ] Explain why a thin `LLMClient` abstraction lets the runtime stay provider-agnostic

---

## Core Concepts

### 1. What Is a Runtime?

A runtime is infrastructure that manages execution. It handles:
- **Who runs** — agent registration and lookup
- **What they receive** — input routing and context construction
- **How they run** — parallel execution with timeouts
- **What happens after** — validation (judge) and ranking (aggregator)

The agents are "dumb" workers. The runtime is the intelligent coordinator.

**Mental model:** Agents are functions. The runtime is the operating system scheduling them.

The key principle from `runtime_outline.md`:
> LLMs are reasoning modules, not the system.

### 2. Pydantic for Typed Schemas

Pydantic enforces data structure at runtime. You define a schema as a class, and Pydantic validates that any data you pass matches it. If it doesn't, you get an immediate, readable error — not silent corruption.

Everything in Alpha flows through Pydantic models:

```python
from pydantic import BaseModel

class Hypothesis(BaseModel):
    label: str
    description: str
    confidence: float      # 0.0 to 1.0
    severity: str          # "low" | "medium" | "high"
    supporting_signals: list[str]   # signal IDs
    contributing_agent: str
```

Why this matters: the judge layer validates against these schemas. If an agent returns malformed output, it gets rejected before it can corrupt the aggregation step.

### 3. asyncio and Task Groups

Python's `asyncio` runs coroutines concurrently on a single thread. For parallel agent execution, you dispatch all agents at once and wait for all of them to finish:

```python
import asyncio

async def run_all_agents(agents, context):
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(agent.run(context)) for agent in agents]
    # All tasks are done here
    return [t.result() for t in tasks]
```

Key behavior of `asyncio.TaskGroup` (Python 3.11+): if one task raises an unhandled exception, it cancels the remaining tasks. You will want to wrap agent execution in try/except to prevent one failing agent from killing the group.

**Note:** This is concurrency, not parallelism. If agents make network calls (LLM API requests), they yield control while waiting, which is where the speedup comes from.

### 4. Structured Memory

Memory in Alpha is not a database. It is a typed, append-only container that lives in RAM for the duration of a single execution:

```python
class StructuredMemory:
    signals: list[Signal]           # deterministic facts extracted from incident
    hypotheses: list[Hypothesis]    # interpretations from agents
    events: list[Event]             # execution trace (optional)
```

It is created at the start of `execute()`, written to during signal extraction and agent execution, and read by the aggregator. It does not persist between runs. No database needed for the hackathon.

### 5. The Judge Layer

The judge validates agent outputs before they reach the aggregator.

**Minimum viable judge (deterministic):**
- Does the output match the `AgentResult` schema? (Pydantic validation)
- Does each hypothesis cite at least one signal ID?

**Optional LLM judge:**
- Do the cited signal IDs actually exist in memory?
- Is the confidence score calibrated (not always 0.5)?

For the hackathon, implement the deterministic judge first. Add LLM validation only if time permits.

### 6. The Aggregator

The aggregator ranks hypotheses from all agents into a single ordered list.

**Simple scoring formula:**
```
final_score = base_confidence + agreement_bonus
```

Where:
- `base_confidence` = agent's self-reported confidence (0.0 to 1.0)
- `agreement_bonus` = +0.1 for each additional agent that produced a matching hypothesis

**Matching logic:** Two hypotheses "match" if their labels are similar (case-insensitive substring match is fine for now).

**Deduplication:** If two agents produce the same root cause, merge them into one hypothesis with the higher confidence and list both contributing agents.

This scoring formula is why cross-agent agreement matters — it's mathematically rewarded.

### 7. The LLMClient Abstraction (OpenRouter)

Alpha routes different agents to different models based on task fit. The provider of choice is **OpenRouter** — a unified proxy that gives access to Anthropic, Gemini, Cerebras, and others through a single OpenAI-compatible API and one API key.

One `OpenRouterClient` handles everything. Model routing is just a string:

```python
from abc import ABC, abstractmethod
import openai

class LLMClient(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str: ...

class OpenRouterClient(LLMClient):
    def __init__(self, model: str):
        self.model = model
        self.client = openai.AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )

    async def complete(self, system: str, user: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response.choices[0].message.content
```

Agent instantiation becomes:
```python
LogAgent(llm=OpenRouterClient("anthropic/claude-sonnet-4-6"))
MetricsAgent(llm=OpenRouterClient("google/gemini-2.0-flash"))
CommitAgent(llm=OpenRouterClient("anthropic/claude-sonnet-4-6"))
ConfigAgent(llm=OpenRouterClient("google/gemini-2.0-flash"))
```

Swapping to Cerebras later requires changing one string: `"cerebras/llama-3.3-70b"`. The rest of the system is unchanged.

### 8. Rich Display Layer

The `rich` library renders a live multi-panel terminal layout — one panel per agent, updating in real time. This is the visual story that proves parallel execution.

```
┌─ LogAgent ──────────────────────┐  ┌─ MetricsAgent ──────────────────┐
│ [1.31s] ● analyzing errors...   │  │ [1.31s] ● analyzing latency...  │
│ → sig_001 detected              │  │ → sig_002, sig_003 detected      │
│ ✓ 2 hypotheses generated        │  │ ✓ 1 hypothesis generated         │
└─────────────────────────────────┘  └─────────────────────────────────┘
┌─ CommitAgent ───────────────────┐  ┌─ ConfigAgent ───────────────────┐
│ [1.32s] ● analyzing diffs...    │  │ [1.32s] ● analyzing config...   │
│ → sig_005, sig_006 detected     │  │ ✓ complete                       │
│ ✓ 2 hypotheses generated        │  │                                  │
└─────────────────────────────────┘  └─────────────────────────────────┘
```

The runtime emits events as it runs (agent started, signal detected, agent complete). The display layer subscribes to those events and updates the panels. Runtime and display are decoupled — the runtime works fine without the display layer attached.

---

## Module Structure to Build

This is a monorepo. `alpha/` contains two layers: the generic runtime (Phases 2) and the SRE vertical built on top of it (Phases 3–4). The runtime never imports from `sre/` — dependency flows one direction only.

```
alpha/
│
├── # ── RUNTIME LAYER (generic, reusable across verticals) ─────────
│
├── core/
│   ├── runtime.py        ← AlphaRuntime class
│   ├── executor.py       ← ParallelExecutor
│   ├── registry.py       ← AgentRegistry
│   └── memory.py         ← StructuredMemory
│
├── agents/
│   └── base.py           ← BaseAgent abstract class
│
├── llm/
│   ├── base.py           ← LLMClient abstract base
│   └── openrouter.py     ← OpenRouterClient (primary)
│
├── judge/
│   └── judge.py          ← JudgeLayer (deterministic only)
│
├── aggregation/
│   └── aggregator.py     ← Aggregator
│
├── schemas/              ← Shared Pydantic models (used by both layers)
│   ├── signal.py         ← Signal model
│   ├── hypothesis.py     ← Hypothesis model
│   ├── incident.py       ← IncidentInput model
│   ├── result.py         ← ExecutionResult, AgentResult
│   └── events.py         ← AgentEvent (for display layer)
│
├── display/
│   └── live.py           ← Rich live display (agent panels)
│
└── # ── SRE VERTICAL (imports from runtime, never the reverse) ─────
│
└── sre/
    ├── agents/
    │   ├── log_agent.py          ← LogAgent (claude-sonnet-4-6)
    │   ├── metrics_agent.py      ← MetricsAgent (gemini-2.0-flash)
    │   ├── commit_agent.py       ← CommitAgent (claude-sonnet-4-6)
    │   ├── config_agent.py       ← ConfigAgent (gemini-2.0-flash)
    │   └── synthesis_agent.py    ← SynthesisAgent (runs after aggregation)
    │
    ├── extractors/
    │   └── signal_extractor.py   ← turns raw IncidentInput → Signal list
    │
    ├── integrations/
    │   ├── sentry.py             ← live Sentry client
    │   └── github.py             ← GitHub client (stub → live swap)
    │
    └── scenarios/
        └── incident_b.py         ← demo payload for hackathon
```

**Dependency rule:** Anything inside `alpha/sre/` may import from `alpha/core/`, `alpha/agents/`, `alpha/llm/`, `alpha/schemas/`, etc. Nothing outside `alpha/sre/` imports from it.

Build in this order: schemas → LLMClient → base agent → memory → executor → judge → aggregator → runtime → display.

---

## Implementation Checklist

### Step 1 — Schemas (build these first, everything else depends on them)

- [ ] `schemas/signal.py` — Define `Signal` model
  - Fields: `id: str`, `type: str`, `description: str`, `value: float | None`, `severity: str`, `source: str`
- [ ] `schemas/hypothesis.py` — Define `Hypothesis` model
  - Fields: `label: str`, `description: str`, `confidence: float`, `severity: str`, `supporting_signals: list[str]`, `contributing_agent: str`
- [ ] `schemas/incident.py` — Define `IncidentInput` model
  - Fields: `deployment_id: str`, `logs: list[str]`, `metrics: dict`, `recent_commits: list[dict]`, `config_snapshot: dict`
- [ ] `schemas/result.py` — Define `AgentResult` and `ExecutionResult` models
  - `AgentResult`: `agent_name: str`, `hypotheses: list[Hypothesis]`, `execution_time_ms: float`
  - `ExecutionResult`: `ranked_hypotheses: list[Hypothesis]`, `signals_used: list[Signal]`, `execution_id: str`, `requires_human_review: bool`

### Step 2 — LLMClient Abstraction

- [ ] `llm/base.py` — Define `LLMClient` abstract base class
  - Abstract method: `async def complete(self, system: str, user: str) -> str`
- [ ] `llm/openrouter.py` — Implement `OpenRouterClient(LLMClient)`
  - Constructor: `model: str` (required — no default, always be explicit)
  - Uses `openai.AsyncOpenAI` pointed at `https://openrouter.ai/api/v1`
  - Reads `OPENROUTER_API_KEY` from environment
  - Install: `pip install openai python-dotenv`
  - Output normalized to plain `str` — callers never see the SDK response object
- [ ] Add `OPENROUTER_API_KEY=your_key_here` to `.env`
- [ ] Add `.env` to `.gitignore`

### Step 3 — Base Agent

- [ ] `agents/base.py` — Define `BaseAgent` abstract class
  - Constructor: `__init__(self, llm: LLMClient)`
  - Property: `name: str` (abstract)
  - Method: `async def run(self, context: AgentContext) -> AgentResult` (abstract)
  - `AgentContext` dataclass: `signals: list[Signal]`, `incident: IncidentInput`

### Step 4 — Structured Memory

- [ ] `core/memory.py` — Implement `StructuredMemory`
  - `add_signal(signal: Signal) -> None`
  - `add_signals(signals: list[Signal]) -> None`
  - `add_hypothesis(hypothesis: Hypothesis) -> None`
  - `get_signals() -> list[Signal]`
  - `get_hypotheses() -> list[Hypothesis]`
  - Memory is initialized empty; all writes are append-only

### Step 5 — Agent Registry

- [ ] `core/registry.py` — Implement `AgentRegistry`
  - `register(agent: BaseAgent) -> None`
  - `get_all() -> list[BaseAgent]`
  - `get_by_name(name: str) -> BaseAgent | None`
  - Raise `ValueError` if registering duplicate agent name

### Step 6 — Parallel Executor

- [ ] `core/executor.py` — Implement `ParallelExecutor`
  - `async def execute(agents: list[BaseAgent], context: AgentContext) -> list[AgentResult]`
  - Use `asyncio.TaskGroup` to run all agents concurrently
  - Per-agent timeout: 30 seconds (configurable)
  - If an agent raises an exception: log the error, skip that agent, continue with remaining results
  - Record execution time per agent

### Step 7 — Judge Layer (deterministic only)

- [ ] `judge/judge.py` — Implement `JudgeLayer`
  - `validate(result: AgentResult, memory: StructuredMemory) -> JudgedResult`
  - `JudgedResult`: `valid: bool`, `result: AgentResult`, `rejection_reason: str | None`
  - All checks are deterministic — same inputs always produce the same pass/fail result
  - Check 1: `agent_name` is a non-empty string
  - Check 2: every `Hypothesis` in the result has at least one entry in `supporting_signals`
  - Check 3: every cited signal ID exists in `memory.get_signals()` (cross-reference)
  - Check 4: every `confidence` value is between 0.0 and 1.0
  - No LLM involved — ever

### Step 8 — Aggregator

- [ ] `aggregation/aggregator.py` — Implement `Aggregator`
  - `aggregate(results: list[JudgedResult]) -> list[Hypothesis]`
  - Collect all valid hypotheses from all agents
  - Group by similar label (case-insensitive)
  - For each group: take highest confidence, apply agreement bonus (+0.1 per additional agent), merge `contributing_agent` into a list
  - Sort by final score descending
  - Return top 5 hypotheses

### Step 9 — Alpha Runtime

- [ ] `core/runtime.py` — Implement `AlphaRuntime`
  - `register(agent: BaseAgent) -> None` — delegates to registry
  - `async def execute(payload: IncidentInput) -> ExecutionResult`
  - Pipeline order:
    1. Validate input (Pydantic)
    2. Initialize `StructuredMemory`
    3. Run signal extraction (placeholder for Phase 3 — pass empty signals for now)
    4. Build `AgentContext` from memory
    5. Execute agents in parallel via `ParallelExecutor`
    6. Validate each result via `JudgeLayer`
    7. Aggregate valid results via `Aggregator`
    8. Return structured `ExecutionResult`

---

## Wiring Test (Smoke Test Before Phase 3)

Before moving on, verify the full pipeline works with stub agents:

```python
import asyncio
from alpha.core.runtime import AlphaRuntime
from alpha.agents.base import BaseAgent, AgentContext
from alpha.schemas.result import AgentResult
from alpha.schemas.hypothesis import Hypothesis
from alpha.schemas.incident import IncidentInput

class StubAgent(BaseAgent):
    name = "stub"

    async def run(self, context: AgentContext) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            hypotheses=[
                Hypothesis(
                    label="Test hypothesis",
                    description="Stub agent output for pipeline testing",
                    confidence=0.6,
                    severity="medium",
                    supporting_signals=["sig_001"],
                    contributing_agent=self.name
                )
            ],
            execution_time_ms=0.0
        )

test_payload = IncidentInput(
    deployment_id="test-001",
    logs=["ERROR timeout", "ERROR timeout"],
    metrics={"latency_p99": 480},
    recent_commits=[],
    config_snapshot={}
)

runtime = AlphaRuntime()
runtime.register(StubAgent())
result = asyncio.run(runtime.execute(test_payload))

assert len(result.ranked_hypotheses) > 0
print("Pipeline smoke test passed.")
```

Run this before writing a single agent in Phase 4.

---

## Success Criteria

- [ ] All modules in `alpha/` directory structure exist and are importable
- [ ] `Signal`, `Hypothesis`, `IncidentInput`, `AgentResult`, `ExecutionResult` are Pydantic models
- [ ] `BaseAgent` is abstract — you cannot instantiate it directly
- [ ] `AlphaRuntime.execute()` completes without error on the stub payload
- [ ] Two stub agents registered simultaneously both appear in output (prove parallel execution by printing timestamps)
- [ ] Aggregator returns hypotheses sorted by confidence score (highest first)
- [ ] A stub agent that raises an exception does NOT crash the runtime
- [ ] `ExecutionResult` is a Pydantic model — not a raw dict

---

## Open Questions

1. **Python version?** `asyncio.TaskGroup` requires Python 3.11+. Check with `python --version`.
2. ~~**LLM provider?**~~ Resolved: OpenRouter via `openai` SDK. One key, all models.
3. ~~**Judge depth?**~~ Resolved: deterministic only — schema validation + signal ID cross-reference. No LLM.
4. **`__init__.py` files?** Decide upfront whether to use them for clean imports — e.g. `from alpha import AlphaRuntime`.

---

## Hackathon Priority

**Essential — build first:**
- [ ] Schemas (Signal, Hypothesis, IncidentInput, AgentResult, ExecutionResult)
- [ ] `OpenRouterClient` — one client, all models
- [ ] BaseAgent abstract class (accepts LLMClient)
- [ ] ParallelExecutor with asyncio
- [ ] AlphaRuntime.execute() pipeline
- [ ] Aggregator (deterministic formula: confidence + agreement bonus)
- [ ] JudgeLayer (deterministic: schema + signal ID checks)

**Important — build second:**
- [ ] StructuredMemory
- [ ] AgentRegistry
- [ ] Rich display layer (live agent panels)

**Optional — skip if time-pressured:**
- [ ] Per-agent timeouts
- [ ] Event logging / execution trace
- [ ] Execution replay
- [ ] CerebrasClient (post-hackathon swap for speed)

# Phase 4 — SRE Agent Pack

**Goal:** Model a parallel AI SRE team. Five specialized agents that independently analyze signals and generate ranked hypotheses using LLM reasoning — grounded in the signals extracted in Phase 3.

---

## Learning Objectives

By the end of this phase, you should be able to:

- [ ] Implement a concrete agent by extending `BaseAgent` from Phase 2
- [ ] Explain why different agents use different models (expert orchestration)
- [ ] Write system prompts that constrain LLM reasoning to provided signals (no hallucination)
- [ ] Force LLM output to be valid JSON matching a Pydantic schema
- [ ] Explain why agents are stateless, never call each other, and never invent signals
- [ ] Implement confidence scoring guidance in prompts (not just "use 0.5 for everything")
- [ ] Verify that all 4 parallel agents run concurrently via the runtime
- [ ] Implement the Synthesis Agent as a post-aggregation step

---

## Core Concepts

### 1. Agent Design Philosophy

Each agent is:
- **Role-specialized** — it asks a different question over the same signals
- **Stateless** — no memory between runs, no side effects, no persistent state
- **Constrained** — it can only reference signals that exist in its `AgentContext`
- **Structured** — output is a Pydantic `AgentResult`, not a freeform string

Think of it as: different experts reading the same briefing document. The log expert asks "what do the error patterns tell us?" The commit expert asks "what changed that could have caused this?" They never talk to each other. The runtime coordinates them.

From `runtime_outline.md`:
> Agents DO NOT call other agents. They DO NOT store memory. They DO NOT orchestrate. They are workers only.

### 2. Structured LLM Output

The most important skill in this phase is reliably getting structured JSON from an LLM.

The pattern:
1. Give the agent a clear role and task in the system prompt
2. Include the signals as JSON in the user message
3. Ask for output matching a specific JSON schema
4. Validate the response with Pydantic

```python
system_prompt = """
You are an expert SRE specializing in log analysis.
You receive structured signals extracted from a production incident.
Generate 1-3 root cause hypotheses based ONLY on the provided signals.
Do not invent signals. Each hypothesis MUST cite at least one signal ID.
Respond with valid JSON matching exactly this schema:
{
  "hypotheses": [
    {
      "label": "short root cause name",
      "description": "explanation of what happened and why",
      "confidence": 0.0-1.0,
      "severity": "low|medium|high",
      "supporting_signals": ["sig_001", "sig_002"],
      "contributing_agent": "log_agent"
    }
  ]
}
"""
```

Common failure modes and how to handle them:
- LLM wraps JSON in markdown code blocks → strip ` ```json ``` ` before parsing
- LLM adds commentary before/after JSON → use regex to extract the JSON object
- LLM returns invalid confidence values → clamp to [0.0, 1.0] after parsing

### 3. Confidence Scoring Guidance

Without explicit guidance, LLMs tend to return confidence = 0.5 for everything. That's useless for ranking.

Tell the agent in the prompt:
- **0.7–0.9** — Multiple signals converge on the same cause. High certainty.
- **0.4–0.6** — One signal supports this. Plausible but not confirmed.
- **0.1–0.3** — Speculative. Weak signal, alternative explanation possible.

The aggregator rewards agents that score confidently and accurately — cross-agent agreement boosts the final score.

### 4. Expert Orchestration — Right Model for the Right Task

Alpha doesn't use one LLM for everything. Each agent is assigned the model best suited to its reasoning task. This is the "expert orchestration" principle: the runtime routes work to specialists, whether those specialists are AI agents or AI models.

| Agent | Model | Why |
|---|---|---|
| `LogAgent` | `claude-sonnet-4-6` | Precision pattern recognition in noisy text. Claude excels at structured analysis. |
| `CommitAgent` | `claude-sonnet-4-6` | Code diff analysis requires deep code understanding. Claude is strongest here. |
| `SynthesisAgent` | `claude-sonnet-4-6` | Narrative requires technical accuracy. Claude keeps the reasoning grounded. |
| `MetricsAgent` | `gemini-2.0-flash` | Numerical threshold reasoning. Gemini Flash is fast and cheap for this task. |
| `ConfigAgent` | `gemini-2.0-flash` | Lightweight key-value comparison. No heavy reasoning needed. |

In the demo, you can show this table. It demonstrates that Alpha is routing intelligently — not just blasting everything at one model.

### 5. Agent Roles and Signal Focus

Each agent focuses on a subset of signal types:

| Agent | Primary Signal Types | Core Question | Model |
|---|---|---|---|
| `LogAgent` | `log_anomaly` | What do the error patterns suggest caused this? | claude-sonnet-4-6 |
| `MetricsAgent` | `metric_spike`, `resource_saturation`, `metric_degradation` | What do the numbers tell us about system behavior? | gemini-2.0-flash |
| `CommitAgent` | `commit_change` | What code changes could have introduced this failure? | claude-sonnet-4-6 |
| `ConfigAgent` | `config_change` | What configuration changes could have triggered this? | gemini-2.0-flash |
| `SynthesisAgent` | All signals + all hypotheses | What is the unified, ranked explanation of this incident? | claude-sonnet-4-6 |

### 5. The Synthesis Agent

The Synthesis Agent is architecturally different from the other four:
- **Runs after** the parallel agents (not in the parallel execution group)
- **Receives** all signals + the already-ranked hypotheses from the aggregator
- **Does not generate** new hypotheses from scratch
- **Produces** a narrative that explains the ranked list in plain English

Think of it as: an experienced SRE reading the investigation report and writing the executive summary.

Output: a `SynthesisResult` with a `summary: str` and `key_finding: str`.

---

## Module Structure to Build

```
alpha/
  packs/
    sre/
      __init__.py
      agents/
        log_agent.py
        metrics_agent.py
        commit_agent.py
        config_agent.py
        synthesis_agent.py
      prompts/
        log_agent.txt
        metrics_agent.txt
        commit_agent.txt
        config_agent.txt
        synthesis_agent.txt
```

---

## Implementation Checklist

### Step 1 — Environment Setup

- [ ] Install the OpenRouter SDK (OpenAI-compatible):
  ```
  pip install openai python-dotenv
  ```
- [ ] Create a `.env` file in the project root:
  ```
  OPENROUTER_API_KEY=your_openrouter_key_here
  ```
- [ ] Add `.env` to `.gitignore` — never commit API keys
- [ ] Confirm `LLMClient`, `OpenRouterClient` are importable from `alpha.llm`
- [ ] Confirm `BaseAgent` is importable from `alpha.agents.base`
- [ ] Create `alpha/packs/sre/` directory structure with `__init__.py` files

### Step 2 — LLM Response Parser Utility

Build this before writing any agent. Every agent will use it. The `LLMClient` abstraction (built in Phase 2) normalizes API calls — this utility normalizes the response text into a Pydantic model.

- [ ] Create `alpha/utils/parse.py`
  - Function: `parse_llm_json(response: str, schema: type[BaseModel]) -> BaseModel`
  - Strip markdown code blocks (` ```json ``` `) from response
  - Extract JSON using regex if LLM adds commentary: `re.search(r'\{.*\}', response, re.DOTALL)`
  - Parse with `json.loads()`
  - Validate with `schema.model_validate(data)`
  - Raise `LLMParseError` on failure with the raw response included for debugging
  - Note: this works identically for both Anthropic and Gemini responses — the `LLMClient` already normalized them to `str`

### Step 3 — Log Agent

- [ ] Implement `LogAgent(BaseAgent)` in `packs/sre/agents/log_agent.py`
  - Instantiated with `OpenRouterClient(model="anthropic/claude-sonnet-4-6")` — precision log analysis
  - Filter context signals to type `log_anomaly`
  - If no log signals: return empty `AgentResult`
  - Build user message with signal list as JSON
  - Call LLM with system prompt + user message
  - Parse response with `parse_llm_json(response, AgentResultSchema)`
  - Return `AgentResult`
- [ ] Write `prompts/log_agent.txt`:
  - Role: expert SRE log analyst
  - Constraint: reference only provided signals
  - Output: JSON schema for 1-3 hypotheses
  - Confidence guidance: 0.7+ when error pattern is unambiguous

### Step 4 — Metrics Agent

- [ ] Implement `MetricsAgent(BaseAgent)` in `packs/sre/agents/metrics_agent.py`
  - Instantiated with `OpenRouterClient(model="google/gemini-2.0-flash")` — fast numerical reasoning
  - Filter context signals to types `metric_spike`, `resource_saturation`, `metric_degradation`
  - Same LLM call pattern as LogAgent
- [ ] Write `prompts/metrics_agent.txt`:
  - Role: expert SRE metrics and resource analyst
  - Focus: resource saturation, performance degradation, cascade failure patterns
  - Confidence guidance: 0.8+ when multiple metric signals converge

### Step 5 — Commit Agent

- [ ] Implement `CommitAgent(BaseAgent)` in `packs/sre/agents/commit_agent.py`
  - Instantiated with `OpenRouterClient(model="anthropic/claude-sonnet-4-6")` — strongest at code diff analysis
  - Filter context signals to type `commit_change`
  - Same LLM call pattern
- [ ] Write `prompts/commit_agent.txt`:
  - Role: expert SRE code change analyst
  - Focus: identifying which code changes introduced the failure
  - Confidence guidance: 0.7+ when the commit signal directly explains the metric signal

### Step 6 — Config Agent

- [ ] Implement `ConfigAgent(BaseAgent)` in `packs/sre/agents/config_agent.py`
  - Instantiated with `GeminiClient(model="gemini-2.0-flash")` — lightweight key-value reasoning
  - Filter context signals to type `config_change`
  - Handle the case where no config signals exist (return empty result gracefully)
- [ ] Write `prompts/config_agent.txt`:
  - Role: expert SRE infrastructure and configuration analyst
  - Focus: configuration limits, feature flags, environment changes

### Step 7 — Synthesis Agent

- [ ] Define `SynthesisResult` in `alpha/schemas/result.py`:
  ```python
  class SynthesisResult(BaseModel):
      summary: str           # 2-3 sentence plain English explanation
      key_finding: str       # single most likely root cause
      confidence_in_ranking: float   # how certain is the synthesis
  ```
- [ ] Implement `SynthesisAgent` in `packs/sre/agents/synthesis_agent.py`
  - Instantiated with `AnthropicClient(model="claude-sonnet-4-6")` — narrative needs technical grounding
  - Receives: all signals + ranked hypotheses list
  - Builds a user message summarizing the full investigation
  - Asks LLM to synthesize a narrative
  - Returns `SynthesisResult`
- [ ] Write `prompts/synthesis_agent.txt`:
  - Role: senior SRE summarizing an investigation
  - Task: explain the incident in plain English, cite the top hypothesis
  - Do NOT invent new causes

### Step 8 — Runtime Integration

- [ ] Register all 4 parallel agents with `AlphaRuntime`:
  ```python
  runtime = AlphaRuntime()
  runtime.register(LogAgent())
  runtime.register(MetricsAgent())
  runtime.register(CommitAgent())
  runtime.register(ConfigAgent())
  ```
- [ ] After aggregation in `AlphaRuntime.execute()`, run `SynthesisAgent` with full context
- [ ] Attach `SynthesisResult` to `ExecutionResult`

---

## Prompt Engineering Reference

Use this checklist when writing any agent system prompt:

- [ ] **Role declaration:** "You are an expert SRE specializing in [domain]."
- [ ] **Task clarity:** "Your job is to generate root cause hypotheses."
- [ ] **Signal constraint:** "Base your hypotheses ONLY on the provided signals. Do not invent facts."
- [ ] **Signal reference requirement:** "Each hypothesis MUST cite at least one signal ID from the list."
- [ ] **Confidence guidance:** "Assign confidence 0.7+ only when multiple signals converge on the same cause."
- [ ] **Output format:** "Respond with valid JSON matching this exact schema: [schema]"
- [ ] **Failure handling:** "If you cannot generate a confident hypothesis, return an empty hypotheses array. Do not guess."
- [ ] **No freeform text:** "Your entire response must be valid JSON. Do not include commentary before or after the JSON."

---

## Example End-to-End Output

After running the full pipeline on `incident_b.json`, the output should look like:

```json
{
  "ranked_hypotheses": [
    {
      "label": "DB Connection Pool Exhaustion",
      "description": "Connection pool was reduced from 20 to 5 in the latest deploy. Combined with an unindexed query causing slow DB operations, the pool saturated immediately under normal load.",
      "confidence": 0.92,
      "severity": "high",
      "supporting_signals": ["sig_003", "sig_006", "sig_007"],
      "contributing_agents": ["metrics_agent", "commit_agent"]
    },
    {
      "label": "Cache Removal Causing Query Amplification",
      "description": "Removing the cache decorator from the user profile endpoint caused every request to hit the database directly, amplifying load on an already constrained connection pool.",
      "confidence": 0.87,
      "severity": "high",
      "supporting_signals": ["sig_004", "sig_005"],
      "contributing_agents": ["log_agent", "commit_agent", "metrics_agent"]
    },
    {
      "label": "Latency Cascade from Upstream Timeouts",
      "description": "With DB queries timing out, upstream services began queuing requests, causing the observed 40x p99 latency spike.",
      "confidence": 0.71,
      "severity": "high",
      "supporting_signals": ["sig_001", "sig_002"],
      "contributing_agents": ["log_agent", "metrics_agent"]
    }
  ],
  "synthesis": {
    "summary": "A deploy that reduced the DB connection pool and removed query caching combined to saturate the database under normal load. The resulting slow queries cascaded into request timeouts across the API.",
    "key_finding": "DB connection pool reduced to 5 + cache removal caused immediate saturation and latency cascade.",
    "confidence_in_ranking": 0.89
  },
  "requires_human_review": true
}
```

This is the output that wins the demo.

---

## Success Criteria

- [ ] All 5 agents are implemented and importable from `alpha.packs.sre`
- [ ] `LogAgent`, `MetricsAgent`, `CommitAgent`, `ConfigAgent` run in parallel via the runtime
- [ ] `SynthesisAgent` runs after the aggregation step (not in parallel)
- [ ] Each agent output is a valid `AgentResult` (passes judge validation)
- [ ] At least one agent cites `sig_001` (log anomaly) in its hypotheses
- [ ] At least one agent cites `sig_003` or `sig_007` (DB saturation / pool reduction)
- [ ] At least one agent cites `sig_005` (cache removal)
- [ ] The aggregator output has at least 3 ranked hypotheses
- [ ] Cross-agent agreement boosts at least one hypothesis above 0.85 confidence
- [ ] Full pipeline: `incident_b.json` → signals → parallel agents → aggregation → synthesis → structured output
- [ ] `parse_llm_json` handles LLM responses wrapped in markdown code blocks without crashing
- [ ] A single agent failure (LLM error, timeout) does not crash the pipeline

---

## Open Questions

1. ~~**LLM provider choice:**~~ Resolved: Anthropic (`claude-sonnet-4-6`) for LogAgent, CommitAgent, SynthesisAgent. Gemini (`gemini-2.0-flash`) for MetricsAgent, ConfigAgent.
2. **Synthesis agent timing:** Should synthesis run before or after the aggregator? Running after aggregation (receiving the ranked list) is architecturally cleaner — the synthesis explains the ranking.
3. **Rate limits:** LogAgent and CommitAgent both hit Anthropic simultaneously. MetricsAgent and ConfigAgent both hit Gemini simultaneously. Test concurrent requests on both keys early — before the demo.
4. **Prompt storage:** Inline strings in Python or separate `.txt` files? `.txt` files are easier to iterate on without restarting the Python process.
5. **Agent failure policy:** If `CommitAgent` fails (LLM timeout), should the runtime continue with 3 agents? (Recommendation: yes — partial results are better than no results.)

---

## Hackathon Priority

**Essential — build first:**
- [ ] LLM response parser utility (`parse_llm_json`)
- [ ] `LogAgent` with working LLM call
- [ ] `MetricsAgent` with working LLM call
- [ ] `CommitAgent` with working LLM call (most impactful for Incident B)
- [ ] All 3 agents running in parallel via the runtime
- [ ] At least 3 ranked hypotheses in the aggregated output

**Important — build second:**
- [ ] `ConfigAgent`
- [ ] `SynthesisAgent` and `SynthesisResult`
- [ ] Judge validates signal references in hypotheses

**Optional — skip if time-pressured:**
- [ ] Separate prompt `.txt` files (inline strings are fine)
- [ ] Confidence calibration testing across multiple runs
- [ ] Retry logic for LLM failures
- [ ] Multi-incident testing

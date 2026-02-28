# Phase 0 — Vision & Scope Lock

**Goal:** Prevent overbuilding. Lock the problem, user, and demo story before a single line of code is written.

---

## Why This Phase Exists

The most common hackathon failure mode: building the wrong thing fast. Phase 0 protects against it by forcing explicit decisions upfront. A bad decision here costs 10 minutes to fix. The same decision made in Phase 4 costs hours.

---

## Learning Objectives

By the end of this phase, you should be able to answer these questions cold, without hesitation:

- [ ] What problem does Alpha SRE solve, and for whom?
- [ ] What are 3 things Alpha SRE explicitly does NOT do?
- [ ] What is the single incident scenario you are demoing?
- [ ] What does a successful 3-5 minute demo look like, step by step?
- [ ] Why is it better to do one thing deeply than two things shallowly?

---

## Core Concepts

### Problem Statement

Early-stage teams move fast with AI-assisted tools, but they carry the downside: incidents are inevitable and nobody owns them. When a new feature causes a latency spike, the on-call engineer is manually sifting through logs, metrics, and recent commits — alone, under pressure, without a playbook.

Alpha SRE integrates as a coordinated AI investigation layer. It extracts objective signals deterministically, dispatches parallel specialized agents to reason over them, and returns ranked, confidence-weighted root cause hypotheses. Not a replacement for SREs — a capable substitute for teams that can't afford one yet.

### Target User

- **The on-call generalist** — a backend or full-stack engineer who deploys multiple times a week, owns incident response by default, and has no dedicated SRE to call when something breaks at 2am.
- **The technical founder or early CTO** — responsible for reliability without a platform team, needs structured investigation output they can act on, not a chatbot to prompt-engineer under pressure.
- **The lean team that deploys first and debugs second** — post-MVP, pre-scale, running on a standard stack (Postgres, Redis, FastAPI or similar). Incidents happen after deploys. MTTR is measured in hours because root cause analysis is manual and unstructured.

### 1. Vertical-First Thinking

Building a general platform before validating a vertical is a common failure mode in both startups and hackathons. Alpha's strategy is intentional:

> Build the vertical first. Let the platform emerge from it. Not the reverse.

This means the runtime (Phase 2) is built *in service of* the SRE use case (Phases 3-4). Resist the urge to make the runtime "general" before it works for anything specific.

### 2. The Product Contract

A product contract is a simple, crisp statement of:
- **Input:** What the system accepts
- **Process:** What it guarantees to do
- **Output:** What the user receives
- **Non-goals:** What it explicitly refuses to do

Alpha SRE's contract:

> Given a structured incident payload, Alpha SRE will extract objective signals, dispatch parallel specialized agents, aggregate hypotheses, and return a ranked, confidence-weighted root cause list. It requires human approval before any action is taken.

Memorize this. You will be asked it.

### 3. Non-Goals Are a Feature

Every "no" you commit to now is time and complexity you won't waste later. These are locked:

1. **No auto-remediation** — Alpha surfaces root causes and suggests fixes. It does not apply patches, roll back deploys, or modify infrastructure. Humans approve all actions.
2. **No chat interface** — Alpha is not a chatbot. You don't prompt it with questions. It runs a structured investigation and returns structured output. CLI only.
3. **Not an observability platform** — Alpha does not replace your monitoring stack. It doesn't ingest streaming metrics, set up alerts, or compete with Datadog or Grafana. It receives a structured incident payload and investigates it.
4. **No broad integration surface** — Sentry is the one intentional integration for v0.1. No Datadog connector, no Prometheus scraper, no CloudWatch pipeline. One integration done well beats five done poorly.
5. **No second incident scenario until Incident B is polished** — Depth beats breadth. The DB saturation + cache miss cascade scenario is the demo. A second scenario is out of scope until the first one is airtight.

### 4. The Demo Story Arc

A demo that wins follows a clear narrative arc:

1. **Pain** — Show the incident. Latency spiked. Error rate is climbing. The on-call engineer is panicking.
2. **Action** — Run Alpha. Agents execute in parallel. You can see them working.
3. **Revelation** — Ranked hypotheses appear. "Three root causes identified. Here's what happened."
4. **Credibility** — Each hypothesis is grounded in specific signals. Not guesses.
5. **Control** — Human approval gate. Alpha advises. Humans decide.

The goal is not to show everything. The goal is to make one scenario feel inevitable and impressive.

---

## The Demo Incident Scenario

Based on `sre_outline.md`, the recommended scenario is:

> **Incident B — The AI-Assisted Deploy**
>
> Two LLM-assisted commits ship in the same deploy. The first refactors the user profile endpoint — the generated code silently drops a `@cache` decorator it didn't know to preserve. The second adds a new feature query — the LLM writes a JOIN without knowing the table lacks an index. Every profile request now hits the database directly with a slow, unindexed query. The connection pool saturates. p99 latency spikes 4x. Users experience timeouts on profile pages within minutes of the deploy.

**Why this scenario works:**
- Realistic — exactly what happens when LLMs write code without full system context
- Two independent LLM-assisted commits compound each other, which no single engineer would immediately connect
- Three agents independently find different pieces: log errors, metric spikes, commit diffs
- The narrative arc lands hard: AI tooling caused the incident, an AI runtime found it
- Containable — Sentry error data + structured commit payload, no live infra needed

### Questions to Resolve Before Moving On

- [X] Incident B — The AI-Assisted Deploy is locked. LLM-assisted commits silently dropping cache + introducing an unindexed query. This problem will only become more common as lean teams ship fast with AI tooling. Alpha helps them recover without slowing down.
- [ ] Will the demo use fully simulated data (JSON fixtures) or a live local service? I would like to pull data from a real observability tool like Sentry to demonstrate deep integrations. However, on Sentry, we can use mock github service with the specific problem. 
- [ ] Is this a solo project or a team project? Who owns what? Team project. We have 2 ML engineers and one product manager. 

---

## Deliverables

These are documents and decisions, not code. Complete each one before moving to Phase 1.

- [X] Write a 1-paragraph problem statement (can refine from `phase_1.md`)
- [X] List your target user in 3 bullet points
- [X] Write down 5 explicit non-goals (things Alpha SRE will NOT do)
- [X] Lock the incident scenario name and brief description (1-2 sentences)
- [X] Write a step-by-step demo script (~5 minutes, walk through it aloud)
- [X] Define what "done" means for the hackathon submission

---

## Demo Script

**Total time: ~5 minutes. Practice this out loud.**

---

```
[0:00–0:30] — SET THE SCENE (pain)

  SAY:  "It's 2am. A deploy just went out. Sentry is lighting up."

  SHOW: Sentry error feed — timeouts on /api/users/profile climbing fast.
        "p99 latency just hit 4800ms. Error rate is at 31% and rising.
         You have no SRE to call. You have two recent commits, both written
         with LLM assistance. You don't know which one broke it — or if it
         was both."

  BEAT: Let that sit for a second. This is the moment your user lives in.

---

[0:30–1:00] — THE OLD WAY (make them feel the pain)

  SAY:  "Normally, you'd spend the next hour manually cross-referencing logs,
         metrics, and diffs. Hoping you find the right signal before users
         start churning."

  SAY:  "Instead, you run Alpha."

---

[1:00–1:30] — RUN ALPHA

  SAY:  "One command."

  RUN:  alpha-sre analyze --source sentry --incident INC-4821

  SHOW: Alpha pulling the Sentry incident, structuring the payload.
        "Alpha is now extracting objective signals — error rates, latency
         percentiles, commit diffs — deterministically, before any AI
         reasoning runs."

---

[1:30–2:30] — PARALLEL AGENTS EXECUTING

  SAY:  "Four specialized agents are now running in parallel."

  SHOW: Live terminal output — all four agents firing simultaneously,
        timestamps proving concurrency:

        [1.31s] LogAgent       → analyzing error patterns
        [1.31s] MetricsAgent   → analyzing latency and DB saturation
        [1.32s] CommitAgent    → analyzing recent diffs
        [1.32s] ConfigAgent    → analyzing environment changes
        [3.47s] All agents complete.

  SAY:  "Each agent sees the same signals. None of them talk to each other.
         The runtime coordinates them — they work in parallel, independently."

---

[2:30–3:30] — THE RESULTS

  SAY:  "Investigation complete."

  SHOW: Ranked hypothesis output:

        #1  DB Connection Saturation via Unindexed Query   confidence: 0.91
            → supported by: sig_002 (latency spike), sig_003 (pool saturation),
                            sig_006 (unindexed JOIN in commit a1b2c3d)
            → flagged by: MetricsAgent, CommitAgent, LogAgent

        #2  Cache Removal Amplifying DB Load              confidence: 0.85
            → supported by: sig_004 (cache hit rate drop), sig_005 (decorator
                            removed in commit a1b2c3d)
            → flagged by: LogAgent, CommitAgent

        #3  Latency Cascade from Request Queuing          confidence: 0.71
            → supported by: sig_001 (error rate spike), sig_002 (latency spike)
            → flagged by: LogAgent, MetricsAgent

  SAY:  "Three agents independently flagged the same root cause — the
         unindexed query. They didn't coordinate. The runtime aggregated their
         findings and boosted the confidence score because they agreed.
         That's not an LLM guessing. That's convergent evidence."

  SAY:  "Both commits contributed. The LLM that wrote the JOIN didn't know
         the table lacked an index. The LLM that refactored the endpoint
         didn't know the cache decorator was load-bearing. Alpha found both
         in 23 seconds."

---

[3:30–4:00] — HUMAN APPROVAL GATE

  SAY:  "Alpha advises. Engineers decide."

  SHOW: Approval prompt:

        Suggested actions:
          1. Add index on users.profile_id
          2. Restore @cache decorator on get_user_profile()

        Approve? [y/N]

  SAY:  "No automated patches. No autonomous rollbacks. Humans stay in
         control. Alpha surfaces the reasoning — you make the call."

---

[4:00–5:00] — THE PITCH

  SAY:  "This is Alpha. A deterministic runtime for coordinating parallel
         AI agents."

  SAY:  "The SRE vertical is the first proof. The runtime is the real product.
         As AI-assisted development becomes the norm — and it will — the gap
         between 'ship fast' and 'debug fast' gets worse. Alpha closes it."

  SAY:  "We're not building another LLM wrapper. We're building the
         infrastructure layer that makes parallel AI reasoning reliable,
         structured, and trustworthy."

  READY FOR QUESTIONS.
```

---

## Definition of Done (Hackathon Submission)

Done does not mean perfect. Done means **the demo script runs live without stopping.**

### Functional — these must work

- [ ] `alpha-sre analyze --source sentry --incident INC-4821` runs end-to-end without crashing
- [ ] Signal extraction produces at least 5 signals from the Sentry incident payload
- [ ] All 4 agents (Log, Metrics, Commit, Config) execute — terminal output proves they run concurrently via timestamps
- [ ] Aggregated output contains at least 3 ranked hypotheses with confidence scores
- [ ] The top-ranked hypothesis correctly identifies the unindexed query or cache removal as a cause
- [ ] Human approval gate appears after results — no automated action is taken without it
- [ ] Full pipeline completes in under 60 seconds

### Showable — these must be visible in the demo

- [ ] Terminal output is clean — no debug noise, no raw stack traces, no JSON blobs
- [ ] Agent execution is visible in real time (you can watch them fire)
- [ ] Each hypothesis shows: confidence score, supporting signal IDs, contributing agents
- [ ] The "AI-assisted commits caused this" narrative is legible from the output alone

### Answerable — a technical judge asks these, you must have answers

- [ ] "How does this differ from just asking ChatGPT?" — you can answer in 30 seconds
- [ ] "What happens if one agent fails?" — you can answer and show it
- [ ] "Why parallel agents instead of one big prompt?" — you can answer in 60 seconds
- [ ] "What's next after the hackathon?" — you have a clear one-sentence answer

---

## Success Criteria

This phase is complete when:

- [X] You can explain Alpha SRE in exactly 2 sentences without looking at notes
- [X] The incident scenario is named and described in 1-2 sentences
- [X] You have a written demo script with timestamps
- [X] You have written down at least 5 explicit non-goals
- [X] The demo data strategy is decided (Sentry integration with mock GitHub service)
- [X] Anyone on the project agrees on all of the above

---

## Open Questions

1. How much time do you have before the hackathon deadline? (This affects which phases are essential vs optional) 
- We have 24 hours. 

2. Will you use simulated data (JSON fixtures) or real local infrastructure for the demo?
- We will integrate with one platform, Sentry

3. What LLM provider will the agents use? (Anthropic Claude, OpenAI, or other?)
- We will focus on Expert Orchestration, and use a variety of ai agents according to their strenghts. 

4. Is the dashboard (Phase 6) in scope, or is CLI-only acceptable for the demo?
- Only focus on CLI for the demo. 

---

## Hackathon Priority

**Essential — do not skip:**
- [X] Lock the incident scenario
- [X] Write the demo script
- [X] Define non-goals explicitly

**Important but flexible:**
- [X] Formal product narrative document
- [X] Written problem statement

**Optional — skip if time-pressured:**
- [ ] Secondary incident scenario
- [ ] Polished pitch deck
- [ ] Brand/naming decisions

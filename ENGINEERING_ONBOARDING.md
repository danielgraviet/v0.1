# Engineering Onboarding Guide

This guide is for engineers joining Alpha SRE and contributing quickly without guessing context.

## 1) What Alpha Is (2 minutes)

Alpha is a parallel AI runtime for incident investigation.

Alpha SRE is the first vertical:
- Input: structured incident payload (`logs`, `metrics`, `recent_commits`, `config_snapshot`)
- Process: deterministic signal extraction first, then parallel AI agent reasoning
- Output: ranked root-cause hypotheses with confidence, plus human approval gate

Core architecture rule:
- `signals` are facts (deterministic, they come from real data)
- `hypotheses` are interpretations (probabilistic, comes from LLM's.)

## 2) Who It Is For (1 minute)

Primary users:
- Early-stage engineering teams
- No dedicated SRE
- Frequent deploys, high incident debugging chaos

Problem Alpha solves:
- Reduce MTTR (Mean time to resolution/repair) by replacing fragmented manual debugging with structured, parallel investigation.

## 3) What We Are Not Building (Non-Goals)

- No auto-remediation
- No chat-first UX
- Not a full observability platform
- No broad integration surface in v0.1
- No second incident scenario before Incident B is polished

## 4) First Team Meeting Agenda (45 minutes)

1. `0-10 min`: Product + architecture briefing
2. `10-20 min`: Walk through `overview.md` and `tasks/phase_0.md`
3. `20-30 min`: Walk through current repo structure and what is already implemented
4. `30-40 min`: Assign first contribution tracks (see section 8)
5. `40-45 min`: Confirm branch strategy, PR checklist, and next sync time

## 5) Ground-Zero Setup (15 minutes)

Run from repo root:

```bash
make setup
cp .env.example .env
```

Add your OpenRouter key to `.env`:

```bash
OPENROUTER_API_KEY=your_openrouter_key_here
```

Sanity checks:

```bash
make verify
make run
```

Optional live API check:

```bash
make test-live
```

## 6) Files to Read In Order (30-45 minutes)

1. `overview.md` (roadmap and strategic arc)
2. `tasks/phase_0.md` (problem statement, user, non-goals, demo story)
3. `tasks/phase_1.md` (data contracts and schema intent)
4. `runtime_outline.md` (runtime design principles)
5. `README.md` (local tooling and commands)
6. `schemas/*.py` (actual typed contract currently in code)

## 7) How To Contribute Safely

Branch and PR flow:

```bash
git checkout -b feat/<short-description>
# make changes
make verify
git add .
git commit -m "feat: <summary>"
git push -u origin feat/<short-description>
```

Before opening PR:
- Run `make verify`
- Keep scope small and single-purpose
- Update docs if behavior changes
- Add or update tests when logic changes
- Call out assumptions and open questions in PR description

## 8) First Contribution Tracks (Recommended)

Pick one lane each so work can happen in parallel.

Track A: Runtime skeleton and orchestration path
- Create core runtime files (`core/runtime.py`, `core/executor.py`, `core/registry.py`, `core/memory.py`)
- Wire a minimal end-to-end pipeline with stubs
- Ensure outputs align with `schemas/result.py`

Track B: Deterministic signal extraction
- Implement `sre` extractor modules for logs/metrics/commits/config
- Produce valid `Signal` objects
- Add deterministic tests for each analyzer

Track C: Judge + Aggregation basics
- Implement judge checks (schema validity + supporting signal references)
- Implement simple aggregation and ranking logic
- Add tests for agreement boost and dedup behavior

## 9) Team Working Agreement

- Prefer deterministic code over prompt-heavy logic for core control flow
- Keep AI agent behavior constrained by typed schemas
- No hidden side effects; keep modules single-responsibility
- Document decisions in PRs so new contributors can replay reasoning
- Default to the roadmap phases; avoid scope creep

## 10) Definition of “Ramp Complete”

An engineer is ramped when they can do all of the following:
- Explain Alpha’s value proposition and non-goals clearly
- Describe the facts-vs-interpretations architecture
- Run setup and local verification commands without help
- Make one scoped PR that passes `make verify`
- Walk through how their code fits the Phase roadmap

## 11) Quick Reference Commands

```bash
make setup      # install dependencies
make run        # run local entrypoint
make check      # syntax/import compile check
make test       # offline deterministic tests
make test-live  # live OpenRouter tests
make verify     # check + test
```

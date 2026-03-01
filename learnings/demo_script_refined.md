# Alpha SRE Demo Script (Refined)

## Narration Script

### (JACKSON) Problem
It’s past midnight. You just shipped a deploy.  
Error rates spike, login breaks, Slack is on fire, and everyone asks the same question:  
“What changed, and what broke?”

For early-stage teams, this is normal. You can ship fast, but you can’t always afford a dedicated SRE team.  
Tools like PagerDuty, Datadog, and Sentry tell you **that** something is wrong.  
**Alpha SRE tells you why, and what to do next.**

---

### (DANNY) Product Intro
This is **Alpha**: an AI-powered incident investigator for engineering teams.

Alpha integrates directly into your existing monitoring workflow, starting with **Sentry**.  
When Sentry detects a production issue, it sends a webhook to Alpha automatically.  
Alpha then pulls incident context, correlates signals across logs, metrics, commits, and config, and starts parallel analysis.

---

### (DANNY) During Live Demo
You’re now seeing a real Sentry-triggered incident flow.

1. A failure is triggered in our mock app.  
2. Sentry fires a webhook to Alpha.  
3. Alpha extracts deterministic signals first:
- log anomalies
- metric degradation
- risky code changes
- config shifts

Then Alpha runs specialized AI agents in parallel, each producing independent root-cause hypotheses.  
Finally, Alpha ranks those hypotheses and generates a synthesis summary for engineers.

---

### (CHUCK) Differentiation
Our core principle is: **facts before interpretation**.

Alpha doesn’t start by guessing.  
It grounds reasoning in deterministic evidence, then applies AI to rank likely causes.  
That reduces noise, shortens time-to-diagnosis, and helps smaller teams respond like they have an on-call SRE org.

---

### Conclusion
Reliability risk grows as shipping speed increases.  
Alpha helps startups keep velocity without sacrificing production confidence.

**Alpha is building the runtime for AI-powered incident investigation, starting with SRE.**

---

## What To Emphasize In This Demo

- Real-time **Sentry webhook integration** (not manual copy/paste).
- Cross-context reasoning (logs + metrics + commits + config).
- Parallel specialist agents + ranked output.
- Deterministic-first architecture (“facts before interpretation”).
- Practical value: faster incident diagnosis for small teams.

# Demo Script (Refined)

## (JACKSON)
It’s past midnight. Your startup just deployed new code.  
Error rates are spiking, customers can’t log in, and the Slack channel is on fire.  
With no specialized Site Reliability Engineer on payroll – your engineers scramble through logs and metrics for hours, trying to answer the simple question:  
“What broke?”

This is the reality for nearly 60,000 early-stage startups nationwide. Rapid deployment of AI-generated code and inability to pay an SRE $100,000 don’t go well together. Incidents arise; customers and revenue decline.

Today, popular softwares like Pagerduty and Dynatrance tell you something is wrong, our brand new Alpha SRE tells you why, and how to fix it.

## Begin demo
### (DANNY)
Introducing Alpha, an AI-powered incident investigator that acts like your 24/7 SRE team.

Here’s how it works:
We didn't want to reinvent the wheel. We chose to deeply integrate with the monitoring tools you already use, including Sentry, PostHog, Datadog, and New Relic.
When something breaks during deployment, Sentry notifies Alpha, and Alpha takes the investigation one level deeper.
It correlates signals across logs, metrics, commits, and configuration changes to give engineers the full picture.

## During loading
Alpha extracts objective signals from logs, metrics, commits, and configuration changes. Instead of one large monolithic LLM, it runs multiple specialized AI analysts in parallel, each generating their independent hypotheses for why things went wrong.

Alpha then aggregates those hypotheses, ranks them, and presents the user with likely root causes to their problem.

## (CHUCK)
Alpha prioritizes facts over interpretations; examining deterministic signals first, then using AI reasoning to fill in the gaps.

## Conclusion
Reliability risk is not shrinking with the size of engineering teams. Alpha ensures that rapid development doesn’t hurt your startup in the long run.

Alpha is building the runtime for AI-powered incident investigation — starting with SRE

# First 90 days as Market Connections TPM — a working plan

How I would approach the role, using the same method GridLink is built around:
**start from customer demand → map access → chase it → test → hand over a reusable connection → keep it visible.**
The plan assumes I first learn the real portfolio, so numbers below are placeholders to be replaced in week 1.

## Days 1–30: Learn the demand and the current state

**Goal: one shared, honest picture of which customer data we have, which we don't, and why.**

- Build the **coverage map**: every customer plant × every data need (metering, prices, master data, grid
  constraints…) with one status and one reason each — the *Customers & plants* view.
- Inventory existing connections: owner, route, health, known issues, undocumented manual steps.
- Shadow Customer Operations: which data questions do customers ask most? Which issues repeat?
- Meet Engineering: how connectors are built today, what is reusable, where reliability hurts.
- Meet Sales: which markets/customers are in the pipeline, and what data they will expect on day one.
- **Output:** coverage baseline (by customer, country, MW), top gaps ranked by demand, list of quick wins.

## Days 31–60: Prioritise and open the access pipeline

**Goal: a prioritised roadmap the team agrees on, and access requests moving in parallel.**

- Agree the **prioritisation model** with Product, Engineering and Sales: transparent factors (customer value
  from demand data, commercial opportunity, data importance, technical effort, access complexity) and the
  decisions it produced — documented with rationale.
- For the top 2–3 countries: complete the **access map** (who holds which data, every route, fallbacks) and
  open **access requests** with named owners and follow-up dates; involve customers where owner authorisation
  is needed.
- **Test before building:** run real requests, save evidence, write the integration spec (formats, units, time
  conventions, limits, licensing) so engineering starts with no surprises.
- Ship one quick win end to end (e.g. a public market-data source or a token-gated API already scoped).
- **Output:** roadmap with rationale, 2–3 country access maps, active request pipeline, one new connection live.

## Days 61–90: Make it repeatable and visible

**Goal: each next connection is faster than the last, and everyone can see data health.**

- Turn what worked into a **country playbook** (same steps every market) and an onboarding-report template.
- Define **health and quality thresholds** with engineering: completeness per plant, freshness vs publication
  lag, validity — so "healthy" never just means HTTP 200. Agree alerting and a runbook for Customer Operations.
- Track **lead time per step** (request → access granted → first data) to show the process is getting faster.
- Close the loop with Customer Operations: issue workflow with root cause and customer-facing update.
- **Output:** playbook v1, health dashboard and alerting, measurable lead-time baseline, 2nd connection in progress.

## How I would measure success

| Metric | Why it matters |
|---|---|
| Coverage of customer data needs (by plant count and by MW) | The outcome customers feel |
| Median time from access request to first data, per country | Shows the process improving |
| Share of connectors meeting completeness & freshness thresholds | Reliability, not just "connected" |
| Data issues detected by us before customers report them | Visibility |
| Open access requests without a scheduled next step (target 0) | Ownership and persistence |

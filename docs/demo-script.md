# 5-minute demo script

A walk-through that tells one story: *a customer's data need → why it is not met → what I am doing about it →
how the next country gets easier.* Times are approximate.

**0:00 — Cockpit (`/`)**
"This is what I'd look at on Monday. Coverage of customer data needs is 26% — 9 of 35 plant-level needs.
Four access requests are overdue for follow-up, and there are five open data issues, two of them high."

**0:40 — Customers & plants (`/coverage`)**
"Every status has a reason and a next step. Provence Solar II says *access denied*: our records say the owner
authorised access, but the DSO refuses — so they disagree. Aquitaine is waiting on the owner. German plants
have no metering route yet — hundreds of DSOs. Prices are covered in Germany from real SMARD data, blocked
elsewhere on one ENTSO-E token."

**1:30 — Prioritisation (`/prioritisation`)**
"Customer value isn't a guess: the ENTSO-E token unlocks prices for 13 plants, 288 MW, all three customers,
at almost no build effort — rank 1. Italy has the most unmet plant demand but the hardest access, so it runs
in parallel as relationship work, not as an engineering ticket."

**2:10 — Italy access map (`/countries/IT`)**
"The official route is blocked: e-distribuzione shows producers their readings in a client area but I found no
third-party API. The fallback is already mapped — owner-delegated access or the O&M SCADA export, with the
caveat that SCADA isn't revenue metering. The playbook shows where we are: 2 of 10 steps."

**2:50 — Relationships (`/relationships`)**
"The request stalled after a call routed us to client-area support. Next step: ask the customer to delegate
access. A request without a scheduled follow-up is a request that will stall — this view makes that visible."

**3:20 — API test bench (`/api-bench`)**
Run *France DSO — consent revoked*. "Before engineering builds anything, I test. Here's the 403 that explains
Provence Solar II — token redacted in the evidence. Run *ENTSO-E without a token*: a real 401 from the real
API. I record that as a verified fact on the provider."

**3:50 — Data issues (`/issues`)**
"Issues are raised at ingestion: a 36-hour gap at Côte d'Opale, estimated readings in Spain, the revoked
consent. Each one lists the affected customers and MW, competing hypotheses, the confirmed root cause, the
message Customer Operations can send — and it can't be closed without a resolution."

**4:30 — Connectors & quality (`/connectors`, `/quality`)**
"Every provider uses the same pipeline: SMARD CSV, ENTSO-E XML and two DSO JSON formats — W vs kWh, interval
end vs hour-ending, local time and DST — normalised to one schema with the original values kept. Health is
not 'HTTP 200': completeness, validity and freshness decide."

**4:50 — Close**
"Everything simulated is labelled. What's real: SMARD data, ENTSO-E's auth behaviour, and the findings —
like SMARD's missing prices on 20 November. This is how I'd run the job: start from customer demand, map
access, chase it, test it, ship a reusable connection, and keep it visible."

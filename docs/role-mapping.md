# How GridLink maps to the Market Connections TPM role

GridLink was built to rehearse the job of a **Technical Product Manager for market connections and data
integrations** at a SaaS platform for renewable-asset management: making the data customers need
*accessible, reliable and usable*, across European markets.

Each responsibility of the role is listed below with where it lives in GridLink and what it demonstrates.

| Responsibility | Where in GridLink | What it shows |
|---|---|---|
| **Expand access to energy data across European markets** | *Country access maps* (DE, FR, ES, IT, NL) | For each country: TSO, market operator, DSO landscape, bidding zones, and every known route to each data need — with fallbacks and blockers. |
| **Map how data can be accessed in a new country** | *Country access maps → Access routes* | Routes typed (public API, consent-based API, portal export, file delivery, email request, third party), each with effort, owner-authorisation flag, evidence level and source. |
| **Prioritise by customer value, commercial opportunity, technical effort** | *Prioritisation* + *Customers & plants* | Transparent scoring formula; **customer value is backed by live demand** (plants, MW and customers waiting). E.g. the ENTSO-E token unlocks prices for 13 plants / 288 MW / 3 customers → rank 1. |
| **Build relationships with providers; understand access requirements** | *Relationships* | Access requests with status and due dates, interaction log, follow-ups (overdue first), contacts by role — including **customer-side** contacts who unlock owner-delegated access. |
| **Explore alternative routes when standard channels stall** | *Italy access map*, *Relationships* | The e-distribuzione request is *stalled* (no third-party API found); the fallback route (owner delegation / O&M SCADA export) is already mapped and linked to the request. |
| **Test technical solutions; make API requests; inspect JSON/CSV** | *API test bench* | Real requests to SMARD, ENTSO-E (401 without token, verified) and MaStR, plus simulated DSO platforms. Secrets redacted; results promoted to **verified facts**. |
| **Investigate an incomplete dataset; test competing explanations** | *Data issues* | Issues raised automatically at ingestion with affected plants, customers and MW, evidence, **hypotheses**, confirmed root cause, customer update and resolution (cannot close without one). |
| **Work with engineering to deliver robust integrations** | *Connectors* + `backend/app/connectors/` | One connector contract; a new provider = one class + one mapping file. SMARD (real), ENTSO-E (token), two simulated DSO platforms all reuse the same pipeline. |
| **Turn investigations into reusable integrations, tools and processes** | *Country playbook*, *Onboarding docs*, lessons learned | Same 10-step playbook per country, lessons learned per market, 15-section onboarding report exported as Markdown/CSV, access lead-time tracked per country. |
| **Improve reliability and visibility of data collection** | *Cockpit*, *Data quality*, *Connector health* | Coverage per plant and need; connector health that does not equate HTTP 200 with healthy; quality reports after every sync. |
| **Work with Customer Operations and Sales** | *Customers & plants*, issue *customer update* | Coverage per customer account ("do you have my data?"); each issue carries the message Customer Operations can send. |
| **Become an expert in how European energy markets exchange data** | Normalisation engine, provider evidence registers | Energy vs power (MWh/interval vs MW), interval-start vs interval-end vs hour-ending, local time & DST, bidding zones (DE-LU, 7 Italian zones), consent-based access, estimated readings. |

## Real findings made while building it

These are not invented; they came from working with the real sources (dated 2026-11-21/22):

1. SMARD day-ahead prices must be requested for region **DE-LU**, not DE — the latter returns "No data".
2. SMARD published most **DE-LU quarter-hour prices for 20 Nov as "-"**; GridLink stores gaps, not zeros, and an issue tracks it.
3. SMARD **revises** recent values: a later sync updated 16 records instead of creating duplicates.
4. ENTSO-E returns **HTTP 401** with an acknowledgement document without a token; its help-centre pages refuse automated reads (403), so facts from them are labelled *assumption* until checked manually.
5. Enedis Data Connect requires **customer consent (OAuth) and a prior contract**; MaStR offers a **daily public bulk export** plus an API-key web service (100,000 calls/day); no third-party API for producer metering was found on e-distribuzione's site.

## What is simulated

Customers, plants, metering-point IDs and plant-level production data are **fictional**, as are the two
DSO platforms (modelled loosely on publicly described French and Spanish behaviour; field names are
illustrative). Everything simulated is stored with `data_origin = "simulated"` and labelled in the UI.
Market data from SMARD is real.

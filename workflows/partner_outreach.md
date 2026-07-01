# Workflow: Competitor Partner Discovery + Outreach

## Objective
3-agent pipeline that finds competitor partners, enriches their contact info (emails), and pushes everything to the Partnership Leads Google Sheet. All free tools.

**Agent 1** — Auto-discovers new competitors (viAct alternatives) → adds to "Competitors" tab.
**Agent 2** — Given a competitor, finds their partners across 6 sources.
**Agent 3** — Given a partner website, finds their contact email using a 4-tier cascade.

Human-in-the-loop points:
- User marks new competitors as `Track` / `Skip` in the Competitors tab.
- User marks partners as `Shortlist` / `Done` in the individual competitor tabs.
- Gmail drafts are deferred to a follow-up iteration.

## Inputs
- `competitor` — slug from the competitor map (e.g., `openspace`, `matterport`)
- `--all` flag — loop over every competitor in the map

## Outputs
- Rows appended to the matching tab in the Partnership Leads sheet (`PARTNER_SHEET_ID`)
- Existing rows are NOT overwritten — dedup by Website domain
- Status column on new rows left blank; user sets `Shortlist` manually

## Sheet structure (v2)

### Competitors tab = master list, single source of truth

Every competitor (existing + newly discovered) lives in the `Competitors` tab. Columns:
`Name | Website | Category | Description | Discovered At | Discovered Via | Status`

- Agent 1 auto-seeds the 14 pre-existing competitors with `Status = Track` on first run (idempotent).
- Agent 1 also appends newly-discovered competitors (Tavily/G2/Capterra) with blank Status.
- User marks each row: `Track` (process), `Skip` (ignore), or blank (pending decision).

### Per-competitor tabs — auto-created

Each `Status = Track` row's `Name` column drives the tab name. When Agent 2 runs:
- If a tab with that exact name exists → append new partner rows (dedup by domain preserves existing).
- If tab doesn't exist → auto-created with the `PARTNER_COLUMNS` header row.

Per-competitor tab columns:
`Company Name | Description | Website | Phone Number | Email | Address | Country | Status | Email Source | Discovered Via | Discovered At`

Agent fills all except **Phone Number** (user's manual column) and **Status** (user marks `Shortlist` / `Done`).

## Pipeline phases

### Phase 1 — Partner discovery (6 sources, Agent 2)

Runs in priority order. Same URL scraped by multiple sources is deduped.

| Src | How | Purpose |
|---|---|---|
| A1 | `<domain>/sitemap.xml` → LLM ranks URLs by partner-keyword score → scrape top 3 | Catches non-standard partner page paths |
| A2 | Homepage fetch → extract `<a>` links → filter by anchor/URL keyword (partner/integration/customer/alliance/ecosystem) → scrape top 3 | Catches partner nav links even if not in sitemap |
| A3 | Static URL fanout: `/partners`, `/integrations`, `/partner-program`, `/marketplace` | Baseline fallback for standard sites |
| A4 | Tavily site-search: `"<competitor> partners"` with `include_domains=[<domain>]` | Catches deep pages Google indexes but sitemap misses |
| A5 | Tavily news search: `"<competitor>" partners with` | Press releases and partnership announcements |
| A6 | Static URL fanout: `/customers`, `/case-studies`, `/clients` | Customer logos and case-study company names |

**Data quality gate**: LLM extraction uses temperature=0.1. Each company gets `confidence ∈ {high, medium, low}`. Only `high` + `medium` are kept.

Dedup across all 6 sources by normalized company name.

### Phase 2 — Contact enrichment cascade (Agent 3, 100% free)

For each discovered partner with a website, run `scrape_partner_contact.scrape_contact(website, company_name)`. The cascade stops as soon as an email is found:

| Tier | Method | Coverage | Setup |
|---|---|---|---|
| **1** | Website scrape: `/contact`, `/contact-us`, `/about`, `/about-us`, `/` — regex + `mailto:` + Cloudflare `data-cfemail` decoder + `[at]/[dot]` de-obfuscation | ~50% | Built-in, free |
| **2** | Tavily search: `"@<domain>" contact email` + `"<company>" contact email` — filters to emails on partner's own domain | +10–15% | Existing key |
| **3** | Pattern guess: `partnerships@`, `sales@`, `contact@`, `info@`, `hello@`, `bd@` + MailboxValidator API verification | +15–20% | `MAILBOXVALIDATOR_API_KEY` (100/day free, needs signup) |
| **4** | WHOIS registrant email (`python-whois`) — fallback for domain owner | ~+5% | `pip install python-whois` |

Address + country: Groq LLM extraction from Tier-1 scraped text (runs regardless of email success).

**Data quality**: `email_source` column tracks which tier produced the email → `scraped` / `tavily` / `pattern_verified` / `whois`. Never writes an unverified guess.

Explicitly NOT used: Apollo, Hunter.io, Snov.io, Clearbit — paid tools declined by user.

Expected combined coverage (all 4 tiers): 70–85% of partners with a valid email.

### Phase 3 — Sheet push
- Read existing rows from the competitor's tab
- Dedup new partners by Website domain (case-insensitive, strip `www.`, ignore protocol)
- Append only NEW rows
- Set `Discovered At` = today; `Discovered Via` = source tag (A/B/C); leave Status blank

### Phase 4 — Manual review (user)
User opens the sheet, fills missing email/phone where needed, sets `Status = Shortlist` on the rows worth contacting.

### Phase 5 — Gmail drafts (DEFERRED to v2)
Will read shortlisted rows, generate personalized email per row, create Gmail drafts for user to review and send. Needs Gmail OAuth `gmail.compose` scope added.

## Edge cases

- **Competitor has no /partners page**: Firecrawl returns empty for partners URL; fall through to case studies + Tavily news only. Log warning.
- **All 3 sources empty**: log error, write nothing to sheet, exit with code 1 so CI/cron flags it.
- **LLM extracts a "partner" that's actually the competitor itself**: filter out names matching the competitor in the dedup step.
- **Same partner appears across multiple competitors**: that's fine — it lives once per competitor tab. Cross-competitor dedup is intentionally NOT done (the same SI partnering with Openspace AND Matterport is a stronger signal, both worth tracking).
- **Sheet tab doesn't exist yet**: skip with warning (don't auto-create; the user controls which competitors are tracked).

## Tools

| Tool | Purpose |
|---|---|
| `tools/discover_partners.py` | Phase 1 (all 3 sources) + Phase 3 (sheet push). One-shot per competitor. |
| `tools/push_to_sheets.py::push_partners()` | Phase 3 write — dedup + append to competitor tab |
| `partner_pipeline.py` (root) | CLI entry: `--competitor <slug>` or `--all` |

## Required env vars
- `FIRECRAWL_API_KEY` — already configured
- `TAVILY_API_KEY` — already configured
- `GROQ_API_KEY` or `GOOGLE_API_KEY` — for LLM extraction (already configured)
- `GCP_SERVICE_ACCOUNT` or `credentials.json` — sheets auth (already configured)
- `PARTNER_SHEET_ID` — **NEW**: `1Q2XJZ2STaCN94DK4JEnS1mHkrgILfFljjNCc1dy_5qw` (add to .env)

## Running

```bash
# One competitor
python partner_pipeline.py --competitor openspace

# All competitors (loops in order, ~2-3 min each)
python partner_pipeline.py --all
```

## v2 roadmap (deferred)
1. Apollo enrichment for missing email/phone/employee count (needs `APOLLO_API_KEY`)
2. Gemini industry-fit classifier + geo-priority tagging
3. Gmail draft generation for shortlisted rows (needs OAuth `gmail.compose` scope)
4. Streamlit UI button under "Partner Outreach" mode
5. Scheduled run (weekly GitHub Actions) — only adds NEW partners since last run

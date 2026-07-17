# Partners Pipeline — Changelog & Working Spec

**Owner**: marketing@viact.ai
**Purpose**: End-to-end AI agent (Agent 11) that finds viAct's competitors,
extracts their partners/customers, discovers websites, collects emails +
contact info, and pushes only BD-relevant industrial-safety leads to the
Partnership Leads Google Sheet.

> **Rule**: Every time an improvement or fix is shipped, add a new section
> at the top of the changelog (below the "Canonical Pipeline" section).
> Keep the WHY, the WHAT, and the FILES touched. Newest at top.

---

## Canonical Pipeline (source of truth)

User's confirmed sequence — every improvement must respect this order:

| # | Stage | What produces | Main file |
|---|-------|---------------|-----------|
| 1 | Find **competitors** | Rows in Competitors tab (`Status=Track`) | `tools/discover_competitors.py` |
| 2 | Find each competitor's **partners** | Partner objects (name only, initially) | `tools/discover_partners.py` (6 sources) |
| 3 | Extract partner **Name + Description** | LLM extraction via `EXTRACT_PROMPT` + **viAct-relevance filter** | `tools/discover_partners.py` |
| 4 | Discover partner **Website** | Real URL on partner's OWN domain | `tools/enrich_partners.py::_find_website_via_search` |
| 5 | Collect **Email** — website first, then footer, then Facebook / LinkedIn, then DDG, then WHOIS | 5-tier cascade | `tools/scrape_partner_contact.py::scrape_contact` |
| 6 | Fill **remaining fields**: Phone, Address, Country | LLM + regex + TLD map | `tools/fill_missing_fields.py` |

**Sheet schema** — 8 user-visible columns:
Company Name | Description | Website | Phone Number | Email | Address | Country | **Relationship** (v4.11 — Customer / Channel Partner / Integration / Unknown).
Internal columns after: Status, Email Source, Discovered Via, Discovered At.

**Partner definition (v4.13)** — only two relationship types are extracted;
Customers are explicitly REJECTED:
- **Channel Partner** — reseller, distributor, VAR, systems integrator
- **Integration** — technology / API / marketplace partnership

**viAct scope** (confirmed from `workflows/viact-web-design.md` +
`workflows/industry_page.md`): AI industrial safety + video analytics
platform serving **5 verticals** — Construction, Manufacturing, Mining,
Oil & Gas, Logistics. Buyers = EHS Directors, HSE Managers, Plant Managers,
Safety Officers.

---

## Changelog

### v4.14.1 — Bugfix: escape curly braces in EXTRACT_PROMPT example

**Why**: v4.14 shipped with an unescaped example line
`Each line looks like: - {Company Name} [{Section Type}]`. Python's
`.format()` treated `{Company Name}` as a template placeholder and raised
`KeyError('Company Name')` — NeoEHS / VIS Systems / Pelco chain all failed
with "DISCOVERY FAILED: 'Company Name'".

**What**: Doubled the braces so they render as literal `{ }` in the final
prompt: `- {{Company Name}} [{{Section Type}}]`.

**Files**:
- `tools/discover_partners.py` — one-char fix in EXTRACT_PROMPT

---

### v4.14 — Image-alt partner extraction (catches logo-only partner sections)

**Why**: Many partner pages show partners as LOGOS with JS tabs
(Softdesigners is the poster child — Technology Partner / Implementation
Partner / Channel Partner tabs each hiding image logos). Firecrawl / Jina
flatten these to plain text, losing alt tags. v4.13 missed all 6 real
Softdesigners partners (Intel, Microsoft, Wayindia, TSSPL, Botaxis,
Duragen) and returned zero.

**What**:
1. `_extract_partner_logos_from_html(url)` — fetches raw HTML via `requests`,
   finds section markers (`Technology Partner`, `Implementation Partner`,
   `Channel Partner`, `Integration Partner`, `Reseller Partner`,
   `Our Partners`, `Trusted Partners`, `Strategic Partner`), and for each
   `<img alt="X">` after the first marker maps to the CLOSEST PRECEDING
   section marker. Cleans WordPress image ID suffixes (`-e12345678`,
   `-logo`, `-png`, `-removebg-preview-1`). Rejects junk alts
   (`logo`, `icon`, `Client 1`, etc.).
2. `_scrape_urls()` — after scraping each URL, injects a
   `--- v4.14 STRONG PARTNER SIGNALS ---` block at the top of the markdown
   with the extracted logo list.
3. `EXTRACT_PROMPT` — recognizes the STRONG PARTNER SIGNALS block as
   authoritative. Maps section type → relationship:
   `Technology / Integration Partner` → `Integration`;
   `Implementation / Channel / Reseller / Strategic / Partner` → `Channel Partner`.

Verified on Softdesigners: all 6 partners extracted with correct sub-
classification, matching the user's screenshots exactly.

**Files**:
- `tools/discover_partners.py` — logo helper, `_scrape_urls` injection,
  EXTRACT_PROMPT signals block

---

### v4.13 — Partner = Channel Partner OR Integration (not just Channel)

**Why**: v4.12 was too narrow — only Channel Partners passed the filter.
But Autodesk on OpticVyu IS a partner (integration via Autodesk Construction
Cloud), just not a reseller. Marketplace / integration listings ARE
partnerships. User correction: "Autodesk and Executive Eye Inc. ARE
partners, extract them like these."

**What**:
1. `EXTRACT_PROMPT` — v4.13 block defines TWO partner types:
   TYPE A = Channel Partner (reseller/distributor/VAR/SI),
   TYPE B = Integration (marketplace/API/tech partner including
   "OpticVyu available on Autodesk Construction Cloud" style listings).
   Only Customers are rejected.
2. `_extract_companies()` — HARD FILTER now accepts
   `relationship in {"Channel Partner", "Integration"}`.
3. Removed v4.10 REVERSE-LISTING DETECTION (was wrongly rejecting
   legitimate integration partnerships). Replaced with a note explaining
   marketplace listings ARE partnerships.
4. Restored Autodesk row on OpticVyu tab (relationship = Integration).

**Files**:
- `tools/discover_partners.py`

---

### v4.12 — Channel Partners ONLY (superseded by v4.13)

**Why**: User's explicit scope: "bass hame partner chaiye baki kuch nahi
chaiye yaad rakho bas parters". Only Channel Partners (resellers,
distributors) should appear.

**What**: EXTRACT_PROMPT CHANNEL-PARTNER-ONLY FILTER; hard-filter
`_extract_companies()` to reject anything except `Channel Partner`.
`filter_viact_relevance.py` CLASSIFY_PROMPT gets a v4.12 requirement note.

**Superseded by v4.13** — Integration partners were incorrectly rejected;
v4.13 broadens to include them.

**Files**:
- `tools/discover_partners.py`
- `tools/filter_viact_relevance.py`

---

### v4.11 — Relationship column (Customer / Channel Partner / Integration / Unknown)

**Why**: Manager audit surfaced naming confusion — tabs are called
"partners" but most rows are actually the competitor's CUSTOMERS (L&T on
OpticVyu tab, Skanska on Openspace tab). Sheet should be honest about
what each row IS.

**What**:
1. `EXTRACT_PROMPT` — RELATIONSHIP CLASSIFICATION block. LLM tags each
   company as `Customer` / `Channel Partner` / `Integration` / `Unknown`.
2. `_extract_companies()` — normalizes the relationship field.
3. `PARTNER_COLUMNS` — appended "Relationship" as column L. Existing rows
   unaffected (new column shows up via `_ensure_partner_columns()` on
   next tab update).
4. `push_partners()` — writes `p["relationship"]` at column L.

Zero new API cost — classification piggybacks on existing LLM extraction.

**Files**:
- `tools/discover_partners.py`
- `tools/push_to_sheets.py`

**Note**: This version allowed all 4 relationship types. v4.12/v4.13
narrow the extraction to just Channel Partner + Integration.

---

### v4.10 — 4 targeted fixes from OpticVyu tab audit

**Why**: OpticVyu tab audit surfaced 4 recurring data quality bugs:
(a) Procore/Autodesk appearing as OpticVyu partners — actually OpticVyu is
LISTED on their marketplaces (reverse relationship).
(b) Lodha (real-estate co) matched `mangalprabhatlodha.com` (chairman's
politician personal site) — namesake trap.
(c) Executive Eye Inc website set to `aptoide.co` (an app-store link).
(d) Names like Spacematrix, Lisual, GMR extracted with NO description AND
NO website — pure noise.

**What**:
1. `EXTRACT_PROMPT` — REVERSE-LISTING DETECTION block (**later reverted
   in v4.13** — marketplace listings ARE partnerships).
2. `_NOT_A_WEBSITE_DOMAIN` — added app-store / marketplace domains:
   `aptoide.com`, `aptoide.co`, `apps.apple.com`, `play.google.com`,
   `marketplace.procore.com`, `appexchange.salesforce.com`,
   `appsource.microsoft.com`, `workspace.google.com/marketplace`,
   `shopify.com/apps`, `wordpress.org/plugins`.
3. `_verify_website_belongs_to_company()` — reject if page metadata
   contains personal-site signals: "MLA of", "member of parliament",
   "author of", "artist", "personal blog", "born on/in".
4. `_extract_companies()` — drop rows where BOTH description AND website
   are missing (name-only rows have insufficient confidence).

Cleanup: 8 bad rows removed from OpticVyu (Procore, Autodesk, Lodha,
Executive Eye, Spacematrix, Lisual, GMR, Rhenus Logistics).

**Files**:
- `tools/discover_partners.py`
- `tools/enrich_partners.py`

---

### v4.9.2 — janed/johne placeholder patterns

**Why**: Autodesk enrichment leaked `janed@populous.com` — the "jane +
first-letter" concat pattern (janeD, janeE, janeS, janeB, janeP,
johnD, etc.) wasn't in earlier filters.

**What**: Additions to `PLACEHOLDER_LOCAL_PARTS` — janed, janee, janes,
janeb, janep, johnd, johne, johns, johnp, johnb. Also cleared the
leaked bad email from Autodesk (Populous row).

**Files**:
- `tools/scrape_partner_contact.py`

---

### v4.9.1 — firstlast/first.last placeholder patterns

**Why**: Procore enrichment leaked `firstlast@unitedrentals.com` — the
concatenated "firstlast" pattern wasn't in v4.4's flast/f.last filter.

**What**: Added `firstlast`, `first.last`, `firstname.last`,
`first.lastname`, `lastname.firstname`, `last.first`, `firstinitial`
to `PLACEHOLDER_LOCAL_PARTS`. Also cleared the leaked bad email from
Procore's United Rentals row.

**Files**:
- `tools/scrape_partner_contact.py`

---

### v4.9 — Whitespace-variant dedup + batch filter + cross-vendor detector

**Why**: (a) `Rite Hite` and `RiteHite` both landed in Voxel — dedup was
case+suffix aware but not whitespace-collapsing. (b) v4.8 filter was only run
on Voxel — Autodesk, Procore, Cryotos, Openspace, Matterport, ClickUp,
Trimble, Intenseye, Protex, and others still carried pre-filter noise.
(c) A partner appearing across multiple competitor tabs is a strong buying
signal — no way to see this before.

**What**:
1. `_norm_name_collapsed()` in `tools/push_to_sheets.py` — strips ALL
   non-alphanumeric characters. Dedup set now stores both the "clean-with-
   spaces" and "collapsed" forms. Rejects whitespace-variant duplicates on
   push.
2. `filter_viact_relevance.py --all` — batch mode iterates every Track-
   status competitor tab, classifies each row, deletes non-relevant ones.
3. `tools/detect_cross_tab_leads.py` — reads all competitor tabs, finds
   partners appearing in 2+ tabs, writes a new `Cross-Vendor Leads` tab
   with columns Company Name | Website | Email | Also In | Signal Strength
   ("MEDIUM" for 2 tabs, "HIGH" for 3, "VERY HIGH" for 4+). Uses collapsed-
   name matching so whitespace variants merge.

**Files**:
- `tools/push_to_sheets.py` — dedup normalization
- `tools/filter_viact_relevance.py` — `--all` batch mode
- `tools/detect_cross_tab_leads.py` (new)

**Ran on**: 16 Track-status competitor tabs. Also generated `Cross-Vendor
Leads` tab.

---

### v4.8 — Correct viAct scope (5 verticals, not just construction)

**Why**: v4.7 filter was too narrow — treated viAct as construction-only.
Actual viAct scope is **industrial safety across 5 verticals**: Construction,
Manufacturing, Mining, Oil & Gas, Logistics.

**What**: Expanded `viact_relevant` classification to include:
- Manufacturing plants of any kind (auto parts, glass, CPG bottling, food
  processing, chemicals, electronics)
- Cold storage warehouses (Americold-type)
- Ports & terminals (DP World, APM Terminals, Ceva)
- Logistics 3PL / fulfillment warehouses

Still rejects: retail STORES only (not their warehouses), banks/VC, insurance,
hospitality, generic SaaS, consumer products, telecom, media, healthcare.

Ran cleanup on Voxel tab: 26 truly-irrelevant rows removed, 19 legitimate BD
leads retained.

**Files**:
- `tools/discover_partners.py` — EXTRACT_PROMPT rewritten
- `tools/filter_viact_relevance.py` — CLASSIFY_PROMPT mirrors the EXTRACT rules

---

### v4.7 — viAct-relevance filter (first version — later corrected in v4.8)

**Why**: Voxel run mai retail (Macy's), CPG (Clorox), logistics (DP World),
cold storage (Americold), insurance (Tokio Marine) sab sheet mai aa rahe the
— none actionable for viAct BD. User: "wo he sheet mai add karna jo viAct
ke kaam aa sakte hai".

**What**: Added `viact_relevant: yes/no` field to LLM extraction output.
Partners tagged `no` are dropped before push.

**Files**:
- `tools/discover_partners.py` — EXTRACT_PROMPT + `_extract_companies()` filter

**Superseded by v4.8** — scope was too narrow.

---

### v4.6 — Tighter phone regex + expanded directory blocklist

**Why**: Voxel run mai junk phones (`285121676`, `42382906589366`) as raw
digit blobs from JSON/JS leakage. Also Carlex Glass mistakenly got
`glassglobal.com` (an industry directory).

**What**:
1. `_normalize_phone()` — reject raw digit blobs (no `+`, no dash, no space,
   no paren, no dot) UNLESS they match exact US-style 10 or 11 digits with
   valid area code.
2. `_DIRECTORY_HINTS` — add glassglobal.com, glassmagazine, construction-
   review, logisticsmgmt, industryweek, prnewswire, businesswire, trademap,
   panjiva.
3. `tools/cleanup_voxel_noise.py` — extended to also purge rows with junk
   Website substrings.

**Files**:
- `tools/scrape_partner_contact.py` — phone regex
- `tools/enrich_partners.py` — directory blocklist
- `tools/cleanup_voxel_noise.py` — one-off cleanup script

---

### v4.5 — Enforce canonical sequence (Stage 4 before push)

**Why**: Before v4.5, `partner_pipeline.py::run_one` pushed rows with BLANK
Website, then Agent 3 filled Website + Email later. If Agent 3 crashed mid-
run, some rows stayed name-only. Doesn't match user's canonical sequence
(name → description → **website** → email → rest).

**What**: Added Stage 4 loop in `run_one()` between `discover_partners()` and
`push_partners()` — calls `_find_website_via_search()` for every partner
before push. Sheet row appears complete (Name+Desc+Website) on first write.

**Files**:
- `partner_pipeline.py` — Stage 4 loop; import `_find_website_via_search`

---

### v4.4 — Correct partners + correct websites

**Why**: LLM was extracting products (SAP Hana, SAP Ariba) and investors
(HG Ventures) as partners. Website discovery was picking spam sites
(`sporting-gsale.com`), staging URLs, and `.gov` mismatches (Motus →
motus.dot.gov).

**What**:
1. **EXTRACT_PROMPT reject rules** — products, VCs, law firms, PR agencies,
   recruiters, gov agencies (unless case-study context). Dedup at parent-
   brand level (SAP Ariba + SAP Hana → SAP once).
2. **Website discovery filters** — reject staging/dev/beta/test subdomains,
   spam patterns (`-gsale`, `-deal`, `-shop-`, `-buy-`), `.gov`/`.edu`/`.mil`
   unless partner name has government/university keywords.
3. **Placeholder email additions** — `flast@`, `doej@`, `f.last@`
   (First-Last / Doe-John patterns leaked in Voxel v4.3).

**Files**:
- `tools/discover_partners.py` — EXTRACT_PROMPT reject rules
- `tools/enrich_partners.py` — website discovery filters
- `tools/scrape_partner_contact.py` — PLACEHOLDER_LOCAL_PARTS

---

### v4.3 — Footer priority + direct Facebook/LinkedIn email extraction

**Why**: User pointed out emails should come from partner's own website —
usually **footer** or **Contact Us** or **Facebook About**. Current tier
cascade was missing footer priority and only searching Google's index for
social pages (missing About-section emails).

**What**:
1. `_extract_footer_html()` — pull just the `<footer>` block (or `.footer`
   div, or bottom 25% of page as fallback). Emails found here get `-15`
   scoring bonus (stronger than partner-domain bonus).
2. `_fetch_facebook_about()` + `_fetch_linkedin_about()` — try slugged URLs
   (`facebook.com/<slug>/about`, `linkedin.com/company/<slug>/about/`) via
   Jina Reader (handles JS). Wrong-slug matches neutralized by v4.2 strict
   domain filter downstream.
3. **Extended CONTACT_PATHS** — added `/team`, `/company`, `/legal`,
   `/support`, `/imprint`, `/impressum`, `/kontakt` for German B2B and
   legal-notice coverage.

**Files**:
- `tools/scrape_partner_contact.py`

---

### v4.2 — Strict domain match for emails

**Why**: Sheet had cross-domain email contamination — `Americold →
mmayer@iron.markets` (Iron Markets is a media publication mentioning
Americold, not their email). 102 such rows cleaned.

**What**: `_pick_best_email()` now enforces strict domain match — email's
domain MUST equal `partner_domain` (or be a subdomain). Rejects any email
belonging to a third party even when it appears in the partner's context.
Kept legitimate rebrands (DLT → TDSynnex, MASS → ModelOfArchitecture).

**Files**:
- `tools/scrape_partner_contact.py::_pick_best_email`

---

### v4.1 — Image asset URLs rejected as emails

**Why**: Emails like `3asset-5@2x.png` and `logo1_185x@2x.png` were leaking
as valid emails (captured src attributes).

**What**: In `_extract_emails()`, reject candidates whose domain ends in
`.png`/`.jpg`/`.svg`/`.css`/`.js` or contains `@2x.`/`@3x.`/`@1x.` patterns.

**Files**:
- `tools/scrape_partner_contact.py::_extract_emails`

---

### v4.0 — TLD-based country fallback + Agent 3.5 (fill missing fields)

**Why**: Country column often blank because LLM extraction from page text
missed it. But TLD gives strong hint (`.co.uk` → UK, `.de` → Germany).

**What**:
1. Added `_country_from_tld()` with `_TLD_TO_COUNTRY` + `_COMPOUND_TLDS` map.
2. Introduced `Agent 3.5` (`tools/fill_missing_fields.py`) — after Agent 3
   completes, fills any remaining blank Description / Address / Country /
   Phone via Groq 8B model. Chained into `--daily` mode.

**Files**:
- `tools/fill_missing_fields.py` (new)
- `tools/enrich_partners.py` — TLD helper
- `partner_pipeline.py` — chain 3.5 after 3

---

### v3.9 — Phone regex hardening

**Why**: ISO dates (`2024-02-16`) and decimals (`15.6091309`) were being
extracted as phones. YYYYMMDD product codes too.

**What**: `_normalize_phone()` rejects:
- YYYY-M-D, D-M-YYYY, YYYY.M.D patterns
- Decimals with 6+ trailing digits
- Digit sequences starting with a year (19xx / 20xx)
- Trailing junk chars stripped aggressively

**Files**:
- `tools/scrape_partner_contact.py::_normalize_phone`

---

### v3.8 — Website verification tightening

**Why**: Namesake mismatches — Heirloom (climate carbon capture) was matching
Heirloom (tiny homes). `.gov` and directory sites leaked through.

**What**:
- `_verify_website_belongs_to_company()` — LLM confidence check
- `_is_wrong_website()` — sanity gate before scrape
- Extended `_NOT_A_WEBSITE_DOMAIN` (crunchbase, g2, capterra, RocketReach,
  etc.) and `_DIRECTORY_HINTS` (opencorporates, bizapedia, hoovers, etc.)

**Files**:
- `tools/enrich_partners.py`

---

### v3.7 — Anti-namesake + description hint

**Why**: DDG returns wrong company when name is common. e.g., Voxel might
return voxel.ai OR voxel.io (crypto).

**What**: `_find_website_via_search()` accepts `context_hint` — pulls
disambiguating words from the partner's description column (e.g., "climate
carbon capture" for Heirloom) to steer the DDG query.

**Files**:
- `tools/enrich_partners.py`

---

### v3.5 — DuckDuckGo replaces Tavily; placeholder email filter

**Why**: Tavily monthly quota was going to run out; DuckDuckGo (`ddgs`) is
free unlimited. Also many email-finder sales pages leaked sample patterns
like `john.doe@company.com` into the results.

**What**:
1. `_tavily_email_search` internally now calls `_ddg_search()`.
2. `_social_email_search` same swap.
3. `PLACEHOLDER_LOCAL_PARTS` set — 40+ patterns rejected in `_clean_email()`
   (john.doe, first.last, jsmith, jsmith123 with trailing-num variants).

**Files**:
- `tools/scrape_partner_contact.py`
- `tools/discover_partners.py`
- `tools/discover_competitors.py`
- `requirements.txt` — `ddgs>=1.0.0`

---

### v3.4 — Tier 5 social media email search

**Why**: Small B2B partners often have Facebook About with contact email but
no such info on website. Website-only cascade (Tiers 1-4) missed these.

**What**: Added Tier 5 in `scrape_contact()` — DDG-searched public FB /
LinkedIn / X / Instagram profiles for email snippets. Detects social source
via URL and sets `email_source` accordingly.

**Files**:
- `tools/scrape_partner_contact.py`

---

### v3.3 — Weekday-only cron for content workflows

**Why**: Weekends off for content agents. Partner Outreach stays 7-day.

**What**: `daily_report.yml` and `weekly_viact.yml` cron changed to Mon-Fri
only (`* * * 1-5`). Partner Outreach workflow unchanged.

**Files**:
- `.github/workflows/daily_report.yml`
- `.github/workflows/weekly_viact.yml`

---

### v3.2 — GitHub deploy (secrets + cron)

**Why**: Local pipeline needed to run on a schedule.

**What**: Added `PARTNER_SHEET_ID` GitHub secret. Committed Agent 11 files
and `.github/workflows/weekly_partner_outreach.yml` — daily 6:30 AM IST.

**Files**:
- `.github/workflows/weekly_partner_outreach.yml`

---

### v3 — Competitor-domain guard + noise filter

**Why**: When a partner is listed on the competitor's own website (e.g.,
`autodesk.com/integrations/partner/360sync`), scraping returned Autodesk's
email, not the partner's. Result: 75% of Autodesk-tab emails were wrong.

**What**:
1. `scrape_contact(website, company_name, competitor_domain)` — skip Tier 1
   + Tier 2 when partner's site is on competitor's own domain.
2. Reject noise partners (Trustpilot, G2, Capterra, GoDaddy, SAP) in
   `discover_partners._process()`.
3. `tools/clean_partner_rows.py` — one-off cleanup of 146 buggy rows.

**Files**:
- `tools/scrape_partner_contact.py`
- `tools/discover_partners.py`
- `tools/clean_partner_rows.py`

---

### v2 — Competitors tab as source of truth

**Why**: v1 had a hardcoded `COMPETITOR_MAP` + a Competitors tab — dual
source of truth. New partners in `Status=Track` needed manual dedup + manual
tab creation.

**What**:
1. `_seed_existing_competitors()` — auto-seed the 14 hardcoded competitors
   into Competitors tab with `Status=Track`.
2. `push_partners()` — auto-create competitor tab with header if missing.
3. `--all-agents` reads Competitors tab (Status=Track), not `COMPETITOR_MAP`.

**Files**:
- `tools/discover_competitors.py`
- `tools/push_to_sheets.py`
- `partner_pipeline.py`

---

### v1 — Initial 3-agent build

Agent 1 (competitor discovery) + Agent 2 (partner extraction, 6 sources) +
Agent 3 (email cascade, 4 tiers). Free stack only — Firecrawl / Jina /
Groq / DDG.

**Files**: `tools/discover_partners.py`, `tools/discover_competitors.py`,
`tools/scrape_partner_contact.py`, `tools/push_to_sheets.py`,
`partner_pipeline.py`.

---

## Utility scripts

| Script | Purpose |
|--------|---------|
| `tools/cleanup_voxel_noise.py` | One-off — delete known-noise rows and rows with junk website substrings from a competitor tab |
| `tools/filter_viact_relevance.py <TabName> [--dry-run]` | LLM-classify existing rows for viAct-BD relevance; delete "no" rows (respects v4.8 5-vertical scope) |

**Cost of running utilities**: ~40 LLM calls per tab (Groq 70B model,
cheap). Groq daily token budget is enough for ~10 tab runs.

## Deploy

- Every commit auto-picks-up on **kal ki 6:30 AM IST cron** (`weekly_partner_outreach.yml`)
- No new env vars or secrets needed for any v4.x change
- Zero paid API dependencies — free stack throughout

## Contact / owner

marketing@viact.ai — anything unexpected in the sheet, file a Slack message
with the row number + tab name.

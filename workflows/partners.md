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

**BD-outreach goal (v4.15.15 clarification from manager 2026-07-23)**:
The `new emails` aggregated outreach list should be built from
**Channel Partner rows ONLY**. Manager said verbatim: *"Hume kharidna
thodi hai — partners dhundh rahe hai"* (we're not buying, we're looking
for resellers who can sell viAct too).
- ✓ Include: named channel partners / authorized resellers / systems
  integrators / VARs / distributors (small-to-mid regional services
  companies whose whole business is reselling third-party software —
  REVTech, SICA, Inforica are the archetype)
- ✗ Exclude from outreach list even if extracted correctly:
  - Integration-type tech partners that are themselves solution vendors
    (BriefCam, SafetyIQ, Autodesk, Fieldwire, other AI vision / EHS
    software companies) — they compete with viAct, they won't resell it
  - Camera / VMS giants (Motorola, Bosch, Axis, Hikvision, Genetec,
    Milestone, Verkada, ...) — they treat cold BD as sales enquiries
  - Mega-corp customers (BMW, Boeing, Coca-Cola, RWE, ports, logistics)
    — they buy, they don't resell
  - Industry associations (construction associations, chambers) — not
    businesses that resell software

**viAct scope** (confirmed from `workflows/viact-web-design.md` +
`workflows/industry_page.md`): AI industrial safety + video analytics
platform serving **5 verticals** — Construction, Manufacturing, Mining,
Oil & Gas, Logistics. Buyers = EHS Directors, HSE Managers, Plant Managers,
Safety Officers.

---

## Changelog

### v4.15.16 — Channel Partner Discovery mode (BD-outreach target extraction)

**Why**: 2026-07-23 session showed the manager's actual BD ask is not
"find any partner of any competitor". It is: *"find REGIONAL SYSTEMS
INTEGRATORS / VARs / AUTHORIZED RESELLERS of viAct's competitors so we
can approach them and offer them viAct alongside the competitor product
they already sell."*

The existing `discover_partners.py` pipeline extracts everything a
competitor lists as a "partner" — which is 80% wrong for this ask (tech
integrations, customers, competing solution vendors, mega-corps, ad
listings). All prior v4.15.x fixes tightened the FILTER; this ships a
new DISCOVERY MODE that goes at the problem from the reseller side:
for each Track competitor, DDG-search "authorized reseller / certified
partner / systems integrator [competitor]", then filter DDG results
through NOISE_NAMES + TRADE_PUB_BLOG_HOSTS + DNS + blog-title triggers.

Session result of the manual version of this: 32 verified regional
resellers appended to the "Channel Partners (Manual)" outreach tab
(SITECH x6, BuildingPoint x3, GRAITEC, MicroCAD 3D, DataStew, Premise
One, Safe & Sound, IdentiSys, FortressGT, JCS UK, ADC KY, and more).

**What**: New tool `tools/discover_channel_partners.py`:

- `find_channel_partners_for(competitor_name, competitor_domain)` —
  runs 4 DDG queries with formal reseller-terminology templates;
  filters TRADE_PUB_BLOG_HOSTS (26 entries: ASMAG, Channel Drive,
  VAR Insights, source/security-informed trade pubs, LinkedIn,
  marketplaces, review sites, Apple-reseller sites, blog articles);
  filters BLOG_TITLE_TRIGGERS (14 patterns: "top 10", "vs.", "default
  password", "how to", "review", etc.); NOISE_NAMES from
  `discover_partners.py` (60+ entries: surveillance giants, competing
  solution providers, mega-corps, generic SaaS, industry associations);
  DNS-verifies each candidate; guesses country from ccTLD; returns
  deduped list of {name, website, email_guess, country,
  resells_competitor}.
- `append_to_channel_partners_tab(entries, tab)` — auto-creates the
  target tab with 9-column schema, dedups against existing rows by
  email + normalized name, appends new entries.
- `run_channel_partner_discovery()` — iterates over all
  Track-status competitors (via existing `read_tracked_competitors()`).

CLI: `python partner_pipeline.py --find-channel-partners`

**Sheet contract**: `Channel Partners (Manual)` tab, 9 columns:
Company Name | Description | Website | Phone Number | Email | Address |
Country | Status | **Resells (Competitor)**

The last column is the killer feature — BD team sees at a glance which
competitor each reseller carries, so outreach can be tailored: *"You
already sell Trimble/Autodesk/Genetec — add viAct to your portfolio."*

**Files**:
- `tools/discover_channel_partners.py` — new module (~220 lines)
- `partner_pipeline.py` — new `--find-channel-partners` CLI flag + routing

---

### v4.15.7 — Word-boundary domain matching + subdomain root-preference

**Why**: v4.15.6 canonical map covers ~60 well-known brands, but any
partner name outside that list still went through DDG search + LLM
verify, and both stages were too lenient:

1. **Substring domain match**: `_verify_website_belongs_to_company`
   accepted `mymilestonecard.net` as valid for the partner "Milestone"
   because `"milestone" in "mymilestonecard.net"` is `True`. The keyword
   was buried in the middle of a token — the "milestone" in that
   domain has nothing to do with Milestone Systems.
2. **Subdomain preference missing**: DDG for "Promise Technology" ranks
   `promiseshop.promise.com` (the reseller shop) above `promise.com`.
   The candidate loop verified the shop URL first and stopped, so the
   root marketing site never got a chance.

**What**:
1. Added `_keyword_matches_domain_token(kw, domain)` — splits domain on
   `.` and `-`, then requires `kw` to be an exact token OR a prefix /
   suffix of a token. `milestone` matches `milestonesys` (prefix) but
   NOT `mymilestonecard` (buried substring). Replaced the substring
   check in `_verify_website_belongs_to_company`.
2. Added `_strip_junk_subdomain(url)` with two phases:
   - **Phase 1**: strip known infrastructure subdomains (`shop.`,
     `docs.`, `careers.`, `download.`, `blog.`, `investors.`, `dev.`,
     `partners.`, ~25 entries).
   - **Phase 2**: strip when the first label REPEATS or CONTAINS the
     second label — catches brand-shop patterns like
     `promiseshop.promise.com` → `promise.com` and
     `milestone-events.milestone.com` → `milestone.com`. Respects
     two-part TLDs (`.co.uk`, `.com.au`) so it doesn't strip
     `brand.co.uk` down to `co.uk`.
3. In `_find_website_via_search`, the stripped root URL is verified
   FIRST for every candidate — root wins whenever it also passes
   `_verify_website_belongs_to_company`. Falls back to the original
   subdomain URL if root fails.

**Test cases** (all passing):

| Input | Expected | Reason |
|-------|----------|--------|
| kw=milestone, domain=milestonesys.com | ✓ accept | prefix of token |
| kw=milestone, domain=mymilestonecard.net | ✗ reject | buried substring |
| url=promiseshop.promise.com | → promise.com | brand repeat |
| url=shop.example.com | → example.com | junk subdomain |
| url=docs.help.company.com | → company.com | chained strip |
| url=mymilestonecard.net | unchanged | no shared label |
| url=brand.co.uk | unchanged | two-part TLD |

**Sheet actions taken** (manually fixed during today's audit):
- AvidBeam / Milestone: `mymilestonecard.net` → `milestonesys.com`
- AvidBeam / Promise Technology: `promiseshop.promise.com` → `promise.com`
- AvidBeam / Bosch: `bosch.us` → `bosch.com`
- AvidBeam / FBX Solutions: added missing `https://` scheme

Future runs will get these right at write-time, no manual patch needed.

**Files**:
- `tools/enrich_partners.py` — new `_JUNK_SUBDOMAINS` set (~25 hosts),
  `_TWO_PART_TLDS` set (~25 entries), `_keyword_matches_domain_token`
  helper, `_strip_junk_subdomain` helper, updated
  `_verify_website_belongs_to_company` (word-boundary check) and
  `_find_website_via_search` (root-first verify)

---

### v4.15.6 — Canonical-domain map for enterprise brands (fixes Milestone → mymilestonecard.net type junk)

**Why**: DDG search for generic single-word brand names ("Milestone",
"Bosch", "Promise") often ranks marketing microsites, retail
subdomains, or completely unrelated squatter domains above the real
corporate site. Concrete cases from AvidBeam tab audit:

- `Milestone` → `mymilestonecard.net` (a *credit-card* site — nothing
  to do with Milestone Systems VMS)
- `Bosch` → `bosch.us` (US retail regional; AvidBeam is a global
  Netherlands-based vendor — should be `bosch.com`)
- `Promise Technology` → `promiseshop.promise.com` (shop subdomain,
  not the main product site)
- `FBX Solutions` → `fbxsolutions.co.uk/` (missing `https://` scheme)

The existing `_verify_website_belongs_to_company` LLM check should
catch these but doesn't always — the LLM sometimes accepts a page
just because the brand name appears somewhere on it. Better to
short-circuit for known brands entirely.

**What**: Added `_CANONICAL_DOMAINS` dict + `_canonical_website_for()`
helper at the top of `_find_website_via_search`. If the partner's
name (after light normalization — strip Inc/Ltd/Corp/etc., collapse
whitespace, lowercase) matches a key in the map, return that URL
directly and skip DDG entirely. Coverage: ~60 brands across VMS,
silicon/hardware, cloud, industrial/MES, construction/SaaS, EHS,
BI/analytics — the ones most likely to appear as competitor
partners AND most likely to trip DDG.

Unknown vendors still fall through to the existing DDG + LLM
verification path — no regression.

**Sheet actions taken** (already applied):
- AvidBeam / Milestone: `mymilestonecard.net` → `milestonesys.com`
- AvidBeam / Promise Technology: `promiseshop.promise.com` → `promise.com`
- AvidBeam / Bosch: `bosch.us` → `bosch.com`
- AvidBeam / FBX Solutions: `fbxsolutions.co.uk/` → `https://fbxsolutions.co.uk/`

**Files**:
- `tools/enrich_partners.py` — new `_CANONICAL_DOMAINS` dict (~60
  entries), `_canonical_website_for()` normalization helper, and
  short-circuit at the top of `_find_website_via_search`

---

### v4.15.5 — EXTRACT_PROMPT reject rules for capability-claims, MES/protocol mentions, media/PR relationships, big-brand ecosystem noise

**Why**: 2026-07-23 partner-quality audit of six competitor tabs
(Observia AI, AvidBeam, Retrocausal, Clarion, AegisVision, WorkVis,
OpenEye) surfaced a whole class of false positives the v4.13
partner/customer filter didn't catch. Deletion counts by tab:

- **Observia AI: 10 → 0** — every row (5 EHS platforms + 5 BI tools)
  came from a section titled "Connection with your entire safety & ops
  stack, out of the box" / "Effortlessly connect Observia with your
  existing systems". Zero named partnerships, zero press releases —
  just a one-sided "our API can push to X" capability grid. viAct's
  BD team cannot sell to Enablon / Cority / Power BI / Tableau
  because those are either competing EHS platforms or generic
  data-viz tools with no partnership program.
- **Retrocausal: 3 → 1** — SAP and Rockwell were pulled from a
  "Manufacturing Execution Systems / OPC UA / Plug-and-Play common
  tools" block. That block listed Siemens (legitimate — Retrocausal
  CEO interview + booth at Siemens Realize Live) alongside SAP,
  Rockwell, Azure AD, Okta, QRadar as "systems we integrate with".
  Only Siemens had actual partnership evidence outside the technical
  compatibility list.
- **OpenEye: 11 → 5** — earlier v4.15.x pass already stripped 5
  customer-story rows (schools / retail / brewery / credit union).
  Today's audit removed Syncomm Management Group after DDG search
  showed the only OpenEye↔Syncomm evidence is press-release
  cross-posting on snnonline.com (Syncomm's trade-media property).
  That's a media/PR relationship, not tech/channel.

Net across 6 tabs: 40 → 25 verified partners.

**What**: Added five new REJECT categories to `EXTRACT_PROMPT` in
`tools/discover_partners.py`, keyed as "v4.15.5":

1. **CAPABILITY-CLAIM sections** — reject logos under headers like
   "Connection with your entire stack", "Compatible with", "Works
   with your tools", "Effortlessly connect to" unless the same names
   also appear under an explicit "Technology Partners / Our Partners /
   Certified Partners" heading, OR the prose uses partnership
   language ("partnered with", "reseller", "certified by", "Available
   on X Marketplace").
2. **TECHNICAL PROTOCOL / STANDARDS mentions** — reject entries in
   "OPC UA integration", "MES systems we integrate with",
   "Plug-and-Play with X / Y / Z", "SSO via Azure AD / Okta"
   sections. These describe technical capability, not partnership.
3. **MEDIA / PR relationships** — reject when the only evidence is
   competitor publishing content on X's news site or X being a trade
   publication that covers the competitor. Syncomm-style case.
4. **BIG-BRAND CLOUD / HARDWARE PROVIDERS** — reject Microsoft /
   Google / AWS / Oracle / IBM as "we integrate with X" unless the
   source names a specific partnership program verbatim (e.g.,
   "NVIDIA Inception Program", "Intel Partner Alliance", "Google
   Cloud for Startups", "AWS ISV Accelerate Program"). Clarion's 4
   partners pass this rule; a bare "Powered by AWS" mention would not.
5. Reinforced the general "if unclear, REJECT" rule with concrete
   examples from today's audit so the LLM has anchor cases to
   generalize from.

**Sheet actions taken** (already applied by the audit script — no
extra migration needed):

- Deleted 10 rows from Observia AI tab (empty tab now)
- Deleted SAP + Rockwell Automation from Retrocausal
- Deleted Syncomm Management Group from OpenEye
- All 25 remaining partners are source-verified against a formal
  "partner"/"integration" section OR a named press release / joint
  case study / verifiable third-party partnership evidence.

**Files**:
- `tools/discover_partners.py` — appended v4.15.5 REJECT rules block
  to `EXTRACT_PROMPT` (~40 lines, between the existing v4.13 REJECT
  list and the "If unclear, REJECT" close-out)

---

### v4.15.4 — Header-aware column writes in enrich_partners (unbreaks legacy tabs)

**Why**: The Partnership Leads sheet has two co-existing column schemas.
Tabs created before v4.11 (Observia AI, AvidBeam, and several others)
put **Status at col D, Phone Number at col E, Email at col F**. Tabs
created v4.11+ (Retrocausal, OpenEye, Clarion, AegisVision, WorkVis,
etc.) put **Phone Number at D, Email at E, Status at H** — the current
`PARTNER_COLUMNS`. `enrich_partners.enrich_tab` built `col_letters`
from the hardcoded `PARTNER_COLUMNS` positions, so on a legacy tab
`col_letters["Email"]` resolved to `E` — the Phone Number column.
Every scraped email would land in the phone slot, and every scraped
phone would land in the Status slot. Row reads were already
header-based (via `_read_partner_rows`) so the bug was silent — the
next read would just see the wrong-column values as blank and try to
enrich them again.

Symptom that finally caught it: on the 2026-07-23 batch enrichment of
Observia AI and AvidBeam we started auditing whether phone values had
leaked into the Email column. They hadn't yet, only because most
legacy rows had been populated before this code path shipped — but
any new write into those tabs was primed to corrupt them.

**What**: Rewrote the col_letters construction in `enrich_tab` to read
the tab's actual header row first and index off THAT, mirroring what
`fill_missing_fields.fill_tab` has done since v3.5. Falls through to
`PARTNER_COLUMNS` positions only if the header row is empty (fresh
tab about to be seeded by `push_partners`, which will overwrite the
header anyway).

**Files**:
- `tools/enrich_partners.py` — replaced the hardcoded PARTNER_COLUMNS
  block at the top of `enrich_tab` with a header-fetch + dynamic
  col_letters build

---

### v4.15.3 — Swap dead Groq fallback model (llama-4-scout → llama-3.1-8b-instant)

**Why**: Groq deprecated / removed
`meta-llama/llama-4-scout-17b-16e-instruct` from its hosted catalog. Every
time `llama-3.3-70b-versatile` hit its rate-limit and the code fell
through to the fallback, the request 404'd. In `discover_partners.py`
the 404 was silently swallowed by `_extract_companies` (which returns
`[]` on any exception), so partner discovery would just quietly return
zero results during a rate-limit window — indistinguishable from a real
"no partners found" outcome. `discover_competitors.py` had the same
dead fallback with no user-visible signal.

**What**: Switched `FALLBACK_MODEL` in both files to
`llama-3.1-8b-instant` — smaller, currently available on Groq, and
cheap enough to burn through rate-limit backoff windows without
draining the daily token budget. Model choice matches what Agent 11
already uses elsewhere for lightweight extraction paths.

**Files**:
- `tools/discover_competitors.py` — line 38 `FALLBACK_MODEL` swap +
  inline comment
- `tools/discover_partners.py` — line ~37 `FALLBACK_MODEL` swap with
  explanation of the silent-swallow bug it fixed

---

### v4.15.2 — Descriptive alt-text support + section-end heading boundary (WorkVis fix)

**Why**: Batch partner discovery for the six 2026-07-23 competitors
returned 0 partners on WorkVis, but the site's homepage clearly shows
`<h3>Our Partners</h3>` with logos for **Industrial Scientific** and
**Code Red Safety**. Three separate issues combined to kill the run:

1. **Alt-max too short.** The alt on Code Red Safety's logo is a full
   accessibility sentence ("Code Red Safety company logo, a broken red
   letter C with the words Code Red Safety under the C." — ~100 chars).
   The old 80-char ceiling filtered it entirely.
2. **No company-name extraction from descriptive alts.** Even after
   bumping the max, an alt like "X company logo, ..." would land in the
   sheet verbatim instead of "X".
3. **Section had no end.** Right below Our Partners, WorkVis's page has
   an `Our Customers` case-study grid with ~15 scene-description alts
   ("Blue USS letter with Blue Circle around them...", "Blue and Green
   triangles..."). Because those imgs sit within 5000 chars of the
   partner marker, the v4.15 proximity gate was silently including them.
   People-photo alts ("Photo of Bart Peetermans from Code Red Safety")
   were also leaking through as fake partners.

**What**:
1. Bumped the alt-text max from 80 → 250 chars in the img regex.
2. For long alts containing the word "logo", peel the company name out
   of the descriptive text (`^(.+?)\s+(?:company\s+)?logo\b` — captures
   "Code Red Safety" from "Code Red Safety company logo, ...").
3. Reject alts that start with `Photo of / Picture of / Image of /
   Headshot of / Portrait of` — those are always team/testimonial
   headshots, never partner logos.
4. **Section-end via next heading.** Track all `<h1>|<h2>|<h3>`
   positions and, for each img, reject if a new heading opens between
   the chosen partner marker (+80 char offset to skip the closing tag
   of the heading that contains the marker) and the img. WorkVis's
   `<h3>Our Customers</h3>` at pos 99511 now correctly ends the
   partner section that started at 97459.
5. Fixed the heading-position scan to use `html_lower` (not the
   tag-stripped `html_norm`) — the tag-stripped version has no `<`
   characters left, so the initial version silently found zero
   headings and did nothing.

Verified:
- WorkVis: 2 partners (Industrial + Code Red Safety) — no false
  positives from the Our Customers grid (was 5, incl. 3 false).
- Clarion: still 4/4 (NVIDIA, Intel, OVHCloud, Google Cloud) — the
  section between "Technology Partnerships" heading and the next h1/h2/h3
  is empty of intervening headings, so nothing regresses.

**Data-quality caveat**: WorkVis's own alt attribute for the Industrial
Scientific tile only says `alt="Industrial"` (not the full name). We
extract what the source gives — the sheet row was manually filled with
the correct "Industrial Scientific".

**Files**:
- `tools/discover_partners.py` — `_extract_partner_logos_from_html`:
  alt max 250, descriptive-alt company extraction, people-photo skip,
  next-heading section boundary, heading scan uses html_lower

---

### v4.15.1 — Agent 1 discovery-query expansion (unblocks saturated pool)

**Why**: Discovery pool saturated at ~78 known competitors — the 5
original queries all targeted "construction / PPE / EHS" and repeatedly
surfaced the same G2 / Capterra alternatives lists. First re-run after
saturation returned only 1 new competitor (Everguard.ai). viAct's buyer
base spans 5 verticals — Construction, Manufacturing, Mining, Oil & Gas,
Logistics — plus APAC / Middle East / European regional markets, all of
which were under-queried.

**What**: Added 12 vertical- and region-specific queries to
`DISCOVERY_QUERIES` in `tools/discover_competitors.py`:

- 6 vertical (mining hazard detection, oil & gas refinery, warehouse
  PPE, manufacturing plant CV, port/terminal/shipyard, APAC industrial)
- 6 regional / product-cut (Europe, Middle East, India/SEA, fall
  detection scaffolding, forklift-pedestrian collision warning,
  drowsiness/fatigue detection)

Second run with the expanded list yielded 6 new competitors in one
session (Everguard.ai, AegisVision, WorkVis, Surveillant, OpenEye,
SafetyWorx365) — 6× the pre-expansion yield. LLM proposals jumped from
15 → 22 across the two runs.

**Data-quality note**: `AegisVision` (aegisvision.ai) may collide with
Clarion.ai's own product "Aegis Vision AI" — worth a manual check
before marking Status=Track. Otherwise the classifier / post-filter
worked as designed.

**Files**:
- `tools/discover_competitors.py` — 12 lines added to `DISCOVERY_QUERIES`

---

### v4.15 — Section-marker robustness in image-alt extractor (Clarion.ai fix)

**Why**: The 2026-07-22 daily run on Clarion.ai returned 0 partners even
though the site's `/ai-company/#partnerships` page clearly lists 4
technology partners (NVIDIA Inception, Intel Partner Alliance, OVHCloud
Startup Program, Google Cloud for Startups). Root cause was three
separate weaknesses in `_extract_partner_logos_from_html`:

1. **Inline HTML tags broke the section regex.** Clarion's heading is
   `<h2 class="sh dark">Technology <em>Partnerships</em></h2>`. The old
   pattern `r"technology\s*partner"` was applied to raw `html_lower`, so
   the `<em>` tag between "technology" and "partnerships" prevented any
   match and no STRONG PARTNER SIGNALS block was ever emitted.
2. **Proximity limit too tight.** Clarion's Technology Partnerships
   card grid spreads the 4 logos across ~4600 chars from the heading.
   The old 2500-char limit dropped 3 of 4 valid partners.
3. **Prose match downgraded specific section.** The paragraph
   "Our partnerships aren't marketing badges..." matched the generic
   `our\s+partners` pattern right after the real "Technology
   Partnerships" heading, and being closer to the imgs, it overrode
   the specific type — every logo would have been labeled generic
   "Partner" (→ Channel Partner) instead of Integration.

**What**:
1. Normalize HTML tags to same-length whitespace before running section
   regex (`html_norm = re.sub(r'<[^>]+>', lambda m: ' ' * len(m.group(0)), html_lower)`).
   Positions are preserved so the img-proximity check still aligns
   with the original html.
2. Bumped the img↔marker proximity limit from 2500 → 5000 chars.
3. Rewrote all section patterns to end with `partner(?:s|ships?)?\b`
   at word boundaries — matches partner / partners / partnership /
   partnerships as whole words, no longer fires on "partnering" verb
   forms.
4. When multiple markers precede the same img, prefer a specific-type
   marker (Technology / Integration / Implementation / Channel) over
   the generic "Partner" fallback. Falls through to the closest
   generic only if no specific one is in range.

Verified on `https://clarion.ai/ai-company/`: all 4 partners now
extracted with `Technology Partner` label → mapped to Integration by
`EXTRACT_PROMPT`. The 4 rows were also back-filled manually to the
`Clarion` tab in the Partnership Leads sheet.

**Files**:
- `tools/discover_partners.py` — `_extract_partner_logos_from_html`:
  tag-stripped `html_norm`, updated `section_patterns` with word
  boundaries and plural variants, specific-over-generic marker
  selection, proximity bumped to 5000

---

### v4.14.3 — Placeholder-email patterns for "J A Doe" middle-initial concat

**Why**: The Oracle NetSuite (via MaintainX) run leaked
`jadoe@example.com` into the sheet — a demo/placeholder generated from
the "J. A. Doe" middle-initial style ("First Middle Last" flattened to
`jadoe`). The v4.9.x placeholder blocklist covered `firstlast`,
`f.last`, `janed`, `johnd` etc. but not the middle-initial concat
variants. `_clean_email` therefore accepted `jadoe@…` as a real
address.

**What**: Added a 2-line block of middle-initial placeholder prefixes
to `PLACEHOLDER_PREFIXES` in `tools/scrape_partner_contact.py`:

- `jadoe`, `jbdoe`, `jcdoe`, `jddoe`, `jedoe` — "J{A,B,C,D,E} Doe"
- `jasmith`, `jbsmith`, `jcsmith` — "J{A,B,C} Smith"

Any email whose local-part starts with these prefixes is now rejected
by `_clean_email`, same path as the older `flast` / `firstlast` /
`janed` / `johnd` rules.

**Files**:
- `tools/scrape_partner_contact.py` — 3 lines added to
  `PLACEHOLDER_PREFIXES` (lines 86–88) with the incident comment

---

### v4.14.2 — Bugfix: URL-decode `mailto:` captures (kills leading `%20` in emails)

**Why**: Pelco's partners page had `mailto:%20sales@action-cs.com` (a leading
URL-encoded space). The mailto regex captured `%20sales@action-cs.com`
literally. `_clean_email` never percent-decoded it, and `%` is a valid
email local-part character per RFC — so the format check passed and the
sheet ended up with `%20sales@action-cs.com` as the contact email.

**What**: Wrap each `mailto:` match in `urllib.parse.unquote()` before
appending. The `%20` becomes a real space, `_clean_email`'s existing
`.strip()` removes it, and the resulting email is written correctly.
Added `unquote` to the `urllib.parse` import.

**Files**:
- `tools/scrape_partner_contact.py` — 2 lines in `_extract_emails` + 1 import

---

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

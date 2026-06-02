# Workflow: Market Radar — Competitor Intelligence

## Objective

Run a live competitor intelligence sweep for a given safety topic or viAct.ai URL. Outputs a Manager-Ready research package: competitor gap analysis table, 2-3 verified universal gaps, keyword signal, and a Decision Logic paragraph for executive email.

## Who Uses What

| Stakeholder | Output |
|---|---|
| **Gary (CEO)** | Decision Logic paragraph — copy-paste into daily email |
| **Surendra (Growth Lead)** | Gap analysis table + reasoning summary in Google Sheet |
| **Shoyab (Content Lead)** | Universal gaps + keyword signal → input for webpage content |

---

## CRITICAL: Sequential Research Protocol

**Non-negotiable. Do not skip or reorder phases.**

1. **Phase 1** — Identify competitors using the topic-category map
2. **Phase 2** — Analyze each competitor ONE AT A TIME (separate LLM call per competitor)
3. **Phase 3** — Synthesize gaps absent from ALL competitors (only after Phase 2 loop completes)
4. **Phase 4** — Package results and push to Google Sheet

Batching all competitors in one prompt produces shallow, unreliable gaps. Sequential analysis + cross-competitor synthesis produces verified intelligence.

---

## Inputs

| Input | Type | Required? |
|---|---|---|
| Safety topic | Free text | Yes (or URL/file) |
| URL | URL string | Alternative to topic |
| Document | .pdf / .docx / .txt | Alternative to topic |
| Competitor URL overrides | Comma-separated URLs | No — defaults applied if omitted |

---

## Competitor Category Map

| Category | Default Competitors | Match Keywords |
|---|---|---|
| AI Vision / Real-Time Detection | Protex AI, Intenseye, Visionify | vision, detection, ppe, fall, hazard, camera |
| Wearables / IoT Safety | Wakecap | wearable, helmet, iot, sensor, connected worker |
| Site Documentation | OpenSpace | documentation, 360, photo, progress |
| Compliance / Checklist | Safesite, Assignar | checklist, compliance, inspection, permit |
| Project Management | ClickUp, Assignar | project, scheduling, workflow, task |

Default fallback (no keyword match): **AI Vision / Real-Time Detection**

---

## Steps

### Step 1 — Topic Input

Accept input via Streamlit UI: free-text field, URL paste, or file upload (.pdf/.docx).

### Step 2 — HITL Gate 1: Competitor Selection

Show matched category and default competitor list.

Ask: *"Analyze one competitor or ALL?"*
- Specific → only that URL analyzed
- ALL → sequential loop

### Step 3 — 4-Phase Sequential Research

Calls `tools/research_competitors.py`:

**Phase 1:** Resolve competitor list. Silently fetch `viact.ai/sitemap.xml` for internal link data.

**Phase 2 (loop):** Per competitor:
1. Scrape via `tools/scrape_url.py` (cache to `.tmp/`)
2. Send ONLY that competitor's content to LLM with topic
3. Extract: `core_message`, `features_highlighted`, `tone`, `has_faqs`, `has_regulatory_context`, `notable_absence`
4. Log progress: `[2/3] Analyzed Protex AI — absence: No MOM compliance context`
5. Move to next ONLY after current is complete

**Phase 3 (synthesis):** Send all individual analyses as JSON array. Extract:
- 2-3 confirmed universal gaps (absent from every competitor)
- Keyword/search opportunity signal
- Strategic brief for content generation

**Phase 4:** Cache to `.tmp/research_<md5(topic)>.json`

### Step 4 — HITL Gate 2: Gap Selection

Show:
1. Competitor analysis table (Competitor | Depth | Regulatory Context | Gap Type | Notable Absence)
2. 2-3 confirmed universal gaps

Ask: *"Which gap should be built into a webpage?"*

### Step 5 — HITL Gate 3: Reference Collection

Ask: *"Provide reference links, PDFs, or case studies — or type 'proceed' for public MOM/BCA data."*

- References provided → source material used, NOT marked [Unverified]
- No references → all statistics marked [Unverified]

### Step 6 — Push to Google Sheets

Calls `tools/push_to_sheets.py` → `push_webpage()`:
- Tab: "Webpage Content"
- 16 columns: Date, Autorun#, Topic, Decision Logic, Webpage Body, SEO Suite, Schema FAQs, Schema JSON-LD, Extended FAQs, GEO Package, Visual Strategy, Internal Links, Competitor URLs, Input Source, Unverified, Status

---

## Running

```bash
streamlit run app.py
```

Select **Agent 01 — Market Radar** on the landing page, then use the "📡 Agent 01 — Market Radar" tab.
Follow the 5-step indicator — each HITL gate requires confirmation before advancing.

---

## Edge Cases

| Situation | Handling |
|---|---|
| Competitor URL fails (403/timeout) | Log warning, continue with remaining. Research proceeds with partial data. |
| All competitor URLs fail | Phase 3 runs on empty analyses; notes "No competitor data available" in gap_brief. |
| User provides no references | [Unverified] flag applied to all statistics. Output proceeds but flagged for review. |
| viAct sitemap unavailable | Falls back to 8 known viAct pages for internal link generation. |
| Topic > 500 chars | Truncated to 500 chars before research phase. |

---

## Tools Used

| Tool | Purpose |
|---|---|
| `tools/research_competitors.py` | 4-phase sequential competitor analysis |
| `tools/scrape_url.py` | Firecrawl-based anti-bot page scraping |
| `tools/generate_webpage_content.py` | Groq/LLM content generation (6-output package) |
| `tools/push_to_sheets.py` → `push_webpage()` | Google Sheets push via service account |

---

## Strict Exclusions

- No generic AI jargon: "transforming," "revolutionizing," "cutting-edge," "innovative"
- No feature-first content — viAct features appear only after problem is established
- No fabricated statistics — cite MOM/BCA/OSHAD by name or use "industry data shows"
- No invented URLs — only viAct.ai pages from sitemap in internal links

# Workflow: Manager-Ready Webpage Content Generation

## Objective

Generate a complete, Manager-Ready webpage content package for viact.ai targeting construction site safety managers and HSE officers in APAC (Singapore, UAE, Malaysia). Each run produces a 6-output content suite: Problem-First webpage body, SEO suite, GEO visibility package, FAQs with JSON-LD schema, Nano Banana 2 visual prompts, and a Decision Logic paragraph for Gary/Surendra's executive email.

## Who Uses What

| Stakeholder | Output They Receive |
|---|---|
| **Gary (CEO)** | Decision Logic paragraph — copy-paste into daily email |
| **Surendra (Growth Lead)** | Decision Logic + Reasoning Summary in Google Sheet |
| **Shoyab (Content Lead)** | Webpage Body (Markdown) + SEO Suite + Internal Links |
| **Web Developer** | Schema JSON-LD → paste into `<head>` block |
| **Design/Visual Team** | 2 Nano Banana 2 prompts for hero + mid-page images |

---

## CRITICAL: Sequential Research Protocol

**This is non-negotiable. Do not skip or reorder phases.**

The research phase runs in 4 strict phases before any content is generated:

1. **Phase 1** — Identify competitors using the topic-category map
2. **Phase 2** — Analyze each competitor ONE AT A TIME (separate Gemini call per competitor)
3. **Phase 3** — Synthesize gaps that are absent from ALL competitors (only after Phase 2 loop is complete)
4. **Phase 4** — Package and cache results

**Why this matters:** Batching all competitors into a single Gemini prompt produces shallow analysis. Gemini may invent a "gap" that one competitor actually covers. Individual analysis followed by cross-competitor synthesis produces verified, credible gaps.

---

## Inputs

| Input | Type | Required? | Default |
|---|---|---|---|
| Safety topic | Text string | **Yes** | — |
| URL (alternative) | URL | One of these three | — |
| Document (alternative) | .txt / .pdf / .docx | One of these three | — |
| Competitor URL overrides | Comma-separated URLs | No | Category defaults |
| Reference material | Text / URLs | No | Public MOM/BCA data ([Unverified]) |
| Autorun number | Integer | No | Auto-increments |

---

## Competitor Category Map

When a topic is entered, the agent automatically matches it to one of 5 categories. The matched competitors are used unless the user overrides them.

| Category | Competitors | Match Keywords |
|---|---|---|
| AI Vision / Real-Time Detection | Protex AI, Intenseye, Visionify | computer vision, ai detection, ppe, fall, hazard, camera |
| Wearables / IoT Safety | Wakecap | wearable, helmet, iot, sensor, connected worker |
| Site Documentation | OpenSpace | documentation, 360, photo, progress, reality capture |
| Compliance / Checklist | Safesite, Assignar | checklist, compliance, inspection, form, audit, permit |
| Project Management | ClickUp, Assignar | project management, scheduling, workflow, task |

Default fallback if no keywords match: **AI Vision / Real-Time Detection**

---

## Steps

### Step 1 — Topic Input

The agent accepts a topic via:
- `--brief "Fall Prevention in High-Rise Construction"` (CLI)
- `--url https://viact.ai/case-study` (extracts topic from page content)
- `--file report.pdf` (extracts topic from document)

In the Streamlit UI: free-text input field at Step 1.

### Step 2 — HITL Gate 1: Competitor Selection

The agent shows the matched competitor category and lists the default competitors.

**User is asked:** *"Which competitor should I analyze first, or analyze ALL?"*

- If user selects a specific competitor → only that URL is analyzed in Phase 2
- If user selects ALL → all category competitors are analyzed sequentially
- If `--competitors` flag is passed on CLI → skips the HITL gate

### Step 3 — 4-Phase Sequential Research

Calls `tools/research_competitors.py`:

**Phase 1:** Resolves the competitor list. Silently scrapes `viact.ai/sitemap.xml` for known pages (used for internal link validation later).

**Phase 2 (loop):** For each competitor URL:
1. Scrapes the page using `tools/scrape_url.py` (cached in `.tmp/`)
2. Sends ONLY that competitor's content to Gemini with the topic
3. Gemini returns: `core_message`, `features_highlighted`, `tone`, `has_faqs`, `has_regulatory_context`, `notable_absence`
4. Logs progress: "[2/3] Analyzed Protex AI — tone: feature-listing | absence: No MOM compliance context..."
5. Proceeds to next competitor ONLY after this analysis is complete

**Phase 3 (synthesis):** Sends ALL individual analyses (as a JSON array) to Gemini and asks:
- What is absent from EVERY competitor? (2-3 confirmed universal gaps)
- What is the keyword/search opportunity signal?
- What is the strategic brief for the content generator?

**Phase 4:** Packages and caches to `.tmp/research_<md5(topic)>.json`

### Step 4 — HITL Gate 2: Gap Selection

The agent shows:
1. The competitor analysis table (5 columns: Competitor | Depth | Regulatory Context | Gap Type | Notable Absence)
2. The 2-3 confirmed universal gaps

**User is asked:** *"Which specific gap should I build into a webpage?"*

The selected gap is set as the priority instruction for content generation.

### Step 5 — HITL Gate 3: Reference Collection

**User is asked:** *"Please provide reference links, PDFs, or case study data. Or type 'proceed' to use public MOM/BCA data."*

- If references provided: used as source material; output is NOT marked [Unverified]
- If no references: agent uses public regulatory data; all statistics marked [Unverified]

**The [Unverified] flag appears:**
- In the Decision Logic paragraph (noting missing reference)
- In the Google Sheet "Unverified" column (value: "Yes")
- As a warning banner in the Streamlit UI

### Step 6 — Content Generation

Calls `tools/generate_webpage_content.py` with:
- `topic`, `gap_brief`, `identified_gaps`, `keyword_signal`
- `references` (empty string if none)
- `viact_known_pages` (from sitemap scrape)
- `selected_gap` (user's HITL Gate 2 choice)

Gemini generates the 6-output package. If fewer than 5 schema FAQs are returned, the tool retries once with an explicit count instruction.

### Step 7 — Push to Google Sheets

Calls `tools/push_to_sheets.py` → `push_webpage()`:
- Creates "Webpage Content" tab if it doesn't exist
- Writes 1 row with 16 columns (see schema below)

### Step 8 — Confirm

CLI prints the full Decision Logic paragraph.
Streamlit shows all output tabs + push button.

---

## Google Sheet Column Schema — "Webpage Content" Tab

| Col | Header | Content | Who Uses It |
|---|---|---|---|
| A | Date | ISO date (2026-05-20) | — |
| B | Autorun# | Sequential run counter | Gary weekly report |
| C | Topic | The safety topic | — |
| D | Decision Logic | Full AI reasoning paragraph | **Gary/Surendra email** |
| E | Webpage Body | Full Markdown H1→CTA | Shoyab → web team |
| F | SEO Suite (JSON) | meta_title, meta_desc, keywords, heading_map | Shoyab → web team |
| G | Schema FAQs (JSON) | 5-item FAQ array | Developer |
| H | Schema JSON-LD | Full FAQPage JSON-LD string | **Developer → `<head>`** |
| I | Extended FAQs (JSON) | 2-item FAQ array | Web team |
| J | GEO Package (JSON) | opening_200_words + citation_framing_tips | Shoyab |
| K | Visual Strategy (JSON) | 2 Nano Banana 2 prompts | Design team |
| L | Internal Links (JSON) | Anchor + URL + context | Web team |
| M | Competitor URLs | URLs researched | Reference |
| N | Input Source | topic brief / URL / filename | Reference |
| O | Unverified | Yes / No | **Review flag** |
| P | Status | Draft → Published | Lifecycle tracking |

---

## Running via CLI

```bash
# Basic run (interactive HITL gates)
python run_pipeline.py --mode webpage --brief "Fall Prevention in High-Rise Construction"

# With autorun number
python run_pipeline.py --mode webpage --brief "PPE Compliance Singapore" --autorun 7

# Skip HITL Gate 1 with custom competitors
python run_pipeline.py --mode webpage --brief "Tunnel Safety Dubai" --competitors "https://url1.com,https://url2.com"

# From a URL (topic extracted from page)
python run_pipeline.py --mode webpage --url https://viact.ai/case-study
```

## Running via Streamlit UI

```bash
streamlit run app.py
```

Select "🌐 Webpage Content — Manager-Ready (HITL Research)" in the mode selector.
Follow the 5-step progress indicator. Each HITL gate requires a confirm button before the next step runs.

---

## 6 Outputs Explained

### Output 1: Webpage Body
- Markdown format, 600-900 words
- Structure: H1 (problem) → Why It Persists → Cost of Inaction → How viAct Helps → Proven Results → CTA
- viAct is NOT mentioned in the first 100 words

### Output 2: SEO Suite
- Meta title (≤60 chars) + Meta description (≤155 chars)
- 1 primary keyword + 3 secondary + 3-5 LSI keywords
- Canonical URL slug + heading map + image alt texts

### Output 3: GEO Package
- Opening 200 words optimized for AI citation (Claude, Perplexity, ChatGPT)
- 3 citation framing tips (which MOM/BCA data to reference, how to frame H1)

### Output 4: Schema FAQs (5 items → JSON-LD)
- 40-60 word answers, AI citation optimized
- Types: Regulatory, Problem definition, ROI, Technical, Timeline

### Output 5: Extended FAQs (2 items → on-page only)
- 80-120 word answers
- Types: Objection handling, Competitor comparison
- NOT included in schema markup

### Output 6: Visual Strategy (Nano Banana 2)
- 2 detailed image prompts
- Style: realistic photography, NOT CGI
- Human-centered: workers in frame, APAC construction context
- No stock-photo clichés

---

## Edge Cases

| Situation | Handling |
|---|---|
| Competitor URL fails to scrape (403/timeout) | Log warning, continue with remaining competitors. Research proceeds with partial data. |
| All competitor URLs fail | Phase 3 receives empty analyses. Gemini generates content from topic alone, notes "No competitor data available" in gap_brief. |
| Fewer than 5 schema FAQs returned | generate_webpage_content.py retries Gemini once with explicit count instruction. |
| User has no reference files | [Unverified] flag applied to all statistics. Output proceeds but is marked for review. |
| viAct sitemap unavailable | Falls back to 8 known viAct pages. Internal links still generated. |
| JSON-LD is malformed | Pushed to sheet as-is with Status "Review Schema". |
| Topic > 500 chars | Truncated to 500 chars before passing to research phase. |

---

## Ahrefs Integration (Live Keyword Data)

The Ahrefs MCP server is available in the Claude Code conversation context but **cannot be called from Python scripts directly**.

To use live Ahrefs data in the content:
1. In your Claude Code conversation, run the Ahrefs MCP tools for your target keyword
2. Copy the volume/trend output text
3. Paste it into your `--brief` alongside the topic: `--brief "Fall Prevention Singapore [Ahrefs: 2,400 monthly searches, +28% YoY]"`
4. The `keyword_signal` and `reasoning` fields will cite the specific numbers

Future upgrade: `--ahrefs-json` flag in `research_competitors.py` to accept pre-fetched keyword data as a JSON file.

---

## Strict Exclusions

- No social media posts (LinkedIn, Twitter, Instagram) — use the Social pipeline
- No image generation — only textual prompts for Nano Banana 2
- No generic AI jargon: "transforming," "revolutionizing," "cutting-edge," "innovative solution," "game-changing"
- No feature-first content — viAct features only appear after the problem is established
- No fabricated statistics — cite MOM/BCA/OSHAD by name or use "industry data shows"
- No invented URLs in internal links — only viAct.ai pages from sitemap

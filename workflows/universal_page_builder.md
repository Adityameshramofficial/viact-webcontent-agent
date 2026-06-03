---
name: Universal Dynamic Page Builder
description: Generate CMS-ready content for ANY viAct website page type given a reference page and field schema. Schema-driven, reusable, quality-validated.
type: agent-skill
version: 1.0
tool: tools/agent4_dynamic_page_builder.py
ui: app.py → "🔧 Universal Builder" tab
---

## Objective
Generate production-ready content for any dynamic page type on viAct's website.
Design is always fixed — only content changes per page. One system, infinite page types.

---

## When to Use
- You want to generate a new Use Case page (PPE Detection, Forklift Safety, etc.)
- You want to generate a Location page (Singapore, Malaysia, UAE, etc.)
- You want to generate a Comparison page (viAct vs. Competitor X)
- You want to generate ANY page type where the Wix CMS template already exists
- Rule: If the design is the same and only content changes → use this builder

---

## Inputs Required

| # | Input | Required | Description |
|---|-------|----------|-------------|
| 1 | Page type | ✅ | Category name, e.g. "Use Case Page", "Location Page" |
| 2 | Page topic | ✅ | Specific subject, e.g. "PPE Detection", "Singapore" |
| 3 | Reference URL | ✅ | Existing viAct page URL — sets tone, structure, brand voice |
| 4 | CMS field schema | ✅ | JSON list defining every field, its type, and constraints |
| 5 | Competitor URLs | ❌ | 1–3 competitor page URLs for research (optional) |
| 6 | Tavily research | ❌ | Toggle on/off — fetches fresh industry stats (default: on) |
| 7 | Custom instructions | ❌ | Freetext overrides for specific requirements |

---

## CMS Field Schema Format

Define once, save forever. Schema auto-loads from dropdown on next use.

```json
[
  {
    "name": "hero_title",
    "type": "text",
    "description": "Main H1 headline — problem-first, punchy",
    "max_chars": 60,
    "required": true
  },
  {
    "name": "hero_description",
    "type": "text",
    "description": "Subtext below hero — quantify the risk",
    "max_words": 40,
    "required": true
  },
  {
    "name": "feature_cards",
    "type": "array",
    "count": 4,
    "description": "Product capability cards",
    "item_fields": {
      "title": {"max_chars": 40},
      "body": {"max_words": 25}
    }
  },
  {
    "name": "stat_1",
    "type": "text",
    "description": "Key metric headline e.g. '87% Fewer Incidents'"
  },
  {
    "name": "meta_title",
    "type": "seo",
    "max_chars": 60
  },
  {
    "name": "meta_description",
    "type": "seo",
    "max_chars": 155
  },
  {
    "name": "hero_image_brief",
    "type": "image",
    "description": "Hero section image — APAC industrial, realistic, 1200x630px"
  }
]
```

**Supported field types:**
- `text` — plain text, constrained by `max_chars` and/or `max_words`
- `seo` — SEO fields; meta_title ≤60 chars, meta_description ≤155 chars enforced
- `array` — repeated items; `count` is enforced exactly; `item_fields` defines each sub-field
- `image` — Nano Banana style image prompt (30–50 words, APAC industrial, realistic)

---

## Pipeline

```
Step 1 — Configure
  ├── Select saved schema OR define new one
  ├── Enter page topic
  ├── Enter reference URL (existing viAct page)
  ├── Enter competitor URLs (optional)
  ├── Toggle Tavily research
  └── Enter custom instructions

Step 2 — HITL Review Gate
  └── Review: page type + topic + field count + reference URL
      → Click "Generate Page" to proceed

Step 3 — Auto Generation (4 sub-steps)
  ├── Scrape reference URL → tone/style context
  ├── Scrape competitor URLs → competitor context  
  ├── Run Tavily research → fresh industry data
  └── Single Groq call → all fields in one JSON response

Step 4 — Auto Validation
  └── Check each field against its constraint
      → Violation found: retry once with explicit correction message
      → Still failing: return best-effort + flag in quality_gate_errors

Step 5 — Output
  ├── CMS Fields tab   — all filled fields, copy-paste ready
  ├── Wix JSON tab     — formatted for Wix CMS import
  ├── SEO tab          — meta_title + meta_description highlighted
  ├── Image Briefs tab — image prompts if image fields defined
  └── Raw JSON tab     — full response for debugging
```

---

## Quality Gates (auto-enforced)

| Check | Rule |
|-------|------|
| `text` fields | Char and word count checked post-generation |
| `array` fields | Exact item count enforced (retry if wrong) |
| `seo` fields | meta_title ≤60 chars, meta_description ≤155 chars |
| ZERO_HALLUCINATION_BLOCK | Active on every Groq call — no invented stats |
| Validation failure after retry | Result returned with `quality_gate_errors[]` populated |

---

## Schema Management

- **New schema**: type it once → auto-saved to `.tmp/page_schemas/{page_type_slug}.json`
- **Existing schemas**: appear in dropdown — select and reuse, no re-entry
- **Update schema**: select from dropdown, edit, re-save — overwrites previous version
- Schemas persist across sessions and Streamlit restarts

---

## Tools Used

| Tool | Purpose |
|------|---------|
| `tools/agent4_dynamic_page_builder.py` → `build_dynamic_page()` | Core generation |
| `tools/agent4_dynamic_page_builder.py` → `research_topic()` | Tavily research |
| `tools/agent2_data_extractor.py` → `extract_competitor_content()` | Scraping |
| `tools/agent4_dynamic_page_builder.py` → `save_schema()` / `load_schemas()` | Schema persistence |

---

## Edge Cases

| Situation | Behavior |
|-----------|----------|
| Reference URL inaccessible (ACCESS_DENIED) | Generation continues with topic + custom instructions only |
| All competitor URLs blocked | Competitor block shows [Data unavailable] — generation continues |
| Tavily returns 0 results | Research block skipped — generation continues without it |
| Groq 429 / 413 rate limit | Auto-retry with FALLBACK_MODEL (llama-4-scout) |
| Validation fails after 1 retry | Result returned with `quality_gate_errors` populated — user sees warning |
| No schema saved yet | JSON textarea shown — user pastes schema manually |

---

## Output Format

```json
{
  "page_type": "Use Case Page",
  "page_topic": "PPE Detection",
  "cms_fields": {
    "hero_title": "...",
    "hero_description": "...",
    "feature_cards": [{"title": "...", "body": "..."}, ...],
    "meta_title": "...",
    "meta_description": "...",
    "data_sources_used": ["..."],
    "access_denied_urls": []
  },
  "quality_gate_errors": [],
  "generation_meta": {
    "model_used": "llama-3.3-70b-versatile",
    "retry_count": 0,
    "timestamp": "2026-06-03T10:00:00Z"
  }
}
```

---

## Self-Improvement Loop

When you discover issues with this builder:
1. If a field type is missing → add it to `_build_json_spec()` and `_validate_dynamic_page()`
2. If a page type has unique tone rules → add to Custom Instructions or update SYSTEM_INSTRUCTION
3. If a schema needs a new constraint → add `max_items` / `min_words` / `format` to field definition
4. Update this workflow file after any significant fix

---

## Verification

1. Run `app.py` → click "🔧 Universal Builder" tab
2. Define a "Use Case Page" schema (hero_title, hero_description, 4 feature_cards, meta_title, meta_description)
3. Topic: "PPE Detection", Reference: any `viact.ai/solutions/` page URL
4. Toggle Tavily on, no competitor URLs
5. Click "Preview & Continue" → review summary → click "Generate Page"
6. Check CMS Fields tab — all fields should be filled, no empty values
7. Check Raw JSON → `quality_gate_errors` should be `[]`
8. Check schema is auto-saved → reload app → dropdown shows "Use Case Page"

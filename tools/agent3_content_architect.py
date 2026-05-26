"""
Agent 3 — Content Architect (Groq / Llama 3.3 70B)

Generates a structured, modular webpage content suite from:
  - Real competitor Markdown scraped by Agent 2 (Firecrawl)
  - Confirmed gap evidence from Agent 1 (Tavily)
  - viAct sitemap (internal links)
  - Optional reference material

ZERO-HALLUCINATION CONTRACT:
  - Only use Markdown from Agent 2. If a URL's markdown == [ACCESS DENIED],
    write "[Data unavailable for {competitor}]" — never invent their content.
  - Every statistic must come from reference material or a named regulatory
    source (MOM, BCA, OSHAD, ISO 45001).
  - List exact source URLs in data_sources_used.
"""
import argparse
import json
import os
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env
from generate_webpage_content import SYSTEM_INSTRUCTION
from agent2_data_extractor import ACCESS_DENIED

ZERO_HALLUCINATION_BLOCK = """
ZERO-HALLUCINATION CONTRACT (non-negotiable):
- Use ONLY the Markdown text provided in COMPETITOR_CONTENT below (scraped by Firecrawl).
- If a competitor's entry is marked "[ACCESS DENIED]", write "[Data unavailable for {competitor}]"
  in any reference to that competitor — NEVER invent their features, claims, or messaging.
- Every statistic must come from the provided reference material or a named regulatory source:
  MOM WSH Act, BCA, UAE OSHAD, ISO 45001, or ILO. Write "industry data shows" if none available.
- List all source URLs you used in the data_sources_used field.
- List all ACCESS DENIED URLs in access_denied_urls field.

REFERENCE PRIORITY RULE:
- If Reference Material is provided below, these are REAL viAct internal project data and verified
  stats — treat them as ground truth, higher priority than any public estimate.
- Cite exact numbers from references. Do NOT round, paraphrase, or replace with generic figures.
- The problem_statement and regulatory_context sections MUST incorporate these figures where relevant.
- If a reference stat conflicts with a public estimate, always use the reference stat.
"""

FULL_SYSTEM = ZERO_HALLUCINATION_BLOCK.strip() + "\n\n" + SYSTEM_INSTRUCTION

# Complete viAct solutions + products catalog for internal link suggestions
VIACT_CATALOG = [
    # Solutions
    "https://www.viact.ai/solutions/video-analytics-solution",
    "https://www.viact.ai/solutions/permit-to-work-system",
    "https://www.viact.ai/solutions/generative-ai-solutions",
    "https://www.viact.ai/solutions/ai-for-decarbonization",
    "https://www.viact.ai/solutions/red-zone-monitoring",
    "https://www.viact.ai/solutions/project-control-center",
    "https://www.viact.ai/solutions/smart-site-safety-system",
    "https://www.viact.ai/solutions/environmental-monitoring",
    "https://www.viact.ai/solutions/ppe-detection",
    "https://www.viact.ai/solutions/danger-zone-detection",
    "https://www.viact.ai/solutions/fleet-management",
    "https://www.viact.ai/solutions/confined-space",
    "https://www.viact.ai/solutions/work-at-height-safety",
    "https://www.viact.ai/solutions/digital-works-supervision-system",
    "https://www.viact.ai/solutions/incident-management-software",
    # Products
    "https://www.viact.ai/products/viLID-lidar",
    "https://www.viact.ai/products/viAER-drone",
    "https://www.viact.ai/products/viHUB-platform",
    "https://www.viact.ai/products/viMOV-mobility",
    "https://www.viact.ai/products/viHOI-hoisting",
    "https://www.viact.ai/products/viMAC-machinery",
    "https://www.viact.ai/products/viBOT-robotic",
    "https://www.viact.ai/products/cctv-ai-modules",
    # IoT
    "https://www.viact.ai/iot/smart-helmet",
    "https://www.viact.ai/iot/smart-watch",
    "https://www.viact.ai/iot/gas-leak-detector",
    "https://www.viact.ai/iot/fleet-tracking-system",
    "https://www.viact.ai/iot/access-control-system",
    # Industries
    "https://www.viact.ai/industry/construction",
    "https://www.viact.ai/industry/oil-and-gas",
    "https://www.viact.ai/industry/manufacturing",
    "https://www.viact.ai/industry/mining",
    "https://www.viact.ai/industry/facility-management",
    "https://www.viact.ai/industry/food-beverage",
]

# viAct industry page URLs for scraping as tone reference
INDUSTRY_VIACT_URLS = {
    "Construction Safety":    "https://www.viact.ai/industry/construction",
    "Oil & Gas Safety":       "https://www.viact.ai/industry/oil-and-gas",
    "Manufacturing Safety":   "https://www.viact.ai/industry/manufacturing",
    "Mining Safety":          "https://www.viact.ai/industry/mining",
    "Facility Management":    "https://www.viact.ai/industry/facility-management",
    "Food & Beverage Safety": "https://www.viact.ai/industry/food-beverage",
}

# Competitor industry pages for Firecrawl scraping
INDUSTRY_COMPETITOR_URLS = {
    "Construction Safety": [
        "https://www.protex.ai/industries/construction",
        "https://www.intenseye.com/industries/construction",
        "https://visionify.ai/construction-safety/",
    ],
    "Oil & Gas Safety": [
        "https://www.intenseye.com/industries/oil-and-gas",
        "https://visionify.ai/oil-gas-safety/",
    ],
    "Manufacturing Safety": [
        "https://www.protex.ai/industries/manufacturing",
        "https://www.intenseye.com/industries/manufacturing",
    ],
    "Mining Safety": [
        "https://visionify.ai/mining-safety/",
        "https://www.intenseye.com/industries/mining",
    ],
    "Facility Management": [
        "https://www.protex.ai/industries/facility-management",
        "https://visionify.ai/facilities-safety/",
    ],
    "Food & Beverage Safety": [
        "https://www.intenseye.com/industries/food-and-beverage",
        "https://visionify.ai/food-and-beverage-safety/",
    ],
}


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _build_competitor_block(competitor_data: dict) -> str:
    """Format competitor markdown dict for the prompt."""
    lines = []
    for url, result in competitor_data.items():
        md = result.get("markdown", ACCESS_DENIED)
        wc = result.get("word_count", 0)
        if md == ACCESS_DENIED:
            lines.append(f"=== URL: {url} ===\n[ACCESS DENIED — do not invent this competitor's content]")
        else:
            lines.append(f"=== URL: {url} ({wc} words) ===\n{md[:1500]}")
    return "\n\n".join(lines)


def _generate_blog_content(
    topic: str,
    viact_pages: list[str],
    references: str,
    radar_topic_entry: dict,
    client,
) -> dict:
    """Generate a shorter educational blog post (600-800 words, 3 FAQs)."""
    combined_pages = list(dict.fromkeys(list(viact_pages or []) + VIACT_CATALOG))
    viact_pages_str = "\n".join(combined_pages[:40]) if combined_pages else "https://viact.ai/"
    references_str = (
        references.strip()[:4000]
        if references.strip()
        else "[No reference provided. Use MOM/BCA/OSHAD/ISO 45001 data only.]"
    )
    topic_slug = topic.lower().replace(" ", "-").replace("/", "-")
    why_trending = radar_topic_entry.get("why_trending", "")
    confirmed_at = radar_topic_entry.get("confirmed_at", "")
    opp_score = radar_topic_entry.get("opportunity_score", "Medium")

    blog_prompt = f"""### CONTEXT
Topic: {topic}
Content Type: Educational Blog Post (600-800 words)
Target Audience: HSE managers, safety officers, construction PMs in Singapore and UAE.
Reference Material: {references_str}
Context: {why_trending}

VIACT KNOWN PAGES (use ONLY these for internal_links — never invent):
{viact_pages_str}

---
### OUTPUT REQUIREMENTS
Write an educational blog post about "{topic}". Educational tone, not a sales pitch.
No heavy marketing language. Cite MOM/BCA/OSHAD/ISO 45001 where relevant.

Return a single JSON object:
{{
  "topic": "{topic}",
  "content_type": "blog",
  "data_sources_used": [],
  "access_denied_urls": [],

  "hero_section": {{
    "h1": "Searchable blog title — educational, specific (e.g. 'What Is X? A Guide for Singapore Construction')",
    "subheadline": "One sentence framing why this topic matters to HSE teams",
    "cta_text": "Book My Demo",
    "cta_url": "/contact"
  }},

  "problem_statement": "40-60 words. What challenge does this blog address?",

  "solution_parameters": [],

  "regulatory_context": {{
    "singapore": {{"standard": "MOM WSH Act or BCA", "requirement": "Specific Singapore requirement"}},
    "uae": {{"standard": "OSHAD SF-AR-L01", "requirement": "Specific UAE requirement"}}
  }},

  "webpage_body": "BLOG_BODY — Full Markdown, 600-800 words. Structure:\\n# [H1]\\n\\n[Opening: 2-3 sentences answering '{topic}' directly — optimised for AI citation]\\n\\n## What Is [Core Concept]?\\n[Definition + why it matters, 60-80 words]\\n\\n## Why It Matters in APAC Construction\\n[Regulatory context + human cost. MOM/OSHAD data. Short sentences ≤20 words each.]\\n\\n## Key Challenges\\n[3-4 bullet points. Practical, specific, no filler.]\\n\\n## How AI Technology Helps\\n[100-150 words. Brief viAct mention. Feature → mechanism → outcome format.]\\n\\n## Frequently Asked Questions\\n[3 Q&A pairs matching schema_faqs]\\n\\n**[Book My Demo →](/contact)**",

  "schema_faqs": [
    {{"question": "What does Singapore MOM require regarding {topic}?", "answer": "40-60 words. Cite MOM by name."}},
    {{"question": "What are the main challenges with {topic} on active construction sites?", "answer": "40-60 words. Factual, practical."}},
    {{"question": "How does AI-powered monitoring improve {topic} management?", "answer": "40-60 words. Cite viAct stats where relevant."}}
  ],

  "extended_faqs": [],

  "schema_json_ld": "FAQPage JSON-LD using the 3 schema_faqs above",

  "seo_suite": {{
    "meta_title": "Max 60 chars — blog format (e.g. '{topic}: Singapore Construction Guide')",
    "meta_description": "Max 155 chars — summarises the blog, includes primary keyword",
    "primary_keyword": "main search keyword for '{topic}'",
    "secondary_keywords": ["variant 1", "variant 2"],
    "lsi_keywords": ["regulatory term", "job role term", "location term"],
    "canonical_url_slug": "/blog/{topic_slug}",
    "heading_map": ["H1: ...", "H2: What Is...", "H2: Why It Matters", "H2: Key Challenges", "H2: How AI Technology Helps", "H2: FAQ"]
  }},

  "geo_package": {{
    "opening_200_words": "First ~200 words of the blog body",
    "citation_framing_tips": ["Tip 1: MOM/OSHAD anchor", "Tip 2: APAC market statistic"]
  }},

  "nano_banana_prompts": [
    {{
      "placement": "Featured Image",
      "prompt": "Realistic documentary construction site photograph related to {topic}. Workers in full PPE (hard hats, hi-vis). Singapore or UAE site. NO CGI, no stock poses.",
      "alt_text": "Construction workers managing {topic} on an active site"
    }}
  ],

  "internal_links": [
    {{"anchor_text": "anchor text", "url": "MUST be from viAct known pages list above — never invent", "context": "In the How AI Technology Helps section"}}
  ],

  "decision_logic": "Supporting blog post for topic cluster. Opportunity: {opp_score}. Confirmed: {confirmed_at}. Educational companion to pillar page on '{topic}'."
}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": FULL_SYSTEM},
            {"role": "user", "content": blog_prompt},
        ],
        temperature=0.65,
        max_tokens=3072,
        response_format={"type": "json_object"},
    )
    result = json.loads(response.choices[0].message.content)
    result["webpage_html"] = build_webpage_html(result)
    return result


def generate_cluster_topics(pillar_topic: str, primary_keyword: str) -> list[str]:
    """
    Single Groq call → returns 3 supporting blog topic strings for a pillar.
    Covers 3 angles: regulatory compliance, cost/ROI, practical how-to.
    """
    from groq import Groq

    client = Groq(api_key=get_env("GROQ_API_KEY"))
    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "user",
                "content": (
                    f'For pillar topic "{pillar_topic}" (primary keyword: "{primary_keyword}"), '
                    "suggest 3 supporting blog post topics covering different angles:\n"
                    "  1. Regulatory compliance angle (Singapore MOM / UAE OSHAD)\n"
                    "  2. Cost / ROI angle (what does non-compliance or manual process cost?)\n"
                    "  3. Practical how-to angle (step-by-step guide or checklist)\n\n"
                    "Each topic: 5-10 words, specific, searchable, construction safety audience.\n"
                    'Return JSON: {"topics": ["topic1", "topic2", "topic3"]}'
                ),
            }
        ],
        max_tokens=256,
        temperature=0.4,
        response_format={"type": "json_object"},
    )
    return json.loads(response.choices[0].message.content).get("topics", [])[:3]


def generate_industry_page(
    industry_name: str,
    industry_slug: str,
    viact_page_content: str,
    competitor_content: dict,
    references: str,
    viact_pages: list[str],
) -> dict:
    """
    Generate a full industry vertical landing page for viAct.ai.

    Produces the same JSON schema as generate_structured_content() so it can be
    pushed to Sheets via the existing push_webpage() call unchanged.
    content_type = "industry_page"

    Content follows the old agent's 8-section structure:
    Hero → One Intelligent Platform → Proven Metrics → AI CCTV Use Cases →
    Pre-Built Solutions → viGent → Voices from the Field → CTA
    """
    from groq import Groq

    client = Groq(api_key=get_env("GROQ_API_KEY"))

    combined_pages = list(dict.fromkeys(list(viact_pages or []) + VIACT_CATALOG))
    viact_pages_str = "\n".join(combined_pages[:40]) if combined_pages else "https://viact.ai/"

    references_str = (
        references.strip()[:4000]
        if references.strip()
        else (
            "[No reference provided. Use viAct verified stats ONLY: "
            "90% construction site risk reduction, 50% TRIR reduction, 65% LTI reduction, "
            "80% safety expenditure reduction, $2.5M+ savings per project, "
            "400+ construction sites, 32,000+ workers protected, 7,200+ lost workdays prevented.]"
        )
    )

    competitor_block = _build_competitor_block(competitor_content)
    denied_urls = [u for u, r in competitor_content.items() if not r.get("success")]

    if viact_page_content and viact_page_content not in ("[ACCESS DENIED]", ""):
        viact_block = (
            f"viAct existing {industry_name} page (match this tone and style):\n"
            + viact_page_content[:3000]
        )
    else:
        viact_block = (
            f"[No existing viAct {industry_name} page — write fresh content for this vertical. "
            "Match the tone of viAct's other industry pages: short punchy sentences, "
            "outcome-first, no buzzwords.]"
        )

    prompt = f"""Generate a complete industry vertical landing page for viAct.ai — {industry_name} sector.

=== VIACT EXISTING PAGE (TONE REFERENCE) ===
{viact_block}

=== COMPETITOR INDUSTRY PAGES (RESEARCH — Firecrawl scraped) ===
{competitor_block}

=== REFERENCE MATERIAL (real viAct data — use EXACTLY, do not paraphrase) ===
{references_str}

=== VIACT KNOWN PAGES (internal_links must ONLY use these — never invent URLs) ===
{viact_pages_str}

---
VIACT VERIFIED STATS (use these numbers — never make up different stats):
• 90% construction/industrial site risk reduction
• 50% TRIR reduction | 65% LTI reduction
• 80% safety expenditure reduction
• $2.5M+ savings per project
• 400+ sites deployed | 32,000+ workers protected | 7,200+ lost workdays prevented

BRAND VOICE (mandatory):
• Max 20 words per sentence. Short punchy fragments OK.
• Numbers beat adjectives: "90% reduction" not "significant reduction".
• CTA = "Book My Demo" — never "Get a Free Safety Audit".
• Feature format: [Name] → [how it works ≤8 words] → [measurable outcome].
• H2s: outcome-first. Start with the result, not the process.

---
Return a single JSON object. Populate EVERY field — do not leave placeholders.

{{
  "topic": "{industry_name} Industry Landing Page",
  "content_type": "industry_page",
  "data_sources_used": ["list URLs you actually used from competitor_content above"],
  "access_denied_urls": {json.dumps(denied_urls)},

  "hero_section": {{
    "h1": "AI for Safety & Productivity in {industry_name}",
    "subheadline": "Bold metric headline, max 20 words. Specific stat (e.g. '90% Risk Reduction Across {industry_name} Sites'). Wrap in **bold**.",
    "cta_text": "Book My Demo",
    "cta_url": "/contact"
  }},

  "problem_statement": "60-80 words. 2-3 {industry_name}-specific risks + regulatory anchor (MOM WSH Act / OSHAD). No viAct mention. Short sentences ≤20 words each.",

  "solution_parameters": [
    {{"feature": "AI CCTV Use Case 1 title (max 6 words)", "mechanism": "specific hazard detected, ≤8 words", "benefit": "specific injury/loss prevented"}},
    {{"feature": "AI CCTV Use Case 2 title", "mechanism": "specific hazard detected, ≤8 words", "benefit": "specific injury/loss prevented"}},
    {{"feature": "AI CCTV Use Case 3 title", "mechanism": "specific hazard detected, ≤8 words", "benefit": "specific injury/loss prevented"}},
    {{"feature": "AI CCTV Use Case 4 title", "mechanism": "specific hazard detected, ≤8 words", "benefit": "specific injury/loss prevented"}},
    {{"feature": "AI CCTV Use Case 5 title", "mechanism": "specific hazard detected, ≤8 words", "benefit": "specific injury/loss prevented"}},
    {{"feature": "AI CCTV Use Case 6 title", "mechanism": "specific hazard detected, ≤8 words", "benefit": "specific injury/loss prevented"}}
  ],

  "regulatory_context": {{
    "singapore": {{"standard": "MOM WSH Act / BCA", "requirement": "{industry_name}-specific Singapore regulatory requirement"}},
    "uae": {{"standard": "OSHAD SF-AR-L01", "requirement": "{industry_name}-specific UAE regulatory requirement"}}
  }},

  "webpage_body": "FULL MARKDOWN — all 8 sections in order:\\n\\n# AI for Safety & Productivity in {industry_name}\\n\\n## **[Bold metric headline, max 20 words]**\\n[H3 description 35-45 words: predictive intelligence system, capturing risks across machines/people/processes, mentioning viAct]\\n\\n## One Intelligent Platform — [Industry-Specific Subtitle max 7 words]\\n[25-35 words: AI CCTV + IoT + edge AI + wearables + SIF prevention, complete {industry_name} site visibility]\\n\\n## Proven Impact Across 400+ {industry_name} Sites\\n*Driving safety, efficiency, and uptime via AI-driven {industry_name} intelligence.*\\n\\n**[Stat 1: Number%↑/↓]** — [Metric 1 title, max 4 words]\\n[10-15 words with specific numbers — enterprise counts, cost savings, event counts]\\n\\n**[Stat 2]** — [Metric 2 title]\\n[10-15 words with specific numbers]\\n\\n**[Stat 3]** — [Metric 3 title]\\n[10-15 words with specific numbers]\\n\\n## AI CCTV Use Cases for {industry_name}\\n\\n**[Use Case 1 title]**\\n[20-30 words: specific hazard detected + specific injury/loss prevented]\\n\\n**[Use Case 2 title]**\\n[20-30 words]\\n\\n**[Use Case 3 title]**\\n[20-30 words]\\n\\n**[Use Case 4 title]**\\n[20-30 words]\\n\\n**[Use Case 5 title]**\\n[20-30 words]\\n\\n**[Use Case 6 title]**\\n[20-30 words]\\n\\n## Pre-Built AI Safety Solutions for Every {industry_name} Risk\\n[15-20 words: ready-to-deploy packages, complete visibility and control across {industry_name}-specific work environment]\\n\\n## viGent: EHS AI Agent\\n[30-40 words: {industry_name} operations generate continuous safety data across sites and shifts. viGent AI empowers HSE managers with real-time insights — detecting risks, prioritizing incidents, enabling faster safer decisions.]\\n\\n## Voices from the Field\\n> **\\"[35-50 words: specific operational problem + how viAct solved it + measurable result. First-person. Realistic.]\\"**\\n> *[Senior Safety/Operations Job Title], [Type of facility], [Country]*\\n\\n> **\\"[35-50 words: DIFFERENT problem from above]\\"**\\n> *[Job Title], [Facility type], [Country]*\\n\\n> **\\"[35-50 words: DIFFERENT problem]\\"**\\n> *[Job Title], [Facility type], [Country]*\\n\\n> **\\"[35-50 words: DIFFERENT problem]\\"**\\n> *[Job Title], [Facility type], [Country]*\\n\\n## Try #1 AI Safety Solutions for {industry_name}\\n[20-30 words: book a demo, name 2+ specific senior roles in this industry, mention how viAct fits daily operations]\\n\\n**[Book My Demo →](/contact)**",

  "schema_faqs": [
    {{"question": "What {industry_name} safety risks does viAct detect?", "answer": "40-60 words. List 3-4 specific hazards viAct detects in {industry_name}. Mention 90% risk reduction."}},
    {{"question": "How does AI CCTV work in {industry_name} environments?", "answer": "40-60 words. Edge AI + CCTV mechanism specific to {industry_name} conditions (dust, heat, low-light etc)."}},
    {{"question": "What regulations apply to {industry_name} safety in Singapore and UAE?", "answer": "40-60 words. Cite MOM WSH Act and OSHAD SF-AR-L01 requirements specific to {industry_name}."}},
    {{"question": "How quickly can viAct be deployed in a {industry_name} facility?", "answer": "40-60 words. Deployment timeline, pre-built AI models, minimal disruption to operations."}},
    {{"question": "What ROI can {industry_name} companies expect from viAct?", "answer": "40-60 words. $2.5M+ savings, 80% expenditure reduction, 400+ sites already deployed as proof."}}
  ],

  "extended_faqs": [
    {{"question": "How does viAct handle {industry_name}-specific environmental challenges like dust, heat, or low light?", "answer": "80-120 words. Specific {industry_name} environmental factors and how viAct edge AI handles each one."}},
    {{"question": "Can viAct integrate with existing {industry_name} management systems (ERP, SCADA, or HSE software)?", "answer": "80-120 words. Integration capabilities, API connectivity, no rip-and-replace required."}}
  ],

  "schema_json_ld": "FAQPage JSON-LD using all 5 schema_faqs. Valid JSON string format: {{\\\"@context\\\":\\\"https://schema.org\\\",\\\"@type\\\":\\\"FAQPage\\\",\\\"mainEntity\\\":[...]}}",

  "seo_suite": {{
    "meta_title": "Max 60 chars. Primary keyword + | viAct.ai. E.g. 'AI Safety for {industry_name} | viAct.ai'",
    "meta_description": "Max 155 chars. Pain point first, mention CCTV + IoT/Edge/Wearables + {industry_name}-specific risks. Soft CTA.",
    "primary_keyword": "primary search keyword for {industry_name} AI safety (long-tail, 3+ words)",
    "secondary_keywords": ["{industry_name} AI safety platform", "AI CCTV {industry_name}", "{industry_name} HSE software"],
    "lsi_keywords": ["edge AI {industry_name}", "wearable safety sensors", "predictive safety analytics", "SIF prevention {industry_name}", "{industry_name} regulatory compliance"],
    "canonical_url_slug": "/industry/{industry_slug}",
    "heading_map": [
      "H1: AI for Safety & Productivity in {industry_name}",
      "H2: [Bold metric headline]",
      "H2: One Intelligent Platform",
      "H2: Proven Impact Across 400+ Sites",
      "H2: AI CCTV Use Cases for {industry_name}",
      "H2: Pre-Built AI Safety Solutions",
      "H2: viGent: EHS AI Agent",
      "H2: Voices from the Field",
      "H2: Try #1 AI Safety Solutions"
    ]
  }},

  "geo_package": {{
    "opening_200_words": "First ~200 words of webpage_body verbatim",
    "citation_framing_tips": [
      "Singapore MOM WSH anchor point for {industry_name}",
      "APAC market statistic grounding the {industry_name} safety problem",
      "Regulatory framing for UAE OSHAD compliance"
    ]
  }},

  "nano_banana_prompts": [
    {{"placement": "Use Case 1 (520x327px)", "prompt": "CCTV perspective, high angle, AI bounding boxes neon green and red, highly realistic {industry_name} site, [use case 1 specific hazard], workers in full PPE, modern industrial lighting, 4k resolution, 520x327 px", "alt_text": "AI CCTV detecting [use case 1 hazard] in {industry_name} facility — viAct safety monitoring"}},
    {{"placement": "Use Case 2 (488x293px)", "prompt": "CCTV perspective, high angle, AI bounding boxes neon green and red, {industry_name} environment, [use case 2 specific hazard], industrial lighting, 4k resolution, 488x293 px", "alt_text": "AI safety monitoring for [use case 2] in {industry_name}"}},
    {{"placement": "Use Case 3 (520x303px)", "prompt": "CCTV perspective, high angle, AI bounding boxes neon green and red, {industry_name} site, [use case 3 hazard], industrial lighting, 4k resolution, 520x303 px", "alt_text": "Computer vision AI detecting [use case 3] — {industry_name} safety"}},
    {{"placement": "Use Case 4 (520x303px)", "prompt": "CCTV perspective, high angle, AI bounding boxes neon green and red, {industry_name} site, [use case 4 hazard], industrial lighting, 4k resolution, 520x303 px", "alt_text": "AI CCTV preventing [use case 4] in {industry_name}"}},
    {{"placement": "Use Case 5 (520x303px)", "prompt": "CCTV perspective, high angle, AI bounding boxes neon green and red, {industry_name} site, [use case 5 hazard], industrial lighting, 4k resolution, 520x303 px", "alt_text": "Real-time hazard detection for [use case 5] — {industry_name}"}},
    {{"placement": "Use Case 6 (520x317px)", "prompt": "CCTV perspective, high angle, AI bounding boxes neon green and red, {industry_name} site, [use case 6 hazard], industrial lighting, 4k resolution, 520x317 px", "alt_text": "AI safety system detecting [use case 6] in {industry_name} facility"}},
    {{"placement": "viGent Dashboard (422x377px)", "prompt": "Ultra-realistic dark-mode AI safety operations dashboard on large monitors, real-time incident heatmaps, alert timelines, worker status panels, {industry_name}-specific data widgets, viAct.ai interface, ambient blue lighting, 422x377 px", "alt_text": "viGent EHS AI Agent — {industry_name} safety operations dashboard"}},
    {{"placement": "Reviewer 1 Headshot (56x56px)", "prompt": "Professional headshot photo, neutral expression, senior safety professional appearance, plain background, 56x56 px", "alt_text": "Senior HSE Manager at {industry_name} facility"}},
    {{"placement": "Reviewer 2 Headshot (56x56px)", "prompt": "Professional headshot photo, neutral expression, operations director appearance, corporate attire, plain background, 56x56 px", "alt_text": "Operations Director at {industry_name} company"}},
    {{"placement": "Reviewer 3 Headshot (56x56px)", "prompt": "Professional headshot photo, neutral expression, plant manager appearance, plain background, 56x56 px", "alt_text": "Plant Safety Manager at {industry_name} enterprise"}},
    {{"placement": "Reviewer 4 Headshot (56x56px)", "prompt": "Professional headshot photo, neutral expression, HSE professional appearance, plain background, 56x56 px", "alt_text": "HSE Officer at {industry_name} site — viAct customer"}}
  ],

  "internal_links": [
    {{"anchor_text": "viAct Video Analytics Solution", "url": "https://www.viact.ai/solutions/video-analytics-solution", "context": "In the AI CCTV Use Cases section"}},
    {{"anchor_text": "AI PPE Detection", "url": "https://www.viact.ai/solutions/ppe-detection", "context": "In the Use Cases section"}},
    {{"anchor_text": "Red Zone Monitoring", "url": "https://www.viact.ai/solutions/red-zone-monitoring", "context": "In the Pre-Built Solutions section"}},
    {{"anchor_text": "viAct {industry_name} industry page", "url": "https://www.viact.ai/industry/{industry_slug}", "context": "Canonical internal link"}}
  ],

  "decision_logic": "Industry vertical landing page for {industry_name}. viAct existing page scraped as tone reference. Competitor industry pages analyzed via Firecrawl. Content follows viAct 8-section structure (Hero → Metrics → Use Cases → viGent → Testimonials → CTA). Stats: 90% risk reduction, 400+ sites, 32,000+ workers. Canonical: /industry/{industry_slug}."
}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": FULL_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.65,
        max_tokens=5120,
        response_format={"type": "json_object"},
    )
    result = json.loads(response.choices[0].message.content)
    result["content_type"] = "industry_page"
    result["webpage_html"] = build_webpage_html(result)
    return result


def generate_structured_content(
    topic: str,
    competitor_data: dict,
    viact_pages: list[str],
    references: str,
    radar_topic_entry: dict,
    content_type: str = "pillar",
) -> dict:
    """
    Generate a modular structured content JSON from real scraped data.

    Args:
        topic: The safety topic string (from Agent 1).
        competitor_data: Dict from Agent 2: {url -> {success, markdown, word_count}}.
        viact_pages: viAct known URLs for internal linking.
        references: Optional reference material text.
        radar_topic_entry: Full topic dict from Agent 1 (includes gap evidence, Tavily confirmation).

    Returns:
        Structured dict with hero_section, problem_statement, solution_parameters,
        regulatory_context, schema_faqs, extended_faqs, schema_json_ld, seo_suite,
        geo_package, nano_banana_prompts, internal_links, decision_logic, etc.
    """
    from groq import Groq

    client = Groq(api_key=get_env("GROQ_API_KEY"))

    # ── Blog fast-path (shorter prompt, educational tone) ─────────────────────
    if content_type == "blog":
        return _generate_blog_content(
            topic=topic,
            viact_pages=viact_pages,
            references=references,
            radar_topic_entry=radar_topic_entry,
            client=client,
        )

    # Build context blocks
    competitor_block = _build_competitor_block(competitor_data)

    accessible_urls = [u for u, r in competitor_data.items() if r.get("success")]
    denied_urls = [u for u, r in competitor_data.items() if not r.get("success")]

    # Merge sitemap pages with full known catalog, deduplicate, cap at 40
    combined_pages = list(dict.fromkeys(list(viact_pages or []) + VIACT_CATALOG))
    viact_pages_str = "\n".join(combined_pages[:40]) if combined_pages else "https://viact.ai/"

    references_str = (
        references.strip()[:4000]
        if references.strip()
        else "[No reference provided. Use MOM/BCA/OSHAD/ISO 45001 data only.]"
    )

    gap_evidence = radar_topic_entry.get("competitor_evidence", [])[:2]
    why_trending = radar_topic_entry.get("why_trending", "")
    confirmed_at = radar_topic_entry.get("confirmed_at", "")
    viact_query = radar_topic_entry.get("viact_search_query", f"site:viact.ai {topic}")
    opp_score = radar_topic_entry.get("opportunity_score", "High")
    comp_count = radar_topic_entry.get("competitor_count", len(gap_evidence))

    evidence_block = json.dumps(gap_evidence) if gap_evidence else "No direct evidence snippets."
    topic_slug = topic.lower().replace(" ", "-").replace("/", "-")

    prompt = f"""### CONTEXT
Topic: {topic}
Target Regions: Singapore (MOM / BCA standards), UAE (OSHAD / UAE Municipality regulations).
Reference Material: {references_str}

GAP CONFIRMATION (Tavily live search — {confirmed_at}):
  Query: "{viact_query}" → 0 results on viact.ai
  Opportunity: {opp_score} | Competitors covering this: {comp_count}
  Why trending: {why_trending}

COMPETITOR EVIDENCE (Tavily snippets — verified source):
{evidence_block}

SCRAPED COMPETITOR CONTENT (Firecrawl — use ONLY this, do not invent):
{competitor_block}

VIACT KNOWN PAGES (use ONLY these for internal_links — never invent URLs):
{viact_pages_str}

---
### OUTPUT REQUIREMENTS
Return a single JSON object with all fields below. Quality over word count — keep responses concise and factual.

{{
  "topic": "{topic}",
  "data_sources_used": ["URLs you actually used from the scraped content above"],
  "access_denied_urls": {json.dumps(denied_urls)},

  "hero_section": {{
    "h1": "HERO_SECTION — H1 Headline: problem-focused, names the risk, no viAct mention, no banned marketing words",
    "subheadline": "Sub-headline: regulatory context or human cost in 1 sentence",
    "cta_text": "Book My Demo",
    "cta_url": "/contact"
  }},

  "problem_statement": "PROBLEM_STATEMENT — 60 words max. AI-citation friendly. Directly answers '{topic}'. States the problem, quantifies it, names the affected group, gives regulatory context. No viAct mention.",

  "solution_parameters": [
    {{"feature": "SOLUTION_BLOCK — Feature 1 name", "mechanism": "How it works in plain English", "benefit": "Measurable outcome"}},
    {{"feature": "Feature 2 name", "mechanism": "How it works", "benefit": "Measurable outcome"}},
    {{"feature": "Feature 3 name", "mechanism": "How it works", "benefit": "Measurable outcome"}}
  ],

  "regulatory_context": {{
    "singapore": {{"standard": "COMPLIANCE_FOCUS — MOM WSH Act or BCA standard", "requirement": "Specific Singapore requirement for {topic}"}},
    "uae": {{"standard": "OSHAD SF-AR-L01 or UAE Federal Law No. 8", "requirement": "Specific UAE requirement for {topic}"}}
  }},

  "webpage_body": "WEBPAGE_BODY — Full Markdown. Sections: # [H1]\\n\\n[problem_statement]\\n\\n## Why This Problem Persists\\n[regulatory + structural causes. Cite MOM/BCA/OSHAD. Short sentences, ≤20 words each.]\\n\\n## The Cost of Getting It Wrong\\n[Human + financial cost. Cite named source or 'industry data shows'.]\\n\\n## How viAct Helps\\n[viAct introduced HERE for first time. Outcome-first. Use feature → mechanism → benefit format. Reference solution_parameters.]\\n\\n## Proven Results\\n[Use viAct verified stats: 90% construction site risk reduction, 50% TRIR reduction, 65% LTI reduction, 80% expenditure reduction, 400+ sites deployed, 32,000+ workers protected — or reference material if provided.]\\n\\n**[Book My Demo →](/contact)**",

  "schema_faqs": [
    {{"question": "SCHEMA_FAQS — What does Singapore MOM / BCA require for {topic}?", "answer": "40-60 words. Cite MOM/BCA by name."}},
    {{"question": "What are the main causes of [key hazard in {topic}]?", "answer": "40-60 words. Factual, named source or 'industry data shows'."}},
    {{"question": "How does viAct reduce costs for {topic} management?", "answer": "40-60 words. Cite viAct verified stats: 80% safety expenditure reduction, 50% TRIR reduction, 65% LTI reduction, 400+ sites deployed."}},
    {{"question": "How does viAct detect [specific hazard in {topic}]?", "answer": "40-60 words. Plain English — no jargon."}},
    {{"question": "How long does viAct deployment take on an active construction site?", "answer": "40-60 words. Realistic and specific."}}
  ],

  "extended_faqs": [
    {{"question": "Common objection: Is AI safety monitoring reliable on a real construction site?", "answer": "80-120 words. Acknowledge the concern, then address with evidence."}},
    {{"question": "How does viAct differ from checklist-based or wearable safety tools?", "answer": "80-120 words. Real-time detection vs reactive compliance."}}
  ],

  "schema_json_ld": "FAQPage JSON-LD using only the 5 schema_faqs. Format: {{\\\"@context\\\":\\\"https://schema.org\\\",\\\"@type\\\":\\\"FAQPage\\\",\\\"mainEntity\\\":[...]}}",

  "seo_suite": {{
    "meta_title": "SEO_SUITE — Max 60 chars. Primary keyword + viAct brand name.",
    "meta_description": "Max 155 chars. Primary keyword + value proposition. No truncation.",
    "primary_keyword": "1 APAC-relevant high-intent keyword for {topic}",
    "secondary_keywords": ["semantic variant 1", "variant 2", "variant 3"],
    "lsi_keywords": ["regulatory term", "job role term", "problem term", "Singapore/UAE location term", "compliance term"],
    "canonical_url_slug": "/ai-{topic_slug}-construction-safety",
    "heading_map": ["H1: ...", "H2: Why This Problem Persists", "H2: The Cost of Getting It Wrong", "H2: How viAct Helps", "H2: Proven Results", "H2: Frequently Asked Questions"]
  }},

  "geo_package": {{
    "opening_200_words": "Exact first ~200 words of webpage_body. Must directly answer '{topic}' query — no build-up. Optimized for AI citation (Claude, Perplexity, ChatGPT, Google AI Overviews).",
    "citation_framing_tips": [
      "Tip 1: MOM/BCA/OSHAD data point to anchor the opening",
      "Tip 2: How to frame H1 as a standalone definition AI systems can extract",
      "Tip 3: APAC market statistic to strengthen regional authority"
    ]
  }},

  "nano_banana_prompts": [
    {{
      "placement": "Hero",
      "prompt": "IMAGE_PROMPTS — Realistic documentary construction site photography. 2-3 workers in full PPE (hard hats, hi-vis, harnesses) on scaffolding. Singapore or Dubai skyline in background. Eye-level camera. NO CGI, no stock-photo poses, no floating UI.",
      "alt_text": "Descriptive alt text matching this prompt and the topic {topic}"
    }},
    {{
      "placement": "Mid-page",
      "prompt": "Realistic construction site control room. Safety manager looking at monitor showing AI detection interface with bounding boxes around a hazard. Workers visible through window. Documentary style. NOT CGI. Person in focus, screen secondary.",
      "alt_text": "Descriptive alt text matching this prompt and the topic {topic}"
    }}
  ],

  "internal_links": [
    {{"anchor_text": "...", "url": "MUST be from viAct known pages list above — never invent", "context": "Place in [section] paragraph"}},
    {{"anchor_text": "...", "url": "MUST be from viAct known pages list above", "context": "Place in [section] paragraph"}}
  ],

  "decision_logic": "Agent 1 confirmed via Tavily on {confirmed_at}: '{viact_query}' returned 0 results. Competitors covering this: {comp_count} ({', '.join(e.get('competitor','') for e in gap_evidence[:3]) if gap_evidence else 'see Tavily evidence'}). Agent 2 scraped {len(competitor_data)} pages via Firecrawl — {len(accessible_urls)} accessible, {len(denied_urls)} ACCESS DENIED. Agent 3 built this page from verified content. Opportunity: {opp_score} in APAC."
}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": FULL_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.65,
        max_tokens=4096,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    result["webpage_html"] = build_webpage_html(result)
    return result


def build_webpage_body(structured: dict) -> str:
    """
    Assemble the modular structured content into a single Markdown string.
    Used for backward compatibility with push_to_sheets.push_webpage().
    Prefers the pre-built webpage_body field if present.
    """
    if structured.get("webpage_body"):
        return structured["webpage_body"]

    hero = structured.get("hero_section", {})
    h1 = hero.get("h1", structured.get("topic", ""))
    problem = structured.get("problem_statement", "")
    params = structured.get("solution_parameters", [])
    reg = structured.get("regulatory_context", {})

    lines = [f"# {h1}", "", problem, ""]

    if reg:
        lines += ["## Regulatory Context", ""]
        for region, ctx in reg.items():
            lines.append(f"**{region.upper()} — {ctx.get('standard', '')}:** {ctx.get('requirement', '')}")
        lines.append("")

    if params:
        lines += ["## How viAct Helps", ""]
        for p in params:
            lines.append(f"**{p.get('feature', '')}** — {p.get('mechanism', '')} → {p.get('benefit', '')}")
        lines.append("")

    lines += ["**[Book My Demo →](/contact)**", ""]
    return "\n".join(lines)


def _md_inline(text: str) -> str:
    """Convert inline Markdown (links, bold, italic) to HTML."""
    import re
    import html as _h
    text = _h.escape(text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    return text


def build_webpage_html(structured: dict) -> str:
    """
    Convert structured content to clean Wix-paste-ready HTML.
    Output uses only <h1>, <h2>, <h3>, <p>, <ul>, <li>, <strong>, <a> tags
    so it can be pasted directly into Wix's Embed Code or Rich Text editor.
    """
    body = structured.get("webpage_body", "")
    if not body:
        body = build_webpage_body(structured)

    lines = body.split("\n")
    out: list[str] = []
    in_list = False

    for line in lines:
        line = line.strip()

        if line.startswith("### "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h3>{_md_inline(line[4:])}</h3>")
        elif line.startswith("## "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h2>{_md_inline(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<h1>{_md_inline(line[2:])}</h1>")
        elif line.startswith("- ") or line.startswith("* "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_md_inline(line[2:])}</li>")
        elif line == "":
            if in_list:
                out.append("</ul>")
                in_list = False
        else:
            if in_list:
                out.append("</ul>")
                in_list = False
            out.append(f"<p>{_md_inline(line)}</p>")

    if in_list:
        out.append("</ul>")

    return "\n".join(out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent 3 — Content Architect (Groq/Llama)")
    parser.add_argument("--topic", required=True, help="Safety topic string")
    parser.add_argument(
        "--agent1-file", default="",
        help="Path to Agent 1 JSON output (.tmp/agent1_results.json)"
    )
    parser.add_argument(
        "--agent2-file", default="",
        help="Path to Agent 2 JSON output (competitor_data dict)"
    )
    parser.add_argument("--references", default="", help="Reference material text")
    args = parser.parse_args()

    from research_competitors import scrape_viact_sitemap

    viact_pages = scrape_viact_sitemap()

    # Load Agent 1 results
    radar_topic_entry: dict = {"topic": args.topic, "competitor_evidence": []}
    if args.agent1_file:
        with open(args.agent1_file, encoding="utf-8") as f:
            a1 = json.load(f)
        for t in a1.get("topics", []):
            if args.topic.lower()[:10] in t["topic"].lower():
                radar_topic_entry = t
                break
        if not radar_topic_entry.get("competitor_evidence"):
            radar_topic_entry = a1.get("topics", [radar_topic_entry])[0]

    # Load Agent 2 results (or use empty dict)
    competitor_data: dict = {}
    if args.agent2_file:
        with open(args.agent2_file, encoding="utf-8") as f:
            competitor_data = json.load(f)

    try:
        result = generate_structured_content(
            topic=args.topic,
            competitor_data=competitor_data,
            viact_pages=viact_pages,
            references=args.references,
            radar_topic_entry=radar_topic_entry,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

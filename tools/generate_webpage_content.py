"""
viAct Strategic Content Architect — 6-output content suite generator.

Outputs per run:
  1. Webpage Body     — Problem-First Markdown, 600-900 words
  2. SEO Suite        — Meta title/desc, keywords, canonical slug, heading map
  3. GEO Package      — First-200-words optimized for AI citation + framing tips
  4. Schema FAQs      — 5 FAQs (40-60 word answers) → goes into JSON-LD
  5. Extended FAQs    — 2 FAQs (80-120 word answers) → on-page only
  6. Visual Strategy  — 2 Nano Banana 2 prompts (realistic, APAC, human-centered)
  + Internal Links    — Real viAct.ai URLs only (from sitemap)
  + Decision Logic    — Gary/Surendra executive report paragraph
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

# ---------------------------------------------------------------------------
# System Instruction — viAct Strategic Content Architect
# ---------------------------------------------------------------------------
SYSTEM_INSTRUCTION = """You are the viAct Strategic Content Architect.

MISSION: Build high-converting, Manager-Ready webpages for viact.ai — an AI-powered construction site safety platform using computer vision, IoT, and deep learning to detect hazards in real time.

BRAND VOICE:
- Tone: Authentic, supportive, grounded, and authoritative
- Never salesy. Never hyperbolic. Never use vague superlatives.
- BANNED WORDS: "transforming," "revolutionizing," "cutting-edge," "state-of-the-art," "innovative solution," "game-changing," "world-class," "next-generation," "industry-leading"
- Write as if briefing a construction site manager who had a safety incident last week and has 4 minutes to read this page.

PROBLEM-FIRST FRAMEWORK (non-negotiable page structure):
1. H1 + opening paragraph: Name the risk. Quantify the cost of inaction. No product mention in the first 100 words.
2. Body sections: Explain WHY the problem persists. Use regulatory data (MOM Singapore, BCA, UAE OSHAD, ISO 45001).
3. "How viAct Helps" section: Introduce viAct as the natural solution — never before this point.
4. CTA: "Get a free safety audit →" or equivalent direct action.

DATA INTEGRITY — NON-NEGOTIABLE:
- Only cite statistics from a named source: MOM annual report, BCA publication, UAE OSHAD data, ISO standards, or the user's reference material.
- If no specific source is available: write "a significant proportion" or "industry data shows" — never fabricate a percentage.
- If reference material is marked [Unverified]: note this clearly on any statistics drawn from it.

GEO VISIBILITY (critical in 2026 — AI search citation):
- The first 200 words must directly and completely answer the primary query.
- Do NOT build up to the answer — state it immediately.
- AI systems (Claude, Perplexity, ChatGPT, Google AI Overviews) evaluate opening content first.
- Use authoritative phrasing: "According to Singapore's Ministry of Manpower (MOM)..." or "Under UAE Federal Law No. 8..."

OUTPUT MANDATE:
Return ALL components in every run. Never return a partial package. No markdown fences around the JSON."""

# ---------------------------------------------------------------------------
# Prompt Template
# ---------------------------------------------------------------------------
PROMPT_TEMPLATE = """TOPIC: {topic}

PRIORITY GAP TO ADDRESS:
{selected_gap}

ALL IDENTIFIED GAPS (from competitor research):
{gaps_as_bullets}

KEYWORD SIGNAL:
{keyword_signal}

STRATEGIC BRIEF:
{gap_brief}

REFERENCE MATERIAL:
{references}

VIACT KNOWN PAGES — use ONLY these URLs for internal links (do not invent URLs):
{viact_pages}

Generate the complete 6-output content suite for viact.ai. Return ONLY valid JSON, no markdown fences, no text outside the JSON object.

{{
  "topic": "{topic}",

  "webpage_body": "Full webpage copy in Markdown format.\\n\\n# [H1: Problem-focused headline — no product mention]\\n\\n[Opening paragraph — 50-80 words. Directly names the risk and quantifies consequences. NO viAct mention. GEO-optimized: this paragraph must directly answer the query '{topic}' for AI search citation.]\\n\\n## [H2: Why This Problem Persists on Construction Sites]\\n[Body paragraph — regulatory context. Cite MOM/BCA/UAE OSHAD data. Explain structural causes of the problem.]\\n\\n## [H2: The Cost of Getting It Wrong]\\n[Human cost paragraph — injury statistics, regulatory penalties, project delays. Cite named source or use 'industry data shows'.]\\n\\n## [H2: How viAct Helps]\\n[viAct solution introduced here for the FIRST time. Problem-to-solution bridge. Explain the detection mechanism in plain English, not technical jargon.]\\n\\n## [H2: Proven Results]\\n[Evidence paragraph — use reference material if provided. Otherwise cite: viAct's 95% accident reduction figure, 500+ deployed projects, 70% manpower cost reduction.]\\n\\n**Get a free safety audit → [contact/demo link]**",

  "seo_suite": {{
    "meta_title": "Max 60 characters. Include primary keyword + viAct brand name.",
    "meta_description": "Max 155 characters. Include primary keyword + a clear value proposition. No truncation.",
    "canonical_url_slug": "/ai-[topic-slug]-[region] or /[topic-slug]-construction-safety",
    "primary_keyword": "1 exact-match keyword, APAC-relevant, high commercial intent",
    "secondary_keywords": ["semantic variant 1", "semantic variant 2", "semantic variant 3"],
    "lsi_keywords": ["regulatory term", "job role term", "problem term", "location term", "compliance term"],
    "image_alt_texts": [
      "Descriptive alt text for hero image — matches Visual Strategy prompt 1",
      "Descriptive alt text for mid-page image — matches Visual Strategy prompt 2"
    ],
    "heading_map": [
      "H1: [exact headline from webpage_body]",
      "H2: Why This Problem Persists on Construction Sites",
      "H2: The Cost of Getting It Wrong",
      "H2: How viAct Helps",
      "H2: Proven Results",
      "H2: Frequently Asked Questions"
    ]
  }},

  "geo_package": {{
    "opening_200_words": "Exact text of the first ~200 words of the webpage. Must directly and completely answer the query '{topic}' — do not build up to the answer. Written to be cited verbatim by Claude, Perplexity, ChatGPT, or Google AI Overviews. Includes: what the problem is, why it matters, who is affected, and what the regulatory context is.",
    "citation_framing_tips": [
      "Tip 1: Reference [specific MOM/BCA/OSHAD data point] in the opening paragraph to establish regional authority",
      "Tip 2: Frame the H1 as a direct definition so AI systems can extract it as a standalone answer",
      "Tip 3: Include [specific APAC market statistic or regulatory reference] to position viAct as the authoritative regional source"
    ]
  }},

  "schema_faqs": [
    {{"question": "Regulatory FAQ — What [regulatory body] requires regarding {topic}?", "answer": "Direct answer in 40-60 words. Cite MOM/BCA/ISO/OSHAD by name."}},
    {{"question": "Problem definition FAQ — What are the main causes of [risk related to topic]?", "answer": "Direct answer in 40-60 words. Factual, cites a named data source or uses 'industry data shows'."}},
    {{"question": "ROI FAQ — How does [solution] reduce costs for construction companies?", "answer": "Direct answer in 40-60 words. Use viAct's 70% manpower cost reduction or 95% accident reduction figures."}},
    {{"question": "Technical FAQ — How does viAct's system detect [specific hazard related to topic]?", "answer": "Direct answer in 40-60 words. Plain English — no jargon. Explains the detection process briefly."}},
    {{"question": "Timeline FAQ — How long does it take to deploy viAct on an active construction site?", "answer": "Direct answer in 40-60 words. Realistic and specific."}}
  ],

  "extended_faqs": [
    {{"question": "Objection FAQ — [Common objection or concern about adopting AI safety on site]?", "answer": "Thorough answer in 80-120 words. Acknowledge the concern, then address it directly with evidence or a counterpoint."}},
    {{"question": "Comparison FAQ — How does viAct differ from [checklist-based or wearable competitor approach]?", "answer": "Thorough answer in 80-120 words. Contrast approaches — problem-solving vs feature-listing. Position viAct's real-time detection advantage."}}
  ],

  "schema_json_ld": "The complete FAQPage JSON-LD string — include ONLY the 5 schema_faqs above, not extended_faqs. Format: {{\\\"@context\\\":\\\"https://schema.org\\\",\\\"@type\\\":\\\"FAQPage\\\",\\\"mainEntity\\\":[{{\\\"@type\\\":\\\"Question\\\",\\\"name\\\":\\\"...\\\",\\\"acceptedAnswer\\\":{{\\\"@type\\\":\\\"Answer\\\",\\\"text\\\":\\\"...\\\"}}}}]}}",

  "visual_strategy": [
    {{
      "placement": "Hero — above the fold, paired with H1",
      "alt_text": "Descriptive alt text matching this image",
      "prompt": "Nano Banana 2 prompt: [Realistic construction site photography — NOT CGI or renders. Show 2-3 workers wearing full PPE (hard hats, hi-vis vests, safety harnesses) on a high-rise scaffolding platform. Singapore or Dubai skyline visible in background. One worker is pointing at a hazard. Overcast sky suggests APAC monsoon season. Camera angle: eye-level, documentary style. NO stock-photo clichés — no handshakes, no floating UI, no posed smiles.]"
    }},
    {{
      "placement": "Mid-page — inside 'How viAct Helps' section",
      "alt_text": "Descriptive alt text matching this image",
      "prompt": "Nano Banana 2 prompt: [Realistic construction site control room or site office. A safety manager is looking at a monitor showing viAct's AI detection interface — red bounding boxes visible around a worker missing a hard hat. Other workers visible through the window in the background on site. Realistic lighting, practical work environment. NO CGI. Documentary photography style. Shows the human operator responding to an AI alert — the person is in focus, the screen is secondary.]"
    }}
  ],

  "internal_links": [
    {{"anchor_text": "...", "url": "MUST be from the viAct known pages list provided above", "context": "Place in [section name] paragraph — after [specific sentence type]"}},
    {{"anchor_text": "...", "url": "MUST be from the viAct known pages list provided above", "context": "Place in [section name] paragraph"}}
  ]
}}"""


def generate_webpage(
    topic: str,
    gap_brief: str,
    identified_gaps: list[str],
    keyword_signal: str = "",
    references: str = "",
    viact_pages: list[str] | None = None,
    selected_gap: str = "",
) -> dict:
    """
    Generate the full 6-output content suite for a viAct webpage.

    Args:
        topic: The safety topic.
        gap_brief: 400-600 word strategic brief from research_competitors.
        identified_gaps: List of gaps confirmed across all competitors.
        keyword_signal: Search trend/opportunity note.
        references: Reference material text. Empty string triggers [Unverified] flag.
        viact_pages: List of known viAct.ai URLs for internal linking.
        selected_gap: Specific gap the user chose to target (prepended as priority).
    """
    from groq import Groq

    client = Groq(api_key=get_env("GROQ_API_KEY"))

    gaps_as_bullets = (
        "\n".join(f"• {g}" for g in identified_gaps)
        if identified_gaps
        else "• No specific gaps identified — generate based on topic and reference material"
    )

    selected_gap_str = (
        selected_gap
        if selected_gap
        else (identified_gaps[0] if identified_gaps else f"General page on: {topic}")
    )

    viact_pages_str = (
        "\n".join(viact_pages[:20])
        if viact_pages
        else "https://viact.ai/ (sitemap unavailable — use only this URL for internal links)"
    )

    references_str = (
        references.strip()
        if references.strip()
        else (
            "[Unverified — no reference material provided. "
            "Use public MOM/BCA/OSHAD data only. "
            "Mark any statistics drawn without a named source as approximate.]"
        )
    )

    prompt = PROMPT_TEMPLATE.format(
        topic=topic,
        selected_gap=selected_gap_str,
        gaps_as_bullets=gaps_as_bullets,
        keyword_signal=keyword_signal or "No keyword data provided — use topic relevance reasoning for APAC market.",
        gap_brief=gap_brief[:4000] if gap_brief else "No strategic brief — generate from topic directly.",
        references=references_str,
        viact_pages=viact_pages_str,
    )

    def _call(temperature: float, max_tokens: int) -> dict:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)

    result = _call(temperature=0.65, max_tokens=8192)

    # Validate schema FAQ count — retry once if fewer than 5 returned
    if len(result.get("schema_faqs", [])) < 5:
        result = _call(temperature=0.5, max_tokens=8192)

    return result


def build_decision_logic(
    topic: str,
    research: dict,
    content: dict,
    references: str = "",
    autonomous_mode: bool = False,
    scan_timestamp: str = "",
) -> str:
    """
    Build the Decision Logic paragraph for Gary/Surendra's executive report.

    autonomous_mode=True uses the Market Radar narrative:
      "I autonomously scanned the market on [date], found viAct was missing [topic]
       while [Competitors] already had it..."

    autonomous_mode=False uses the manual research narrative:
      "I analyzed [competitors], found a gap in [topic]..."
    """
    primary_kw = content.get("seo_suite", {}).get("primary_keyword", topic)

    if references.strip() and "[Unverified" not in references:
        ref_str = f"using '{references[:60].strip()}...' as verified reference material"
    else:
        ref_str = (
            "using public MOM/BCA regulatory data "
            "[Unverified — add an internal reference source to confirm statistics]"
        )

    if autonomous_mode:
        # Radar flow — research dict is the full radar result for one topic entry
        competitors_with = research.get("competitors_with_it", [])
        competitors_without = research.get("competitors_without_it", [])
        total_scanned = research.get("total_competitors_scanned", len(competitors_with) + len(competitors_without))
        why_trending = research.get("why_trending", "")
        opportunity_reason = research.get("opportunity_reason", "")
        scan_ts = scan_timestamp or research.get("scan_timestamp", "")

        leaders_str = ", ".join(competitors_with[:3]) if competitors_with else "multiple competitors"
        date_str = f" on {scan_ts}" if scan_ts else ""

        return (
            f"I autonomously scanned the market{date_str}, analyzing {total_scanned} competitors "
            f"across 5 categories without any manual topic input. "
            f"viAct was missing '{topic}' while {leaders_str} already had dedicated content on this. "
            f"Why it matters: {why_trending[:150]} "
            f"I built this page {ref_str}, targeting the '{primary_kw}' search opportunity. "
            f"{opportunity_reason} "
            f"This positions viAct as the authoritative voice on {topic} in APAC, "
            f"closing a confirmed gap against {leaders_str}."
        )
    else:
        # Manual research flow
        competitors = [a.get("name", "") for a in research.get("competitor_analyses", [])]
        gaps = research.get("identified_gaps", [])
        keyword_signal = research.get("keyword_signal", "")

        competitors_str = ", ".join(competitors) if competitors else "industry competitors"
        gap_str = gaps[0] if gaps else f"no dedicated content on {topic}"
        kw_note = keyword_signal[:100] + "..." if len(keyword_signal) > 100 else keyword_signal
        first_competitor = competitors[0] if competitors else "all analyzed competitors"

        return (
            f"I analyzed {competitors_str}, found a gap in '{topic}' — specifically: {gap_str}. "
            f"Keyword signal: {kw_note} "
            f"I built this page {ref_str}, targeting the '{primary_kw}' search opportunity. "
            f"This positions viAct as the authoritative voice on {topic} in APAC, "
            f"directly filling the content gap left by {first_competitor}."
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Generate viAct Manager-Ready webpage content suite"
    )
    parser.add_argument("--topic", required=True, help="Safety topic")
    parser.add_argument("--gap-brief", default="", help="Strategic brief from research phase")
    parser.add_argument("--gaps", default="", help="Comma-separated identified gaps")
    parser.add_argument("--keyword-signal", default="", help="Keyword trend signal")
    parser.add_argument("--references", default="", help="Reference material text or URL")
    parser.add_argument("--selected-gap", default="", help="Specific gap chosen by user")
    parser.add_argument(
        "--research-file", default="",
        help="Path to cached research JSON from research_competitors.py"
    )
    args = parser.parse_args()

    gap_brief = args.gap_brief
    identified_gaps = [g.strip() for g in args.gaps.split(",") if g.strip()]
    keyword_signal = args.keyword_signal
    viact_pages = None

    if args.research_file:
        with open(args.research_file, encoding="utf-8") as f:
            research_data = json.load(f)
        gap_brief = research_data.get("gap_brief", gap_brief)
        identified_gaps = research_data.get("identified_gaps", identified_gaps)
        keyword_signal = research_data.get("keyword_signal", keyword_signal)
        viact_pages = research_data.get("viact_known_pages")

    try:
        result = generate_webpage(
            topic=args.topic,
            gap_brief=gap_brief,
            identified_gaps=identified_gaps,
            keyword_signal=keyword_signal,
            references=args.references,
            viact_pages=viact_pages,
            selected_gap=args.selected_gap,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

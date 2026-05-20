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
"""

FULL_SYSTEM = ZERO_HALLUCINATION_BLOCK.strip() + "\n\n" + SYSTEM_INSTRUCTION


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
            lines.append(f"=== URL: {url} ({wc} words) ===\n{md[:4000]}")
    return "\n\n".join(lines)


def generate_structured_content(
    topic: str,
    competitor_data: dict,
    viact_pages: list[str],
    references: str,
    radar_topic_entry: dict,
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

    # Build context blocks
    competitor_block = _build_competitor_block(competitor_data)

    accessible_urls = [u for u, r in competitor_data.items() if r.get("success")]
    denied_urls = [u for u, r in competitor_data.items() if not r.get("success")]

    viact_pages_str = (
        "\n".join(viact_pages[:20])
        if viact_pages
        else "https://viact.ai/ (sitemap unavailable)"
    )

    references_str = (
        references.strip()
        if references.strip()
        else (
            "[No reference material provided. Use public MOM/BCA/OSHAD data only. "
            "Mark any statistics without a named source as approximate with 'industry data shows'.]"
        )
    )

    gap_evidence = radar_topic_entry.get("competitor_evidence", [])
    why_trending = radar_topic_entry.get("why_trending", "")
    confirmed_at = radar_topic_entry.get("confirmed_at", "")
    viact_query = radar_topic_entry.get("viact_search_query", f"site:viact.ai {topic}")
    opp_score = radar_topic_entry.get("opportunity_score", "High")
    comp_count = radar_topic_entry.get("competitor_count", len(gap_evidence))

    evidence_block = json.dumps(gap_evidence, indent=2) if gap_evidence else "No direct evidence snippets."

    prompt = f"""TOPIC: {topic}

GAP CONFIRMATION (from Tavily live search on {confirmed_at}):
  Search query: "{viact_query}" → 0 results (viAct has NO page on this topic)
  Opportunity score: {opp_score}
  Competitor count covering this: {comp_count}
  Why trending: {why_trending}

COMPETITOR EVIDENCE SNIPPETS (from Tavily search):
{evidence_block}

COMPETITOR FULL PAGE CONTENT (scraped by Firecrawl — use ONLY this content):
{competitor_block}

REFERENCE MATERIAL:
{references_str}

VIACT KNOWN PAGES (use ONLY these URLs for internal_links — never invent URLs):
{viact_pages_str}

Generate the complete modular content suite. Return ONLY valid JSON matching exactly this schema:

{{
  "topic": "{topic}",
  "data_sources_used": ["list of URLs whose content you actually used"],
  "access_denied_urls": {json.dumps(denied_urls)},

  "hero_section": {{
    "h1": "Problem-focused headline. Names the risk. No viAct mention. No marketing language.",
    "subheadline": "Supporting line — regulatory context or human cost in 1 sentence.",
    "cta_text": "Get a Free Safety Audit",
    "cta_url": "/contact"
  }},

  "problem_statement": "50-80 words. Directly answers the query '{topic}' for AI citation. No viAct. GEO-optimized: states the problem, quantifies it, names the affected group, and gives regulatory context immediately.",

  "solution_parameters": [
    {{"feature": "...", "mechanism": "how it works in plain English", "benefit": "measurable outcome"}},
    {{"feature": "...", "mechanism": "...", "benefit": "..."}},
    {{"feature": "...", "mechanism": "...", "benefit": "..."}}
  ],

  "regulatory_context": {{
    "singapore": {{"standard": "MOM WSH Act or BCA", "requirement": "specific requirement relevant to {topic}"}},
    "uae": {{"standard": "OSHAD SF-AR-L01 or UAE Federal Law", "requirement": "specific requirement"}}
  }},

  "webpage_body": "Full Markdown webpage body. Structure: # [H1 from hero_section]\\n\\n[problem_statement]\\n\\n## Why This Problem Persists\\n[regulatory + structural causes paragraph]\\n\\n## The Cost of Getting It Wrong\\n[human + financial cost paragraph. Cite named source or 'industry data shows'.]\\n\\n## How viAct Helps\\n[viAct introduced HERE for first time. Plain English mechanism. Reference solution_parameters.]\\n\\n## Proven Results\\n[Evidence: 95% accident reduction, 500+ deployed projects, 70% manpower cost reduction — or use reference material if provided.]\\n\\n**Get a free safety audit →**",

  "schema_faqs": [
    {{"question": "Regulatory FAQ about {topic}?", "answer": "40-60 word answer citing MOM/BCA/OSHAD by name."}},
    {{"question": "What are the main causes of [risk related to {topic}]?", "answer": "40-60 word answer."}},
    {{"question": "How does viAct reduce costs for [topic] management?", "answer": "40-60 word answer citing 70% manpower cost reduction or 95% accident reduction."}},
    {{"question": "How does viAct detect [specific hazard in {topic}]?", "answer": "40-60 word plain English answer."}},
    {{"question": "How long does viAct deployment take on an active site?", "answer": "40-60 word realistic and specific answer."}}
  ],

  "extended_faqs": [
    {{"question": "Common objection about AI safety on construction sites?", "answer": "80-120 word answer that acknowledges the concern, then addresses it with evidence."}},
    {{"question": "How does viAct differ from checklist-based or wearable safety tools?", "answer": "80-120 word answer comparing approaches. Real-time detection vs reactive compliance."}}
  ],

  "schema_json_ld": "Complete FAQPage JSON-LD string using only the 5 schema_faqs above. Format: {{\\\"@context\\\":\\\"https://schema.org\\\",\\\"@type\\\":\\\"FAQPage\\\",\\\"mainEntity\\\":[...]}}",

  "seo_suite": {{
    "meta_title": "Max 60 chars. Primary keyword + viAct.",
    "meta_description": "Max 155 chars. Primary keyword + value proposition. No truncation.",
    "primary_keyword": "1 APAC-relevant high-intent keyword",
    "secondary_keywords": ["variant 1", "variant 2", "variant 3"],
    "lsi_keywords": ["regulatory term", "role term", "problem term", "location term", "compliance term"],
    "canonical_url_slug": "/ai-{topic_slug}-construction-safety",
    "heading_map": ["H1: ...", "H2: Why This Problem Persists", "H2: The Cost of Getting It Wrong", "H2: How viAct Helps", "H2: Proven Results", "H2: Frequently Asked Questions"]
  }},

  "geo_package": {{
    "opening_200_words": "Exact first ~200 words of the webpage body. Must directly answer '{topic}' query. AI citation optimized.",
    "citation_framing_tips": [
      "Tip 1: specific MOM/BCA data point to reference",
      "Tip 2: how to frame H1 as a standalone definition",
      "Tip 3: APAC market statistic to strengthen authority"
    ]
  }},

  "nano_banana_prompts": [
    {{
      "placement": "Hero",
      "prompt": "Realistic documentary construction site photography. 2-3 workers in full PPE on scaffolding. APAC skyline (Singapore or Dubai) in background. Eye-level camera. NO CGI, NO stock-photo poses.",
      "alt_text": "Descriptive alt text matching this prompt and topic"
    }},
    {{
      "placement": "Mid-page",
      "prompt": "Realistic construction site control room or site office. Safety manager looking at monitor showing AI detection interface with bounding boxes around hazard. Workers visible through window. Documentary style. NOT CGI.",
      "alt_text": "Descriptive alt text matching this prompt and topic"
    }}
  ],

  "internal_links": [
    {{"anchor_text": "...", "url": "MUST be from viAct known pages list above", "context": "Place in [section] paragraph"}},
    {{"anchor_text": "...", "url": "MUST be from viAct known pages list above", "context": "Place in [section] paragraph"}}
  ],

  "decision_logic": "Agent 1 confirmed via Tavily on {confirmed_at}: '{viact_query}' returned 0 results. Competitors covering this topic: {comp_count} ({', '.join(e.get('competitor','') for e in gap_evidence[:3]) if gap_evidence else 'see Tavily evidence'}). Agent 2 scraped {len(competitor_data)} competitor pages via Firecrawl — {len(accessible_urls)} accessible, {len(denied_urls)} returned ACCESS DENIED. Agent 3 built this page from verified content. Primary keyword targets {opp_score} opportunity in APAC."
}}"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": FULL_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.65,
        max_tokens=8192,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content)


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

    lines += ["**Get a free safety audit →**", ""]
    return "\n".join(lines)


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

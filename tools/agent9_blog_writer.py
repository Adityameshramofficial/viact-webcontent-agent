"""
Agent 9 — Blog / SEO Article Writer

Generates a full, CMS-ready SEO blog post for viAct.ai from a topic + keyword.
Uses Tavily for research (Google News RSS fallback) and Groq for writing.

Input:  topic, target_keyword, industry (optional), word_count (800/1200/1500)
Output: {"cms_fields": {...}, "seo": {...}, "generation_meta": {...}}
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

PRIMARY_MODEL  = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

VIACT_BRAND_CONTEXT = """
viAct.ai is a B2B AI-powered computer vision safety platform for industrial sites.

PRODUCTS (use these names exactly when mentioning viAct solutions):
- viGent AI Agent — agentic AI that reasons, plans, and acts on site safety data
- Smart Site Safety System (SSSS) — real-time site-wide safety monitoring
- Project Control Center (PCC) — centralised EHS command dashboard
- viHUB — enterprise centralised management platform (ECMP)
- PPE Detection AI — real-time hard hat, vest, glove, mask compliance
- Fall Protection AI — detects fall risks, missing harness, open edges
- Crane Safety AI — monitors crane swing zones, load limits, proximity
- Red Zone Management — controls access to restricted/danger zones
- e-Permit to Work (PTW) — AI-powered digital permit management
- Confined Space Supervision — gas, entry, duration monitoring
- Forklift Safety AI — pedestrian proximity, speed, seatbelt detection

TARGET CUSTOMERS: EHS Directors, HSE Managers, Plant Managers, Operations VPs at large industrial enterprises in construction, oil & gas, manufacturing, mining, facilities management.

VERIFIED VIACT STATS (you may use these without placeholders):
- 65% reduction in safety incidents
- 80% faster compliance reporting
- 500+ enterprise sites deployed
- 30+ countries
- 15,000+ unsafe events prevented annually
- 100+ enterprises
- 40% hygiene violation reduction (UAE dairy client)
- 48% reduction in back strain incidents (Singapore construction client)
- 62% reduction in forklift near misses in 3 months
- 30% boost in audit readiness
- Awards: BCA Singapore, MOM Singapore Safety Award, Frost & Sullivan

WRITING STYLE (match exactly):
- Third-person formal with occasional direct address
- Every section opens with a problem statement or provocative fact
- Use "high-risk industries" not "dangerous workplaces"
- Cite research sources when using external stats (UK HSE, OSHA, PwC, ISO, ILO)
- Weave viAct products naturally into solutions — never as an ad
- Frame issues as systemic, not individual failures
"""

ZERO_HALLUCINATION_BLOCK = """
ZERO HALLUCINATION RULE:
- External stats MUST include their source in parentheses e.g. (UK Health and Safety Executive, 2025) or use [X%] placeholder.
- Never invent client names, locations, or case study details beyond what is listed above.
- viAct verified stats listed above can be used freely.
- Do NOT invent product feature details not listed in PRODUCTS above.
"""

REAL_VIACT_CASE_STUDIES = """
REAL VIACT CASE STUDIES (use one relevant to the topic):
1. UAE Dairy/Food Manufacturing: 40% reduction in hygiene violations, 95%+ compliance accuracy
2. Singapore Construction Site: 48% reduction in back strain incidents using viAct EHS platform
3. Dubai Power Generator Manufacturer: 88% improvement in PPE compliance; 65% reduction in forklift incidents during facility relocation
4. General Industrial: 62% reduction in forklift near misses in 3 months; 30% boost in audit readiness
5. Across 100+ enterprises: 65% incident reduction, 15,000+ unsafe events prevented annually
"""

VIACT_INTERNAL_PAGES = {
    "Smart Site Safety System": "/smart-site-safety-system",
    "Project Control Center": "/project-control-center",
    "PPE Detection": "/ppe-detection",
    "Fall Protection": "/fall-protection",
    "Forklift Safety": "/forklift-safety",
    "Red Zone Management": "/red-zone-management",
    "e-Permit to Work": "/e-permit-to-work",
    "Crane Safety": "/crane-safety",
    "Confined Space Supervision": "/confined-space-supervision",
    "viGent": "/vigent",
    "viHUB": "/vihub",
    "Blog": "/blogs",
    "Contact": "/contact-us",
}

VIACT_CATEGORIES = [
    "Workplace Safety", "Environment, Health, and Safety",
    "Manufacturing Industry", "Electronic Permit Management",
    "Generative AI in Construction", "Generative AI in Manufacturing",
    "AI in Construction", "AI Applications in Construction",
    "Computer Vision", "Safety Inspection Software",
    "Facility Management", "Facility Maintenance",
    "Construction Planning & Execution", "Project Control Center (PCC)",
    "IoT Devices", "Virtual Site Inspection with AI",
    "ESG Scoring for Construction", "PropTech",
    "Singapore Construction Industry", "Japan Construction Industry",
    "Vietnam Construction Industry", "Indonesia Construction Industry",
    "Construction Contractor", "Autodesk Construction Cloud",
    "Wall Crack Detection", "Property Management", "Property Developers",
]


# ── Research ──────────────────────────────────────────────────────────────────

def _google_news_rss(query: str, max_results: int = 4) -> list:
    import requests
    import xml.etree.ElementTree as ET
    from urllib.parse import quote
    try:
        url = f"https://news.google.com/rss/search?q={quote(query)}&hl=en-US&gl=US&ceid=US:en"
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        results = []
        for item in root.findall(".//item")[:max_results]:
            results.append({
                "title": item.findtext("title", ""),
                "content": re.sub(r"<[^>]+>", "", item.findtext("description", ""))[:300],
            })
        return results
    except Exception:
        return []


def _tavily_search(query: str, max_results: int = 4) -> list:
    import requests
    try:
        resp = requests.post(
            "https://api.tavily.com/search",
            json={"api_key": get_env("TAVILY_API_KEY"), "query": query,
                  "search_depth": "basic", "max_results": max_results},
            timeout=15,
        )
        if resp.status_code in (429, 432):
            return _google_news_rss(query, max_results)
        data = resp.json()
        return [{"title": r.get("title", ""), "content": r.get("content", "")[:300]}
                for r in data.get("results", [])]
    except Exception:
        return _google_news_rss(query, max_results)


def _research(topic: str, keyword: str, industry: str) -> str:
    queries = [
        f"{keyword} statistics 2025 2026 workplace safety data",
        f"{topic} AI computer vision {industry} industry report",
        f"{keyword} OSHA ISO ILO regulation compliance requirements",
        f"{topic} challenges problems {industry} site safety",
        f"{keyword} case study results ROI industrial",
    ]
    snippets = []
    for q in queries:
        for r in _tavily_search(q, 3):
            snippets.append(f"SOURCE: [{r['title']}]\n{r['content']}")
    return "\n\n".join(snippets[:12])[:3500]


# ── LLM wrapper ───────────────────────────────────────────────────────────────

def _groq_call(messages: list, max_tokens: int = 6000, temperature: float = 0.65,
               json_mode: bool = True) -> str:
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))
    kwargs = dict(
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    try:
        resp = client.chat.completions.create(model=PRIMARY_MODEL, **kwargs)
        return resp.choices[0].message.content
    except Exception as e:
        err = str(e)
        if "429" in err or "413" in err or "rate_limit" in err.lower() or "too large" in err.lower():
            resp = client.chat.completions.create(model=FALLBACK_MODEL, **kwargs)
            return resp.choices[0].message.content
        raise


# ── Slug helper ───────────────────────────────────────────────────────────────

def _make_slug(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return f"/post/{s[:70]}"


def _reading_time(word_count: int) -> str:
    mins = max(1, round(word_count / 200))
    return f"{mins} min read"


# ── Main generator ────────────────────────────────────────────────────────────

def generate_blog_post(
    topic: str,
    target_keyword: str,
    industry: str = "Industrial",
    word_count: int = 1200,
    progress_callback=None,
) -> dict:
    """
    Generate a full SEO blog post for viAct.ai.
    Returns a dict with cms_fields, seo, generation_meta.
    """
    def _prog(msg: str):
        if progress_callback:
            progress_callback(msg)

    _prog("Researching topic...")
    research_ctx = _research(topic, target_keyword, industry)

    _prog("Writing blog post...")
    section_count = 4 if word_count <= 800 else (5 if word_count <= 1500 else 6 if word_count <= 2000 else (7 if word_count <= 2500 else 8))
    internal_pages_str = ", ".join(f'"{k}" → {v}' for k, v in VIACT_INTERNAL_PAGES.items())
    target_per_section = word_count // section_count

    prompt = f"""You are the lead content strategist for viAct.ai, the B2B AI safety platform.
You have written 250+ authoritative blog posts for viAct.ai's blog. Your writing gets cited by EHS managers, plant operators, and safety consultants.

BRAND CONTEXT:
{VIACT_BRAND_CONTEXT}

REAL CASE STUDIES YOU CAN REFERENCE:
{REAL_VIACT_CASE_STUDIES}

{ZERO_HALLUCINATION_BLOCK}

RESEARCH CONTEXT — mine this for statistics, findings, and angles:
{research_ctx}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TASK: Write a full, publish-ready viAct.ai blog post.

Topic: {topic}
Primary keyword: "{target_keyword}"
Industry focus: {industry}
Word count: {word_count} words
Body sections: {section_count} H2 sections (~{target_per_section} words each, each with 2-3 H3 subsections)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
STYLE RULES (based on 250+ real viAct posts — follow exactly):

OPENING: Must start with ONE of these patterns:
  a) A shocking industry statistic in quotes with source: "According to [source], X% of..."
  b) An uncomfortable truth: "Every [industry] [role] faces the same uncomfortable reality:..."
  c) A provocative question that reframes the problem

STATISTICS: Every H2 section needs at least 1 real stat with its source in parentheses.
Use research context above. If not available, use verified viAct stats or [X%] placeholder with source hint.

VIACT PRODUCTS: Mention 2-3 specific viAct products naturally within sections (not as ads).
Use exact product names from the brand context.

COMPARISON SECTION: Include one H2 section titled "Traditional [X] vs [AI/viAct] [X]: [Differentiator]"
with H3 subsections comparing old vs new approach across 3-4 dimensions.

CASE STUDY: Use one real viAct case study from the list above (pick most relevant to topic).
Title it "Seeing It in Practice: viAct [Topic Solution]" or similar.

CONCLUSION H2: Always "Conclusion and Key Takeaways"
KEY TAKEAWAYS H3: 4-6 full-sentence takeaways (not fragments — each must be a complete, informative sentence).

FAQS: 4-6 questions an EHS manager would actually Google. Answers: 40-60 words each, practical.

BOLD TEXT: Use **bold** for: (1) all viAct product names on first mention in each section, (2) every key statistic ("**65% fewer incidents**"), (3) critical safety terms EHS managers scan for ("**lockout tagout**", "**permit to work**", "**fall protection**"). Aim for 8-12 bold phrases per article.

TONE: Third-person formal. Consultative. Never salesy. Frame problems as systemic, not individual.
No clichés: avoid "in today's world", "game-changer", "revolutionize", "cutting-edge".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CATEGORY — pick single best match from:
{", ".join(VIACT_CATEGORIES)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT — single JSON object (no markdown, no code fences):
{{
  "blog_title": "Choose ONE title pattern — NUMBERED: '5 Reasons Why [Industry] Sites Fail at [Topic]' | PROBLEM-LED: 'Why [Industry] Sites Still Struggle with [Topic]' or 'The Hidden Cost of [Problem] in [Industry]' | HOW-TO: 'How to Reduce [Risk] by [X]% Using AI Vision' | WHAT: 'What Happens When [Safety System] Fails in [Industry]'. Primary keyword in first 6 words. Max 70 chars.",
  "meta_title": "SEO title (max 60 chars, primary keyword first)",
  "meta_description": "155 chars max — keyword + specific benefit + soft CTA. No generic phrases.",
  "excerpt": "2 sentences for blog card. Open with the core problem or stat. (max 45 words)",
  "slug_suffix": "lowercase-hyphenated-slug (max 65 chars, no prefix, keyword-rich)",
  "tags": ["Tag1", "Tag2", "Tag3", "Tag4", "Tag5"],
  "category": "Exact category name from list",
  "reading_time_words": {word_count},
  "tldr": [
    "H2 section heading 1 (used as clickable anchor link)",
    "H2 section heading 2",
    "H2 section heading 3",
    "Conclusion and Key Takeaways",
    "FAQs"
  ],
  "table_of_contents": ["same as tldr — H2 headings in order"],
  "introduction": "100-130 words. MUST open with a shocking stat or uncomfortable truth (see opening patterns above). Include primary keyword in first 2 sentences. Third paragraph should bridge problem to what the article covers.",
  "sections": [
    {{
      "heading": "H2 heading — specific and informative, keyword variation",
      "content": "60-80 word intro paragraph for this section. Frames the problem or context before subsections. Not empty.",
      "subsections": [
        {{
          "subheading": "H3 MUST follow one pattern — NUMBERED: '1. Problem Name', '2. Root Cause' (for problem/risk analysis) | STAGED: 'Stage 1: Detection', 'Stage 2: Alert', 'Stage 3: Response' (for process flows) | LETTERED: 'A. Legacy Approach', 'B. AI-Powered Alternative' (for comparisons). Named headings only for case study subsections.",
          "content": "150-200 words. Each subsection must: open with the specific problem, explain the mechanism/cause, include 1 stat with source, close with the solution direction. No generic sentences."
        }}
      ]
    }}
  ],
  "case_study": {{
    "heading": "Seeing It in Practice: viAct [specific solution for topic]",
    "client": "Real client type and region from verified case studies",
    "challenge": "2-3 sentences on specific safety/compliance challenge. Include industry context.",
    "solution": "2-3 sentences on exactly which viAct products were deployed and how.",
    "outcome": "Specific quantified results using verified viAct stats. Include numbers."
  }},
  "conclusion": "100-120 words. Synthesise the core argument. Show how viAct closes the gap described in the article. End with a single thought-provoking sentence.",
  "key_takeaways": [
    "Full sentence that stands alone as a learning. Not a fragment. (e.g. 'Incident reporting captures past events, not live risk, which is why facilities can appear safe on paper while accumulating undetected hazards.')",
    "Full sentence takeaway 2",
    "Full sentence takeaway 3",
    "Full sentence takeaway 4",
    "Full sentence takeaway 5"
  ],
  "faqs": [
    {{
      "question": "Question an EHS manager would actually search for about {topic}",
      "answer": "Practical 40-60 word answer. Reference viAct where natural but don't force it."
    }}
  ],
  "cta_heading": "Specific CTA headline related to {topic} (max 10 words)",
  "cta_body": "2 sentences. State the specific problem viAct solves for {industry}. Then the outcome.",
  "cta_button_text": "Talk to Our AI Expert!",
  "image_alt_main": "Descriptive alt text for hero image. Include primary keyword. 10-15 words.",
  "image_prompt_main": "Photorealistic industrial safety scene: [specific scene for {topic}]. Dark industrial environment with high-visibility workers. AI detection bounding boxes visible on screen. viAct dashboard displaying real-time metrics. Professional photography style, 16:9 ratio.",
  "focus_keyword": "{target_keyword}",
  "secondary_keywords": ["4-6 long-tail keyword phrases EHS managers actually search"],
  "internal_links_suggested": [
    {{"anchor": "natural anchor text from the article body", "url": "exact URL — choose ONLY from: {internal_pages_str}"}}
  ]
}}"""

    raw = _groq_call([{"role": "user", "content": prompt}], max_tokens=6000)

    try:
        data = json.loads(raw)
    except Exception:
        fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
        data = json.loads(fence.group(1)) if fence else {}

    # Build final CMS fields
    slug = f"/post/{data.get('slug_suffix', _make_slug(data.get('blog_title', topic))[7:])}"
    word_est = data.get("reading_time_words", word_count)

    cms = {
        "blog_title":          data.get("blog_title", topic),
        "slug":                slug,
        "meta_title":          data.get("meta_title", ""),
        "meta_description":    data.get("meta_description", ""),
        "excerpt":             data.get("excerpt", ""),
        "category":            data.get("category", "Safety Technology"),
        "tags":                data.get("tags", []),
        "reading_time":        _reading_time(word_est),
        "introduction":        data.get("introduction", ""),
        "tldr":                data.get("tldr", []),
        "table_of_contents":   data.get("table_of_contents", []),
        "body_sections":       data.get("sections", []),
        "case_study":          data.get("case_study", {}),   # {heading, client, challenge, solution, outcome}
        "conclusion":          data.get("conclusion", ""),
        "key_takeaways":       data.get("key_takeaways", []),
        "faqs":                data.get("faqs", []),
        "cta_heading":         data.get("cta_heading", "See viAct in Action"),
        "cta_body":            data.get("cta_body", ""),
        "cta_button_text":     data.get("cta_button_text", "Talk to Our AI Expert!"),
        "cta_url":             "https://www.viact.ai/contact-us",
        "image_alt_main":      data.get("image_alt_main", ""),
        "image_prompt_main":   data.get("image_prompt_main", ""),
        "internal_links":      data.get("internal_links_suggested", []),
        "publish_date":        datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "author":              "Shoyab Ali",
    }

    seo = {
        "focus_keyword":       data.get("focus_keyword", target_keyword),
        "secondary_keywords":  data.get("secondary_keywords", []),
        "title_length":        len(cms["meta_title"]),
        "description_length":  len(cms["meta_description"]),
        "keyword_in_title":    target_keyword.lower() in cms["meta_title"].lower(),
        "keyword_in_desc":     target_keyword.lower() in cms["meta_description"].lower(),
        "estimated_word_count": word_est,
    }

    return {
        "cms_fields": cms,
        "seo": seo,
        "generation_meta": {
            "topic": topic,
            "industry": industry,
            "model": PRIMARY_MODEL,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


# ── CLI entry ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--keyword", required=True)
    parser.add_argument("--industry", default="Industrial")
    parser.add_argument("--words", type=int, default=1200)
    args = parser.parse_args()

    result = generate_blog_post(
        topic=args.topic,
        target_keyword=args.keyword,
        industry=args.industry,
        word_count=args.words,
        progress_callback=print,
    )
    print(json.dumps(result, indent=2))

"""
Agent 3 — Product Page Generator (Groq / Llama 3.3 70B)

Generates structured CMS-ready content + design context for viAct.ai product pages.
Follows the same zero-hallucination contract as generate_industry_page().
Output is consumed by claude_designer.py to produce the final HTML page.
"""
import json
import os
import sys

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env
from agent3_content_architect import (
    ZERO_HALLUCINATION_BLOCK, VIACT_CATALOG,
    _strip_fences, _build_competitor_block, _groq_chat,
)

PRIMARY_MODEL  = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

# Known viAct product pages for auto-scraping
PRODUCT_VIACT_URLS: dict[str, str] = {
    "viGent — AI Agent for EHS":        "https://www.viact.ai/products/viHUB-platform",
    "CCTV AI Modules":                  "https://www.viact.ai/products/cctv-ai-modules",
    "viHUB Platform":                   "https://www.viact.ai/products/viHUB-platform",
    "viLID LiDAR":                      "https://www.viact.ai/products/viLID-lidar",
    "viAER Drone":                      "https://www.viact.ai/products/viAER-drone",
    "viMOV Mobility":                   "https://www.viact.ai/products/viMOV-mobility",
    "viHOI Hoisting":                   "https://www.viact.ai/products/viHOI-hoisting",
    "viMAC Machinery":                  "https://www.viact.ai/products/viMAC-machinery",
    "viBOT Robotic":                    "https://www.viact.ai/products/viBOT-robotic",
    "Smart Helmet (IoT)":               "https://www.viact.ai/iot/smart-helmet",
    "Smart Watch (IoT)":                "https://www.viact.ai/iot/smart-watch",
    "Gas Leak Detector (IoT)":          "https://www.viact.ai/iot/gas-leak-detector",
    "Fleet Tracking System (IoT)":      "https://www.viact.ai/iot/fleet-tracking-system",
    "Access Control System (IoT)":      "https://www.viact.ai/iot/access-control-system",
}

PRODUCT_SYSTEM = ZERO_HALLUCINATION_BLOCK.strip() + """

AGENT PERSONAS (follow all three simultaneously):

━━ ARIA SINGH — B2B Product Copywriter (14 years, enterprise SaaS) ━━
• Lead with outcome, not feature. "Reduces incidents by 65%" beats "AI-powered detection".
• Every feature card: what it detects → what injury or loss it prevents → measurable outcome.
• Banned words: cutting-edge, revolutionary, state-of-the-art, innovative, game-changing, transforming.
• Tone: precise, confident, result-oriented. Max 20 words per sentence.
• Hero body: 40-60 words. Problem-first framework: name the risk → quantify the cost → viAct solution.

━━ MARCUS WEBB — Technical SEO Director (12 years) ━━
• Meta title: [Product Name] | viAct.ai — ≤60 chars total. Count every character.
• Meta description: product outcome + primary keyword + differentiator + soft CTA. 150-160 chars exactly.
• Primary keyword must be a 3+ word long-tail phrase (converts 3-5× better than head terms).

━━ DANI CRUZ — AI Art Director (10 years) ━━
• Hero image: "Ultra-realistic render of [product in real-world industrial context]..." on #0D1117 bg.
• Feature images: "CCTV perspective, high angle, [specific hazard scenario], neon green #00FF41 safe zones, red #FF3B3B hazard zones, 2px stroke monospace labels, [WxH]px..."
• Dashboard image: "Ultra-realistic render of dark-mode dashboard (#0D1117 bg), viAct interface, real-time data, [WxH]px..."
• Every prompt MUST contain exact pixel dimensions (e.g. 1440x810px).

QUALITY GATES — output fails if any are violated:
• key_features: exactly 4 items
• how_it_works: exactly 3 steps
• use_cases: exactly 3 items (each from a different industry)
• testimonials: exactly 3 (different roles and countries)
• faqs: exactly 5 items
• image_prompts: exactly 6 items with pixel dimensions
• meta_title ≤ 60 chars
• meta_description 150-165 chars
"""


def generate_product_page(
    product_name: str,
    product_slug: str,
    viact_page_content: str,
    competitor_content: dict,
    references: str,
    custom_instructions: str = "",
) -> dict:
    """
    Generate a full product landing page for viAct.ai.

    Returns a JSON dict with all CMS fields + design_context brief for Claude HTML generation.
    """
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))

    combined_pages = list(dict.fromkeys(VIACT_CATALOG))
    viact_pages_str = "\n".join(combined_pages[:40])

    references_str = (
        references.strip()[:2000]
        if references.strip()
        else (
            "[No reference provided. Use viAct verified stats ONLY: "
            "90% construction site risk reduction, 50% TRIR reduction, 65% LTI reduction, "
            "80% safety expenditure reduction, $2.5M+ savings per project, "
            "400+ active sites, 32,000+ workers protected, 7,200+ lost workdays prevented.]"
        )
    )

    competitor_block = _build_competitor_block(competitor_content) if competitor_content else "[No competitor pages provided]"

    if viact_page_content and viact_page_content not in ("[ACCESS DENIED]", ""):
        viact_block = f"viAct existing {product_name} page (tone reference):\n{viact_page_content[:1500]}"
    else:
        viact_block = (
            f"[No existing viAct {product_name} page. "
            "Write fresh content. Match tone of existing viAct pages: short punchy sentences, "
            "outcome-first, no buzzwords, problem-first framework.]"
        )

    custom_block = (
        f"\nCUSTOM INSTRUCTIONS (follow exactly):\n{custom_instructions.strip()}"
        if custom_instructions.strip()
        else ""
    )

    prompt = f"""Generate a complete product page for viAct.ai's "{product_name}" product.
These are CMS text fields for a Wix product page + a design_context brief for HTML generation.

=== VIACT EXISTING PAGE (TONE REFERENCE) ===
{viact_block}

=== COMPETITOR PRODUCT PAGES (RESEARCH — do not invent if ACCESS DENIED) ===
{competitor_block}

=== REFERENCE MATERIAL (real viAct data — use EXACTLY, higher priority than generic figures) ===
{references_str}

=== VIACT KNOWN PAGES (use ONLY these for internal links — never invent URLs) ===
{viact_pages_str}
{custom_block}

---
VIACT VERIFIED STATS — use ONLY these if no reference provided:
• 90% site risk reduction | 50% TRIR reduction | 65% LTI reduction
• 80% safety expenditure reduction | $2.5M+ savings per project
• 400+ active sites | 32,000+ workers protected | 7,200+ lost workdays prevented

CONTENT RULES:
• Problem-First Framework: name the risk → quantify the cost → introduce viAct product as solution.
• Use cases: each must reference a specific industry (e.g. Construction, Oil & Gas, Manufacturing).
• Testimonials: first-person, specific problem + viAct solved it + measurable result, 35-50 words.
• FAQ answers: precise, 40-60 words, useful to a buyer doing due diligence.
• Max 20 words per sentence. No buzzwords.

---
Return ONE valid JSON object. No markdown fences. No explanation outside the JSON.

{{
  "topic": "{product_name} Product Page",
  "content_type": "product_page",
  "product_name": "{product_name}",
  "product_slug": "{product_slug}",
  "data_sources_used": ["list source URLs from competitor_content that you used"],
  "access_denied_urls": [],

  "hero_section": {{
    "h1": "{product_name} — [outcome-led tagline, max 10 words]",
    "subheadline": "[25-35 words: what the product does + key measurable outcome]",
    "hero_body": "[40-60 words: problem-first — risk name → cost → how this product solves it]",
    "primary_cta": "Book a Demo",
    "secondary_cta": "See How It Works"
  }},

  "problem_statement": {{
    "heading": "[Problem-first H2, max 10 words]",
    "body": "[60-80 words: specific pain point this product addresses, with a stat or regulatory reference]",
    "pain_points": [
      "[specific measurable pain point 1]",
      "[specific measurable pain point 2]",
      "[specific measurable pain point 3]"
    ]
  }},

  "key_features": [
    {{"title": "[Feature name, max 5 words]", "description": "[25-35 words: what it detects/does + outcome prevented]", "icon_hint": "shield"}},
    {{"title": "...", "description": "...", "icon_hint": "..."}},
    {{"title": "...", "description": "...", "icon_hint": "..."}},
    {{"title": "...", "description": "...", "icon_hint": "..."}}
  ],

  "how_it_works": [
    {{"step": 1, "title": "[Action verb + object, max 6 words]", "description": "[25-35 words explaining this step]"}},
    {{"step": 2, "title": "...", "description": "..."}},
    {{"step": 3, "title": "...", "description": "..."}}
  ],

  "technical_specs": {{
    "integrations": ["list compatible hardware, cameras, protocols, or software platforms"],
    "deployment_options": "[Cloud / On-premise / Edge / Hybrid]",
    "compatibility": "[camera brands, OS, communication protocols supported]"
  }},

  "use_cases": [
    {{"industry": "[Industry Name]", "title": "[Use case, max 6 words]", "description": "[25-35 words: specific hazard prevented + outcome + industry context]"}},
    {{"industry": "[Different Industry]", "title": "...", "description": "..."}},
    {{"industry": "[Different Industry]", "title": "...", "description": "..."}}
  ],

  "social_proof": {{
    "stats": [
      {{"metric": "90%", "label": "reduction in site risk", "source": "viAct verified"}},
      {{"metric": "50%", "label": "TRIR reduction", "source": "viAct verified"}},
      {{"metric": "$2.5M+", "label": "average savings per project", "source": "viAct verified"}}
    ]
  }},

  "testimonials": [
    {{"quote": "[35-50 word first-person: specific problem + viAct solved it + measurable result]", "role": "[Job Title, Company Type, Country]"}},
    {{"quote": "...", "role": "[Different role and country]"}},
    {{"quote": "...", "role": "[Different role and country]"}}
  ],

  "faqs": [
    {{"question": "[Specific buyer due-diligence question]", "answer": "[40-60 word precise answer]"}},
    {{"question": "...", "answer": "..."}},
    {{"question": "...", "answer": "..."}},
    {{"question": "...", "answer": "..."}},
    {{"question": "...", "answer": "..."}}
  ],

  "cta_section": {{
    "heading": "Deploy {product_name} Across Your Sites",
    "description": "[20-30 words: specific job titles who should book a demo + what they will see/get]",
    "primary_cta": "Book a Demo",
    "cta_url": "https://www.viact.ai/contact"
  }},

  "seo_suite": {{
    "meta_title": "[Product Name] | viAct.ai — must be ≤60 chars total",
    "meta_description": "[150-160 chars: outcome + primary keyword + differentiator + CTA]",
    "primary_keyword": "[3+ word long-tail keyword]",
    "keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"],
    "canonical_slug": "/products/{product_slug}"
  }},

  "image_prompts": [
    {{"id": "hero", "dimensions": "1440x810px", "prompt": "Ultra-realistic render of {product_name} in real industrial context, dark setting, #0D1117 background, professional product visualization, 1440x810px, photorealistic quality"}},
    {{"id": "feature_1", "dimensions": "520x327px", "prompt": "CCTV perspective, high angle, [specific hazard scenario for feature 1], neon green #00FF41 bounding boxes (safe zones), red #FF3B3B hazard zones, 2px stroke, monospace confidence labels, 520x327px"}},
    {{"id": "feature_2", "dimensions": "520x327px", "prompt": "CCTV perspective, high angle, [specific hazard scenario for feature 2], neon green #00FF41 safe zones, red #FF3B3B hazard boxes, 520x327px"}},
    {{"id": "feature_3", "dimensions": "520x327px", "prompt": "CCTV perspective, high angle, [specific hazard scenario for feature 3], AI detection overlay, 520x327px"}},
    {{"id": "dashboard", "dimensions": "1280x720px", "prompt": "Ultra-realistic render of dark-mode dashboard (#0D1117 bg), viAct {product_name} interface, real-time safety metrics, neon #ff6a3d accent, data visualization panels, 1280x720px, photorealistic"}},
    {{"id": "use_case", "dimensions": "800x500px", "prompt": "CCTV perspective, industrial facility environment, workers in full PPE, AI detection bounding boxes overlay, neon green safe zones, red hazard zones, 800x500px"}}
  ],

  "design_context": {{
    "page_objective": "[One sentence: what action this page must drive from the visitor]",
    "primary_audience": "[Specific job title + company type + region, e.g. HSE Manager, construction sites, APAC]",
    "tone": "Professional, precise, outcome-first. B2B enterprise. No buzzwords.",
    "key_differentiators": [
      "[differentiator 1 — specific, measurable]",
      "[differentiator 2 — specific, measurable]",
      "[differentiator 3 — specific, measurable]"
    ],
    "section_order": ["hero", "problem", "features", "how_it_works", "use_cases", "social_proof", "testimonials", "faq", "cta"],
    "color_palette": {{
      "primary": "#ff6a3d",
      "secondary": "#3fb950",
      "bg": "#0a0a0a",
      "text": "#c9d1d9",
      "card_bg": "#0e0e0e",
      "border": "#1e1e1e"
    }},
    "typography": "Jost, sans-serif"
  }}
}}"""

    messages = [
        {"role": "system", "content": PRODUCT_SYSTEM},
        {"role": "user", "content": prompt},
    ]

    raw = _groq_chat(client, messages, max_tokens=6000, temperature=0.65)
    raw = _strip_fences(raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(raw[start:end])
        else:
            raise ValueError(f"Could not parse JSON from LLM response:\n{raw[:500]}")

    return result

"""
Agent 6 — Case Study Builder
Generates a full viAct case study page from: company name, industry, location,
products used, optional metrics/references, and Tavily research.

Output schema mirrors viact.ai/case-studies page structure:
  Hero → Company Overview → Challenge → Solution → Impact → Testimonials → CTA
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

PRIMARY_MODEL  = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

VIACT_CASE_STUDY_REF = "https://www.viact.ai/case-studies"

ZERO_HALLUCINATION_BLOCK = """
ZERO HALLUCINATION RULE (MANDATORY):
- Every metric/stat/percentage you write MUST come from: (a) the references the user provided,
  (b) the Tavily research context, or (c) viAct verified published stats.
- If you don't have a real metric, write a PLAUSIBLE placeholder in [brackets] like [X% reduction]
  so the user knows to verify it.
- NEVER invent company names, employee counts, locations, or project details not in the input.
"""

VIACT_PRODUCTS = [
    "PPE Detection", "Fall Protection AI", "Crane Safety AI",
    "Red Zone Management", "e-Permit to Work (e-PTW)",
    "Confined Space Supervision", "Machinery & Equipment Tracking",
    "Worker Behaviour Analytics", "Area Access Control",
    "Forklift Safety AI", "Near-Miss Detection", "Fire & Smoke Detection",
    "viGent AI Agent",
]


# ── LLM wrapper ──────────────────────────────────────────────────────────────

def _groq_call(messages: list[dict], max_tokens: int = 3500, temperature: float = 0.65) -> str:
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))
    kwargs = dict(
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    try:
        resp = client.chat.completions.create(model=PRIMARY_MODEL, **kwargs)
        return resp.choices[0].message.content
    except Exception as e:
        err = str(e)
        if "429" in err or "413" in err or "rate_limit" in err.lower() or "too large" in err.lower():
            resp = client.chat.completions.create(model=FALLBACK_MODEL, **kwargs)
            return resp.choices[0].message.content
        raise


def _tavily_research(company: str, industry: str, location: str) -> str:
    """Search for company + viAct context. Returns combined snippet text."""
    import requests
    queries = [
        f"{company} {industry} safety AI viAct results {location}",
        f"{company} construction safety improvement {location}",
    ]
    snippets = []
    for q in queries:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={"api_key": get_env("TAVILY_API_KEY"), "query": q,
                      "search_depth": "basic", "max_results": 3},
                timeout=15,
            )
            for r in resp.json().get("results", []):
                snippets.append(f"[{r.get('title','')}] {r.get('content','')[:200]}")
        except Exception:
            pass
    return "\n".join(snippets[:6])


def _scrape_reference(url: str) -> str:
    """Scrape a reference page via Firecrawl. Returns markdown or empty string."""
    try:
        from agent2_data_extractor import extract_competitor_content
        result = extract_competitor_content([url])
        return result.get(url, {}).get("markdown", "")[:3000]
    except Exception:
        return ""


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(
    company: str,
    industry: str,
    location: str,
    products_used: list[str],
    references: str,
    research_context: str,
    ref_page_content: str,
    custom_instructions: str,
) -> list[dict]:
    products_str = ", ".join(products_used) if products_used else "viAct AI Safety Platform"

    system = (
        "You are a senior B2B content writer for viAct, an AI-powered construction safety platform.\n"
        "Write a full case study page following the exact structure of viact.ai/case-studies pages.\n"
        "Tone: authoritative, data-driven, specific. No marketing fluff. Real business outcomes.\n"
        "Follow the ZERO HALLUCINATION RULE strictly.\n"
        f"{ZERO_HALLUCINATION_BLOCK}"
    )

    ref_block = f"\nREFERENCE PAGE STYLE (scrape of viact.ai/case-studies):\n{ref_page_content[:2000]}\n" if ref_page_content else ""
    research_block = f"\nCOMPANY RESEARCH (Tavily):\n{research_context}\n" if research_context else ""
    refs_block = f"\nUSER-PROVIDED REFERENCES (use these as ground truth):\n{references}\n" if references else ""
    custom_block = f"\nCUSTOM INSTRUCTIONS:\n{custom_instructions}\n" if custom_instructions else ""

    prompt = f"""Generate a complete viAct case study page for:

COMPANY: {company}
INDUSTRY: {industry}
LOCATION: {location}
viAct PRODUCTS DEPLOYED: {products_str}
{ref_block}{research_block}{refs_block}{custom_block}

Return a JSON object with ALL of these fields (this maps directly to the Webflow CMS):

{{
  "hero_h1": "Achievement-focused headline e.g. '[Company] Cuts Rework by 60% with viAct viLid'",
  "h3": "1-2 sentence intro paragraph under the headline. Company context + main outcome achieved. Max 60 words.",
  "company_name": "{company}",
  "industry": "{industry}",
  "location": "{location}",
  "company_size": "e.g. '12,000+ employees' or '[X] employees' if unknown",
  "company_type": "e.g. 'Leading construction developer' or 'Major oil refinery operator'",
  "company_overview": "1-2 paragraphs (80-120 words). Who the company is, scale of operations, relevant industry context, compliance obligations.",
  "story_snapshot": "2-3 sentence narrative brief. Structure: [Company] faced [problem]. By deploying viAct [product], the team [achieved outcome].",
  "use_case": "Short use case label e.g. 'AI-Powered PPE Detection on Active Construction Sites'",
  "products_used": {json.dumps(products_used)},
  "metric_1_value": "primary metric value e.g. '80%' or '10x'",
  "metric_1_label": "short metric title e.g. 'Incident Reduction'",
  "metric_1_description": "Explanatory phrase starting with 'through', 'by', or 'via'. Max 15 words. e.g. 'through real-time PPE detection across all site entry points'",
  "metric_2_value": "second metric value",
  "metric_2_label": "second metric title",
  "metric_2_description": "Explanatory phrase for metric 2. Max 15 words.",
  "metric_3_value": "third metric value",
  "metric_3_label": "third metric title",
  "metric_3_description": "Explanatory phrase for metric 3. Max 15 words.",
  "challenge_title": "H3 subtitle for The Challenge section. Specific pain point e.g. 'Catching Deviations Before Follow-On Trades Make Rework Inevitable'",
  "challenge_body": "3-4 paragraphs (200-300 words). Specific pain points, manual processes, risks, compliance gaps, operational impact. Plain text only.",
  "solution_title": "H3 subtitle for The Solution section. Describes deployment approach e.g. 'Multi-Mode viLid Deployment for Continuous Spatial Site Intelligence'",
  "solution_body": "2-3 paragraphs (150-200 words). Overview of how viAct was deployed and what changed. Plain text only.",
  "solution_sub1_title": "Title for Solution subsection 1 — specific to first product/module deployed",
  "solution_sub1_body": "2 paragraphs (100-150 words). How subsection 1 product was deployed + specific outcome. Plain text only.",
  "solution_sub2_title": "Title for Solution subsection 2 — specific to second product/module or second deployment phase",
  "solution_sub2_body": "2 paragraphs (100-150 words). How subsection 2 product was deployed + specific outcome. Plain text only.",
  "impact_title": "H3 subtitle for The Impact section e.g. 'Building Compliance Resilience and Competitive Advantage'",
  "impact_body": "2-3 paragraphs (120-180 words). Quantified results first, then qualitative improvements, long-term value. Plain text only.",
  "testimonial_1_quote": "Direct quote (1-3 sentences) from EHS/safety professional. Specific benefit, not generic praise.",
  "testimonial_1_role": "Role title only e.g. 'EHS Director'",
  "testimonial_2_quote": "Second quote from different role (project manager, safety supervisor, BIM manager, etc.)",
  "testimonial_2_role": "Role title only e.g. 'Project Safety Manager'",
  "cta_headline": "e.g. 'Bring the same results to your {industry.lower()} site'",
  "meta_title": "SEO title max 60 chars e.g. '{company} Case Study | viAct AI Safety'",
  "meta_description": "SEO description 150-160 chars",
  "keywords": "5-8 SEO keywords comma-separated. Mix of product keywords + location + industry. e.g. 'AI safety monitoring Singapore, PPE detection construction, viAct case study'",
  "slug": "url-slug e.g. 'company-name-viact-case-study-location'",
  "hero_image_brief": "Nano Banana image prompt: 35-50 words, APAC industrial setting, realistic, safety context, 1200x630px",
  "hero_alt_text": "SEO alt text 10-20 words. Include viAct + product + company/location context.",
  "solution_1_alt_text": "SEO alt text for solution subsection 1 image. 10-20 words. Describe what the viAct system is detecting/monitoring.",
  "solution_2_alt_text": "SEO alt text for solution subsection 2 image. 10-20 words.",
  "section_alt_text": "SEO alt text for main site photo. 10-20 words. Company + viAct product + location."
}}

Rules:
- All body fields: plain text only, no markdown headers, no bullet points
- metric values: use real numbers from references if provided, else use [bracketed placeholders]
- metric descriptions: max 15 words, start with 'through', 'by', or 'via'
- testimonial roles: role title ONLY, no company name (company is auto-added)
- meta_title: MUST be ≤60 chars
- meta_description: MUST be 150-160 chars
- keywords: comma-separated plain string
- slug: lowercase, hyphens only, no special chars
- solution_sub1 and solution_sub2 must each cover a DIFFERENT viAct product/module"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]


# ── Validation ────────────────────────────────────────────────────────────────

def _validate(content: dict) -> list[str]:
    errors = []
    meta_title = content.get("meta_title", "")
    if len(meta_title) > 60:
        errors.append(f"meta_title: {len(meta_title)} chars (must be ≤60)")

    meta_desc = content.get("meta_description", "")
    if not (140 <= len(meta_desc) <= 165):
        errors.append(f"meta_description: {len(meta_desc)} chars (must be 140-165)")

    for field in ["challenge_body", "solution_body", "impact_body", "solution_sub1_body", "solution_sub2_body"]:
        val = content.get(field, "")
        if len(val.split()) < 40:
            errors.append(f"{field}: too short ({len(val.split())} words, need ≥40)")

    for field in ["challenge_title", "solution_title", "solution_sub1_title", "solution_sub2_title", "impact_title"]:
        if not content.get(field, "").strip():
            errors.append(f"{field}: empty")

    for i in (1, 2):
        if not content.get(f"testimonial_{i}_quote", "").strip():
            errors.append(f"testimonial_{i}_quote: empty")

    if not content.get("keywords", "").strip():
        errors.append("keywords: empty")

    return errors


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_case_study(
    company: str,
    industry: str,
    location: str,
    products_used: list[str],
    references: str = "",
    custom_instructions: str = "",
    run_tavily: bool = True,
    progress_callback=None,
) -> dict:
    """
    Generate a full viAct case study page.
    Returns {"cms_fields": {...}, "quality_gate_errors": [...], "generation_meta": {...}}
    """
    emit = progress_callback or print

    emit("Step 1/3 — Researching company context...")
    research = _tavily_research(company, industry, location) if run_tavily else ""

    emit("Step 2/3 — Scraping viAct case study reference page...")
    ref_content = _scrape_reference(VIACT_CASE_STUDY_REF)

    emit("Step 3/3 — Generating case study (Llama 3.3 70B)...")
    messages = _build_prompt(
        company=company,
        industry=industry,
        location=location,
        products_used=products_used,
        references=references,
        research_context=research,
        ref_page_content=ref_content,
        custom_instructions=custom_instructions,
    )

    retry_count = 0
    quality_gate_errors: list[str] = []

    raw = _groq_call(messages)
    try:
        content = json.loads(raw)
    except json.JSONDecodeError:
        content = {}

    errors = _validate(content)
    if errors:
        emit(f"Quality gate: {errors} — retrying once...")
        retry_messages = messages + [
            {"role": "assistant", "content": raw},
            {"role": "user", "content": f"Fix these issues and regenerate the full JSON:\n" + "\n".join(f"- {e}" for e in errors)},
        ]
        raw2 = _groq_call(retry_messages)
        try:
            content = json.loads(raw2)
        except json.JSONDecodeError:
            pass
        quality_gate_errors = _validate(content)
        retry_count = 1

    # ── Auto-derive fields (no LLM needed) ────────────────────────────────────
    content["h2"]                  = content.get("hero_h1", "")
    content["url"]                 = f"https://www.viact.ai/case-studies/{content.get('slug', '')}"
    content["filter_tag"]          = industry
    content["tags"]                = [industry]
    content["industry_alt_text"]   = industry
    content["location_alt_text"]   = location
    content["testimonial_1_company"] = content.get("company_name", company)
    content["testimonial_2_company"] = content.get("company_name", company)
    content["list_page_description"] = content.get("meta_description", "")
    for i in (1, 2, 3):
        v = content.get(f"metric_{i}_value", "")
        l = content.get(f"metric_{i}_label", "")
        d = content.get(f"metric_{i}_description", "")
        content[f"metric_{i}_alt_text"] = f"{v} {l} {d}".strip()

    return {
        "cms_fields": content,
        "quality_gate_errors": quality_gate_errors,
        "generation_meta": {
            "company": company,
            "industry": industry,
            "location": location,
            "products_used": products_used,
            "model_used": PRIMARY_MODEL,
            "retry_count": retry_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

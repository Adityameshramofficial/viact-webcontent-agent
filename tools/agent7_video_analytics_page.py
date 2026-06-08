"""
Agent 7 — Video Analytics Item Page Generator

Generates all Wix CMS text fields for one of viAct's 27 video analytics
detection-type item pages (e.g. "Fall Detection", "PPE Detection").

Input:  detection_name (str)
Output: {"cms_fields": {...}, "quality_gate_errors": [...], "generation_meta": {...}}
"""
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

PRIMARY_MODEL  = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

VA_DETECTIONS = [
    "Open Edge Detections",
    "Work Under Suspended Load Monitoring",
    "Proximity Detection & Warning",
    "Fall Detection",
    "Unauthorized Intrusion Detection",
    "Danger Zone Entry Detection",
    "Near Miss Detection",
    "Theft Detection",
    "Workforce Heat Maps",
    "Fire & Smoke Detection",
    "Wildfire Detection",
    "Missing Barricade Detection",
    "Weapon Detection",
    "Perimeter Intrusion Detection",
    "Loitering Detection",
    "Fight & Violence Detection",
    "Worker Smoking Detection",
    "Anomaly Detection",
    "Pedestrian Detection",
    "Worker Fatigue Detection",
    "Stairway Risks Detection",
    "Overcrowding Detection",
    "Facial Recognition System",
    "Unconscious Worker Detection",
    "Traffic Jam Detection",
    "Illegal Parking Detection",
    "Automatic Number Plate Recognition",
]


VIACT_VA_REFERENCE_URL = "https://www.viact.ai/fall-detection"


# ── Research helpers ──────────────────────────────────────────────────────────

def _tavily_va_research(detection_name: str) -> str:
    """Fetch live stats/incidents for this detection type. 2 credits. Returns ≤1200 chars."""
    import requests
    queries = [
        f"{detection_name} construction site safety incidents statistics 2025",
        f"{detection_name} AI computer vision regulation requirement",
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
    combined = "\n".join(snippets[:6])
    return combined[:1200]


def _scrape_viact_va_style() -> str:
    """Scrape an existing viAct VA page for style/tone reference. Returns ≤2000 chars."""
    try:
        from agent2_data_extractor import extract_competitor_content
        result = extract_competitor_content([VIACT_VA_REFERENCE_URL])
        return result.get(VIACT_VA_REFERENCE_URL, {}).get("markdown", "")[:2000]
    except Exception:
        return ""


# ── LLM wrapper (identical pattern to agent6) ────────────────────────────────

def _groq_call(messages: list[dict], max_tokens: int = 6000, temperature: float = 0.65) -> str:
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


# ── Prompt builder ────────────────────────────────────────────────────────────

def _build_prompt(detection_name: str, research_context: str = "", style_reference: str = "") -> list[dict]:
    system = (
        "You are a senior B2B content writer for viAct, an AI construction safety platform.\n"
        "Write for Wix CMS dynamic item pages — each page covers one specific AI detection capability.\n"
        "viAct uses edge AI cameras + cloud dashboard for real-time detection on construction sites.\n"
        "Tone: technical, authoritative, specific. APAC/construction focus. No generic marketing fluff.\n"
        "All body text must be plain text only — no markdown headers, no bullet symbols inside JSON strings.\n"
        "Use newline characters (\\n) to separate paragraphs or bullet items within a single field."
    )

    style_block = (
        f"\n=== VIACT STYLE REFERENCE (match this tone, structure, and specificity exactly) ===\n{style_reference[:2000]}\n"
        if style_reference else ""
    )
    research_block = (
        f"\n=== LIVE RESEARCH (Tavily — use real stats/incidents, do not invent numbers) ===\n{research_context}\n"
        if research_context else ""
    )

    prompt = f"""Generate all Wix CMS text fields for the "{detection_name}" video analytics item page.
{style_block}{research_block}

viAct's platform detects {detection_name} in real time using edge AI cameras deployed on construction sites,
oil & gas facilities, and industrial sites across APAC. The system runs 24/7 with instant alerts.

Return a JSON object with EXACTLY these fields:

{{
  "title": "{detection_name}",

  "h1": "Hero H1 headline — bold claim about {detection_name} AI. Max 12 words. e.g. 'Stop Falls Before They Happen with AI-Powered Detection'",
  "h2": "Hero H2 subheadline — expand on H1 with viAct angle. Max 20 words.",
  "h3": "Hero H3 supporting line — specific benefit or stat. Max 20 words.",
  "first_paragraph": "3-paragraph intro (plain text, ~150 words total). Paragraph 1: what {detection_name} is and why it matters on job sites. Paragraph 2: how traditional methods fail and the human cost. Paragraph 3: how viAct's AI solves this. Separate paragraphs with \\n\\n.",

  "t1": "Section title: 'What Makes {detection_name} Challenging on Job Sites?' (exact phrasing)",
  "td": "Challenges body (~250 words). Start with 1 intro sentence. Then write exactly 8 bullet points, each on its own line starting with a dash and space (- ). End with 2 closing paragraphs. Use \\n for line breaks between bullets. No markdown bold.",

  "t2": "Section title: 'How Computer Vision Enables {detection_name}' (exact phrasing)",
  "t2_ct2": "Step 1 title — one word: 'Choose'",
  "t2_cdesc2": "Step 1 description (~40 words): choosing the right camera placement and configuration for {detection_name} detection on site.",
  "t2_t1": "Step 2 title — one word: 'Connect'",
  "t2_1d": "Step 2 description (~40 words): connecting cameras to viAct's edge AI platform and configuring {detection_name} detection zones.",
  "t3_1t": "Step 3 title — one word: 'Capture'",
  "t3_1d": "Step 3 description (~40 words): the AI captures and analyzes {detection_name} events in real time, generating instant alerts.",
  "t4_t1": "Step 4 title — one word: 'Control'",
  "t4_td": "Step 4 description (~40 words): site managers control compliance via the viAct dashboard — reports, trends, audit trails.",

  "s6_title": "Where Is {detection_name} Needed Most? (exact phrasing with the detection name)",
  "s6_descriptions": "Intro paragraph (~60 words): overview of industries and scenarios where {detection_name} is critical. Mention APAC context.",
  "s6_t1": "Use case 1 title — industry or scenario (3-6 words)",
  "s6_desc1": "Use case 1 description (~40 words): specific application of {detection_name} in this industry/scenario.",
  "s6_t2": "Use case 2 title",
  "s6_desc2": "Use case 2 description (~40 words)",
  "s6_t3": "Use case 3 title",
  "s6_desc3": "Use case 3 description (~40 words)",
  "s6_t4": "Use case 4 title",
  "s6_desc4": "Use case 4 description (~40 words)",
  "s6_t5": "Use case 5 title",
  "s6_desc5": "Use case 5 description (~40 words)",

  "s7_title": "Case study headline (1 sentence, ~12 words). e.g. 'How a Singapore Developer Eliminated Fall Risk with viAct AI'",
  "construction": "Industry label for case study — e.g. 'Construction' or 'Oil & Gas' (whichever fits {detection_name} best)",
  "singapore": "Location label for case study — e.g. 'Singapore' or 'Hong Kong' (realistic APAC location)",
  "open_edge_detection": "viAct module label used in case study — e.g. '{detection_name} AI Module'",
  "problem_description": "The Problem (~60 words): specific safety challenge the client faced before viAct. No company name needed.",
  "solution_description": "The Solution (~60 words): how viAct's {detection_name} AI was deployed and what it changed operationally.",
  "viact_impact_descriptions": "The viAct impAct (~60 words): quantified outcomes — incident reduction %, compliance improvement, audit results. Use [X%] placeholders if uncertain.",

  "s8_title": "Why Choose viAct {detection_name} Over Traditional Safety Methods? (exact phrasing with detection name)",
  "s8_description": "Intro line (~20 words): one punchy sentence positioning viAct vs manual/legacy methods for {detection_name}.",
  "s8_1": "Stat/benefit bullet 1 (~15 words). Start with a bold number or claim. e.g. '[80%] fewer incidents through continuous 24/7 AI monitoring vs manual spot-checks'",
  "s8_2": "Stat/benefit bullet 2 (~15 words)",
  "s8_3": "Stat/benefit bullet 3 (~15 words)",
  "s8_4": "Stat/benefit bullet 4 (~15 words)",
  "s8_5": "Stat/benefit bullet 5 (~15 words)",
  "s8_6": "Stat/benefit bullet 6 (~15 words)",
  "s8_7": "Stat/benefit bullet 7 (~15 words)",

  "meta_title": "SEO title. MUST include '| viAct' at end. MUST be ≤60 chars. e.g. '{detection_name} AI for Construction | viAct'",
  "meta_descriptions": "SEO meta description. MUST be between 150 and 160 characters exactly. Count carefully. Include '{detection_name}', 'viAct', and a benefit.",
  "keywords": "6-8 SEO keywords, comma-separated. Mix detection keyword + construction + AI + APAC. e.g. '{detection_name.lower()} AI, construction safety monitoring, viAct video analytics'",

  "hero_image_alt_text": "Alt text for hero image (10-15 words). Include {detection_name} + viAct + construction site context.",
  "image_alt_text_1": "Alt text for section image 1 (10-15 words).",
  "image_alt_text_2": "Alt text for section image 2 (10-15 words).",
  "image_alt_text_3": "Alt text for section image 3 (10-15 words).",
  "image_alt_text_4": "Alt text for section image 4 (10-15 words).",
  "s7_image_alt_text": "Alt text for case study section image (10-15 words). Include construction site + {detection_name} context."
}}

Rules:
- All body fields: plain text only, no markdown symbols (#, **, *, etc.)
- Use \\n\\n to separate paragraphs within a field
- Use \\n- to start each bullet point in the td field
- meta_title: MUST be ≤60 chars total including '| viAct'
- meta_descriptions: MUST be 150-160 characters — count carefully
- keywords: comma-separated plain string, no JSON array
- s8_1 through s8_7: short punchy bullets, use [X%] bracket placeholders for unverified stats
- All 6 alt text fields MUST be filled"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": prompt},
    ]


# ── Validation ────────────────────────────────────────────────────────────────

def _validate(cms: dict, detection_name: str) -> list[str]:
    errors = []

    meta_title = cms.get("meta_title", "")
    if len(meta_title) > 60:
        errors.append(f"meta_title: {len(meta_title)} chars (must be ≤60)")
    if "viAct" not in meta_title and "viact" not in meta_title.lower():
        errors.append("meta_title: missing '| viAct'")

    meta_desc = cms.get("meta_descriptions", "")
    if not (130 <= len(meta_desc) <= 165):
        errors.append(f"meta_descriptions: {len(meta_desc)} chars (must be 130-165)")

    for field in ["first_paragraph", "td", "problem_description", "solution_description",
                  "viact_impact_descriptions", "s6_descriptions"]:
        val = cms.get(field, "")
        if len(val.split()) < 30:
            errors.append(f"{field}: too short ({len(val.split())} words, need ≥30)")

    for field in ["h1", "h2", "t1", "t2", "s6_title", "s8_title", "s7_title"]:
        if not cms.get(field, "").strip():
            errors.append(f"{field}: empty")

    for i in range(1, 8):
        if not cms.get(f"s8_{i}", "").strip():
            errors.append(f"s8_{i}: empty")

    for i in range(1, 6):
        if not cms.get(f"s6_t{i}", "").strip():
            errors.append(f"s6_t{i}: empty")

    if not cms.get("keywords", "").strip():
        errors.append("keywords: empty")

    return errors


# ── Main entry point ──────────────────────────────────────────────────────────

def generate_va_page(
    detection_name: str,
    progress_callback=None,
    run_tavily: bool = True,
) -> dict:
    """
    Generate all Wix CMS text fields for one video analytics item page.
    run_tavily=False skips Tavily (0 credits) — useful for bulk runs.
    Returns {"cms_fields": {...}, "quality_gate_errors": [...], "generation_meta": {...}}
    """
    emit = progress_callback or print

    research_context = ""
    style_reference  = ""

    if run_tavily:
        emit(f"Step 1/3 — Fetching live research for '{detection_name}' (2 Tavily credits)...")
        research_context = _tavily_va_research(detection_name)
    else:
        emit(f"Step 1/3 — Skipping Tavily (run_tavily=False).")

    emit("Step 2/3 — Fetching viAct style reference (Firecrawl)...")
    style_reference = _scrape_viact_va_style()

    emit(f"Step 3/3 — Generating CMS fields (Llama 3.3 70B)...")
    messages = _build_prompt(detection_name, research_context, style_reference)

    raw = _groq_call(messages, max_tokens=6000)

    try:
        cms = json.loads(raw)
    except json.JSONDecodeError:
        cms = {}

    errors = _validate(cms, detection_name)
    retry_count = 0

    if errors:
        emit(f"Quality gate: {errors} — retrying once...")
        raw_trimmed = raw[:4000] + "\n...[truncated]" if len(raw) > 4000 else raw
        retry_messages = messages + [
            {"role": "assistant", "content": raw_trimmed},
            {"role": "user", "content": "Fix these issues and regenerate the COMPLETE JSON from scratch:\n" + "\n".join(f"- {e}" for e in errors)},
        ]
        raw2 = _groq_call(retry_messages, max_tokens=6000)
        try:
            cms = json.loads(raw2)
        except json.JSONDecodeError:
            pass
        errors = _validate(cms, detection_name)
        retry_count = 1

    # Hard post-processing: enforce limits the LLM may still miss
    meta_desc = cms.get("meta_descriptions", "")
    if len(meta_desc) > 160:
        cms["meta_descriptions"] = meta_desc[:160].rsplit(" ", 1)[0].rstrip(",. ")

    # Ensure title is always set correctly
    cms["title"] = detection_name

    return {
        "cms_fields": cms,
        "quality_gate_errors": errors,
        "generation_meta": {
            "detection_name": detection_name,
            "model_used": PRIMARY_MODEL,
            "retry_count": retry_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    }

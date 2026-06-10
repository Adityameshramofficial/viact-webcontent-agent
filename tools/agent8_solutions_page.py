"""
Agent 8 — Solutions Page Generator

Generates all Wix CMS text fields for one of viAct's Solutions item pages
(e.g. "Job Hazard Analysis Software", "Behaviour Based Safety Software").

Input:  solution_name (str)
Output: {"cms_fields": {...}, "quality_gate_errors": [...], "generation_meta": {...}}
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

VIACT_SOLUTIONS_REF_URL = "https://www.viact.ai/solutions/job-hazard-analysis-software"

SOLUTIONS_LIST = [
    "Job Hazard Analysis Software",
    "Incident Management Software",
    "Lone Worker Monitoring System",
    "Vehicle Control Management Software",
    "Industrial Space Management Solution",
    "Behaviour Based Safety Software",
    "Scaffolding Safety Software",
    "Housekeeping Assessment Software Solution",
    "Crane Safety Software",
    "Inventory Utilization Monitoring System",
    "Ergonomics Assessment Software",
    "Forklift Safety System",
    "Area Control Safety System",
    "Industrial Workforce Productivity Monitoring Solution",
]


# ── Research helpers ───────────────────────────────────────────────────────────

def _google_news_rss(query: str, max_results: int = 3) -> list:
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
                "url": item.findtext("link", ""),
                "title": item.findtext("title", ""),
                "content": re.sub(r"<[^>]+>", "", item.findtext("description", ""))[:300],
            })
        return results
    except Exception:
        return []


def _tavily_research(solution_name: str) -> str:
    import requests
    queries = [
        f"{solution_name} workplace safety statistics market 2025",
        f"{solution_name} AI computer vision compliance APAC",
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
            if resp.status_code in (429, 432):
                for r in _google_news_rss(q):
                    snippets.append(f"[{r.get('title','')}] {r.get('content','')[:200]}")
                continue
            for r in resp.json().get("results", []):
                snippets.append(f"[{r.get('title','')}] {r.get('content','')[:200]}")
        except Exception:
            for r in _google_news_rss(q):
                snippets.append(f"[{r.get('title','')}] {r.get('content','')[:200]}")
    return "\n".join(snippets[:6])[:1200]


def _scrape_viact_reference() -> str:
    try:
        from agent2_data_extractor import extract_competitor_content
        result = extract_competitor_content([VIACT_SOLUTIONS_REF_URL])
        return result.get(VIACT_SOLUTIONS_REF_URL, {}).get("markdown", "")[:2000]
    except Exception:
        return ""


def _make_slug(solution_name: str) -> str:
    s = solution_name.lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"\s+", "-", s.strip())
    return f"/solutions/{s}"


# ── LLM wrapper ───────────────────────────────────────────────────────────────

def _groq_call(messages: list, max_tokens: int = 6000, temperature: float = 0.65) -> str:
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


# ── Prompt builders ────────────────────────────────────────────────────────────

_MAIN_SCHEMA = """{
  "tagline": "Benefit-first tagline – Sub-benefit or context (≤80 chars)",
  "short_description": "1-2 sentences with solution name + viAct + key benefit",
  "long_description": "Same or slightly expanded version",
  "testimonial_quote": "Specific outcome quote from EHS/safety professional",
  "testimonial_attribution": "- Role | Company Type",
  "diff_section_title": "What difference does [Solution Name] make?",
  "trend_title": "Trend headline (3-6 words)",
  "trend_description": "Trend description including a specific % metric",
  "stats_title": "Statistics headline (3-6 words)",
  "stats_description": "Stats description with 2-3 specific numbers",
  "outcome_title": "Outcome headline (3-6 words)",
  "outcome_description": "Outcome description with measurable result",
  "cta_text": "2-sentence CTA paragraph: bold headline + description (Transform How You...)",
  "cta_button": "Action phrase (3-6 words)",
  "new_cta_text": "Action tagline for bottom of page (e.g. Transform [X] with AI—get insights, not just data)",
  "features_title": "Key features of [Solution Name]",
  "feature_tab_1": "Feature category name",
  "feature_tab_2": "Feature category name",
  "feature_tab_3": "Feature category name",
  "feature_tab_4": "Feature category name",
  "feature_tab_5": "Feature category name",
  "bullet_1": "Verb + specific feature description (1 sentence)",
  "bullet_2": "...", "bullet_3": "...", "bullet_4": "...", "bullet_5": "...",
  "bullet_6": "...", "bullet_7": "...", "bullet_8": "...", "bullet_9": "...",
  "bullet_10": "...", "bullet_11": "...", "bullet_12": "...", "bullet_13": "...",
  "bullet_14": "...",
  "metric_1_value": "95%", "metric_1_desc": "...",
  "metric_2_value": "90%+", "metric_2_desc": "...",
  "metric_3_value": "10x", "metric_3_desc": "...",
  "uvp_1_title": "Edge AI / viAct differentiator name",
  "uvp_1_desc": "1-2 sentence description",
  "uvp_2_title": "...", "uvp_2_desc": "...",
  "uvp_3_title": "...", "uvp_3_desc": "...",
  "uvp_4_title": "...", "uvp_4_desc": "...",
  "uvp_5_title": "Responsible AI", "uvp_5_desc": "GDPR-compliant data handling description",
  "slug": "/solutions/kebab-case-name",
  "seo_meta_title": "AI-Powered [Solution Topic]: [Key Benefit] with [Specific Tech] | viAct (≤60 chars)",
  "seo_meta_description": "EXACTLY 130-165 chars — count every character",
  "seo_keywords": "keyword 1, keyword 2, keyword 3, keyword 4, keyword 5",
  "hero_image_alt": "Best Computer Vision AI Enabled [Solution Name] Software",
  "trends_image_alt": "[Specific Benefit/Outcome] with [Standard/Tech e.g. RULA & REBA / PPE Compliance / AI Detection]",
  "stats_image_alt": "Computer Vision AI enabled [Analytics description] for [Solution Topic]",
  "outcome_image_alt": "Reduced [Risk/Cost/Incident] with AI [Solution Name]",
  "dashboard_image_alt": "Top Computer Vision AI Enabled [Solution Name] Software",
  "feature_1_img_alt": "[Feature 1 name] with viAct [Solution Name]",
  "feature_2_img_alt": "[Solution Name] for [Feature 2 specific use case]",
  "feature_3_img_alt": "viAct [Solution Name] for [Feature 3 specific topic]",
  "feature_4_img_alt": "[Feature 4 name] for [Compliance/Industry use case]",
  "feature_5_img_alt": "[Feature 5 name] for [Specific detection/monitoring]",
  "uvp_1_img_alt": "Edge AI for [Solution primary use case]",
  "uvp_2_img_alt": "Computer Vision AI for [Solution primary use case]",
  "uvp_3_img_alt": "IoT for [Solution primary use case]",
  "uvp_4_img_alt": "AI Co-Pilot for [Solution primary use case]",
  "uvp_5_img_alt": "Responsible AI in [Solution Name] Software",
  "check_img_alt": "Best [Solution Name] Software for [Primary Industry e.g. Manufacturing / Construction]",
  "list_image_alt": "Best EHSQ Management Software for [primary industry]"
}"""

_FAQ_SCHEMA = """{
  "faq_1_q": "Question?", "faq_1_a": "Answer — 2-3 sentences, 40-60 words max.",
  "faq_2_q": "...", "faq_2_a": "...",
  "faq_3_q": "...", "faq_3_a": "...",
  "faq_4_q": "...", "faq_4_a": "...",
  "faq_5_q": "...", "faq_5_a": "..."
}"""

_IMAGE_PROMPTS_SCHEMA = """{
  "image_prompts": [
    {"placement": "Hero Section (1155x764px)",      "prompt": "...", "alt_text": "..."},
    {"placement": "Dashboard Section (1620x705px)", "prompt": "...", "alt_text": "..."},
    {"placement": "Key Feature 1 (800x672px)",      "prompt": "...", "alt_text": "..."},
    {"placement": "Key Feature 2 (755x561px)",      "prompt": "...", "alt_text": "..."},
    {"placement": "Key Feature 3 (699x498px)",      "prompt": "...", "alt_text": "..."},
    {"placement": "Key Feature 4 (794x504px)",      "prompt": "...", "alt_text": "..."},
    {"placement": "Key Feature 5 (851x572px)",      "prompt": "...", "alt_text": "..."}
  ]
}"""


def _build_main_prompt(solution_name: str, research: str, style_ref: str) -> list:
    system = (
        "You are a senior B2B SaaS copywriter for viAct.ai — AI-powered industrial safety platform. "
        "viAct uses: Computer Vision, Edge AI, IoT, Video Analytics, Generative AI. "
        "Core differentiators: Edge deployment, 90%+ accuracy, scenario-based AI, Responsible AI (GDPR). "
        "Tone: confident, benefit-driven, specific metrics, EHS professional audience. "
        "Output ONLY valid JSON matching the schema exactly."
    )
    user = (
        f"Generate ALL Wix CMS text fields for this viAct Solutions page.\n\n"
        f"SOLUTION: {solution_name}\n\n"
        f"LIVE RESEARCH:\n{research or '(none — use domain knowledge)'}\n\n"
        f"STYLE REFERENCE:\n{style_ref[:600] if style_ref else '(not available)'}\n\n"
        "RULES:\n"
        "- tagline: use em dash pattern 'Benefit – Context', ≤80 chars\n"
        "- trend/stats/outcome: each must include at least one specific % or number\n"
        "- 14 bullets: start each with a verb (Detect/Monitor/Identify/Generate/Automate/Track)\n"
        "- 5 UVPs: Exclusive Edge Advantage, Scenario-based Vision Intelligence, Seamless IoT Integration, Generative AI-based Workflow, Responsible AI\n"
        "- new_cta_text: punchy 1-line action tagline for bottom of page CTA, e.g. 'Transform [X] with AI—get insights, not just data'\n"
        "- seo_meta_title: format EXACTLY 'AI-Powered [Solution Topic]: [Key Benefit] with [Specific Tech/Standard] | viAct' — ≤60 chars\n"
        "- seo_meta_description: mention CCTV computer vision + specific solution tech — EXACTLY 130-165 chars\n"
        "- seo_keywords: 5 specific keywords, include solution name + monitoring + software + risk assessment + tech standard\n"
        "- slug: /solutions/[kebab-case-name]\n"
        "- hero_image_alt: 'Best Computer Vision AI Enabled [Solution Name] Software'\n"
        "- trends_image_alt: '[Specific Outcome/Benefit] with [Tech Standard or Method]' e.g. 'Fatigue Free Workspaces with RULA & REBA Assessment'\n"
        "- stats_image_alt: 'Computer Vision AI enabled [Analytics] for [Topic]'\n"
        "- outcome_image_alt: 'Reduced [Risk/Incident] with AI [Solution]'\n"
        "- dashboard_image_alt: 'Top Computer Vision AI Enabled [Solution Name] Software'\n"
        "- feature_N_img_alt: rotate these patterns — '[Feature] with viAct [Solution]' / '[Solution] for [Use Case]' / 'viAct [Solution] for [Topic]' / '[Feature] for [Compliance]' / '[Feature] for [Detection]'\n"
        "- uvp_1_img_alt: 'Edge AI for [solution use case]'\n"
        "- uvp_2_img_alt: 'Computer Vision AI for [solution use case]'\n"
        "- uvp_3_img_alt: 'IoT for [solution use case]'\n"
        "- uvp_4_img_alt: 'AI Co-Pilot for [solution use case]'\n"
        "- uvp_5_img_alt: 'Responsible AI in [Solution Name] Software'\n"
        "- check_img_alt: 'Best [Solution Name] Software for [Primary Industry]'\n\n"
        f"JSON SCHEMA:\n{_MAIN_SCHEMA}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_faq_prompt(solution_name: str, cms: dict) -> list:
    desc = cms.get("short_description", "")
    tabs = ", ".join(cms.get(f"feature_tab_{i}", "") for i in range(1, 6) if cms.get(f"feature_tab_{i}"))
    system = (
        "You are a senior B2B SaaS copywriter for viAct.ai. "
        "Generate FAQ Q&A pairs for an EHS software product page. "
        "Each answer: exactly 2-3 sentences, 40-60 words MAX — concise, benefit-driven. "
        "Include viAct product name in at least 2 answers. "
        "Output ONLY valid JSON."
    )
    user = (
        f"Generate exactly 5 FAQ pairs for viAct's {solution_name} page.\n"
        f"Product: {desc}\nKey features: {tabs}\n\n"
        "Cover these 5 angles: (1) What is it & key benefit, (2) How AI/CV works for this solution, "
        "(3) Industries & compliance standards it supports, "
        "(4) ROI / measurable outcomes, (5) Deployment (Edge AI vs cloud).\n\n"
        "WORD LIMIT: Each answer must be 40-60 words. Count carefully — do not exceed 60 words.\n\n"
        f"JSON SCHEMA:\n{_FAQ_SCHEMA}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _build_image_prompts_prompt(solution_name: str, cms: dict) -> list:
    tabs = [cms.get(f"feature_tab_{i}", f"Feature {i}") for i in range(1, 6)]
    system = (
        "You are a visual art director for viAct.ai — AI-powered industrial EHS software platform. "
        "Generate Nano Banana image prompts that match viAct's exact visual style. "
        "No text or logos inside the generated image. Output ONLY valid JSON."
    )
    user = (
        f"Generate exactly 7 Nano Banana image prompts for the viAct '{solution_name}' solutions page.\n\n"
        f"Feature tabs: {', '.join(tabs)}\n\n"
        "PROMPT RULES — follow the exact visual style described for each placement:\n\n"
        "HERO SECTION (1155x764px):\n"
        "Composite image on a pure black (#000000) background. Center: a sleek MacBook Pro showing the "
        "viAct dashboard UI (map visualization view with colored zone markers, camera grid sidebar, "
        "events list). Overlapping top-right: a floating CCTV camera feed card showing a high-angle "
        f"aerial view of an industrial/construction site relevant to '{solution_name}', "
        "with neon green #00FF41 AI bounding boxes on compliant workers/equipment and "
        "red #FF3B3B alert boxes on detected violations/hazards, 2px stroke, "
        "small monospace confidence percentage labels. Photorealistic product composite, 4K, 1155x764px.\n\n"
        "DASHBOARD SECTION (1620x705px):\n"
        "Clean wide-format product mockup on a pure white (#FFFFFF) background. "
        "A sleek MacBook laptop displaying the viAct platform UI (site map with zone markers, "
        "device list panel, live camera thumbnails, events/alerts feed). "
        "A smartphone leaning against it showing a mobile alert notification with an aerial site photo. "
        "No workers. No industrial site visible — only the software interface. "
        "Photorealistic product render, soft drop shadow, 1620x705px.\n\n"
        "KEY FEATURE 1 (800x672px), KEY FEATURE 2 (755x561px), KEY FEATURE 3 (699x498px), "
        "KEY FEATURE 4 (794x504px), KEY FEATURE 5 (851x572px):\n"
        "For each feature tab, generate a realistic workplace photo of a relevant worker/EHS professional "
        "in their actual work environment (not stock pose — natural action shot). "
        "Overlaid: a floating viAct software UI card (white card, rounded corners, subtle shadow) "
        "showing interface elements relevant to that feature (checkboxes, forms, status badges, "
        "alert notifications, compliance score gauge, map snippet — whichever fits the feature). "
        "Natural workplace lighting. The person and environment must clearly match the feature topic. "
        "Use the exact pixel dimensions for each feature as specified in the schema.\n\n"
        f"JSON SCHEMA:\n{_IMAGE_PROMPTS_SCHEMA}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


# ── Quality gate ───────────────────────────────────────────────────────────────

def _validate(cms: dict) -> list:
    errors = []

    meta_title = cms.get("seo_meta_title", "")
    if len(meta_title) > 60:
        errors.append(f"seo_meta_title: {len(meta_title)} chars (must be ≤60)")
    if not meta_title.strip():
        errors.append("seo_meta_title: empty")

    meta_desc = cms.get("seo_meta_description", "")
    if not (130 <= len(meta_desc) <= 165):
        errors.append(f"seo_meta_description: {len(meta_desc)} chars (must be 130-165)")

    for field in ["tagline", "short_description", "testimonial_quote", "cta_text", "new_cta_text", "seo_keywords"]:
        if not cms.get(field, "").strip():
            errors.append(f"{field}: empty")

    for i in range(1, 6):
        if not cms.get(f"feature_tab_{i}", "").strip():
            errors.append(f"feature_tab_{i}: empty")

    empty_bullets = sum(1 for i in range(1, 15) if not cms.get(f"bullet_{i}", "").strip())
    if empty_bullets > 4:
        errors.append(f"bullets: only {14 - empty_bullets} filled (need ≥10)")

    for i in range(1, 4):
        if not cms.get(f"metric_{i}_value", "").strip():
            errors.append(f"metric_{i}_value: empty")

    for i in range(1, 6):
        if not cms.get(f"uvp_{i}_title", "").strip():
            errors.append(f"uvp_{i}_title: empty")

    slug = cms.get("slug", "")
    if not slug.startswith("/solutions/"):
        errors.append("slug: must start with /solutions/")

    return errors


# ── Main entry point ───────────────────────────────────────────────────────────

def generate_solutions_page(
    solution_name: str,
    progress_callback=None,
    run_tavily: bool = True,
) -> dict:
    """
    Generate all Wix CMS text fields for a viAct Solutions item page.
    Returns {"cms_fields": {...}, "quality_gate_errors": [...], "generation_meta": {...}}
    """
    emit = progress_callback or print

    if run_tavily:
        emit(f"Step 1/5 — Fetching live research for '{solution_name}'...")
        research = _tavily_research(solution_name)
    else:
        emit("Step 1/5 — Skipping Tavily research.")
        research = ""

    emit("Step 2/5 — Fetching viAct style reference...")
    style_ref = _scrape_viact_reference()

    emit("Step 3/5 — Generating main content (Llama 3.3 70B)...")
    main_messages = _build_main_prompt(solution_name, research, style_ref)
    raw_main = _groq_call(main_messages, max_tokens=6000)
    try:
        cms = json.loads(raw_main)
    except json.JSONDecodeError:
        cms = {}

    emit("Step 4/5 — Generating FAQs...")
    faq_messages = _build_faq_prompt(solution_name, cms)
    raw_faq = _groq_call(faq_messages, max_tokens=3500)
    try:
        cms.update(json.loads(raw_faq))
    except json.JSONDecodeError:
        pass

    cms["solution_name"] = solution_name
    if not cms.get("slug"):
        cms["slug"] = _make_slug(solution_name)

    errors = _validate(cms)
    retry_count = 0

    if errors:
        critical = [e for e in errors if any(k in e for k in
                    ["seo_meta_title", "tagline", "feature_tab", "uvp_", "metric_", "seo_meta_description"])]
        if critical:
            emit(f"Quality gate: {critical[:3]} — retrying main content once...")
            retry_msg = main_messages + [
                {"role": "assistant", "content": raw_main[:4000] + ("\n...[truncated]" if len(raw_main) > 4000 else "")},
                {"role": "user", "content": "Fix these issues and regenerate the COMPLETE JSON:\n" + "\n".join(f"- {e}" for e in critical)},
            ]
            try:
                raw_main2 = _groq_call(retry_msg, max_tokens=6000)
                cms_retry = json.loads(raw_main2)
                faqs = {k: v for k, v in cms.items() if k.startswith("faq_")}
                cms = cms_retry
                cms.update(faqs)
                cms["solution_name"] = solution_name
                if not cms.get("slug"):
                    cms["slug"] = _make_slug(solution_name)
            except Exception:
                pass
            retry_count = 1

    # Hard post-processing
    meta_desc = cms.get("seo_meta_description", "")
    if len(meta_desc) > 165:
        cms["seo_meta_description"] = meta_desc[:165].rsplit(" ", 1)[0].rstrip(",. ")
    meta_title = cms.get("seo_meta_title", "")
    if len(meta_title) > 60:
        cms["seo_meta_title"] = meta_title[:60].rsplit(" ", 1)[0].rstrip(",. |")

    errors = _validate(cms)

    # Image prompts generated last — uses final (post-retry) feature tab names
    emit("Step 5/5 — Generating Nano Banana image prompts...")
    img_messages = _build_image_prompts_prompt(solution_name, cms)
    raw_img = _groq_call(img_messages, max_tokens=3500)
    try:
        image_prompts = json.loads(raw_img).get("image_prompts", [])
    except json.JSONDecodeError:
        image_prompts = []
    image_prompts = image_prompts[:7]

    return {
        "cms_fields": cms,
        "image_prompts": image_prompts,
        "quality_gate_errors": errors,
        "generation_meta": {
            "solution_name": solution_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "retry_count": retry_count,
            "model": PRIMARY_MODEL,
            "slug": cms.get("slug", _make_slug(solution_name)),
        },
    }

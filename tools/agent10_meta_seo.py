"""
Agent 10 — Meta / SEO Tag Generator

Generates all SEO meta tags, Open Graph tags, Twitter Card tags, and
JSON-LD schema markup for any viAct.ai page type.

Input:  page_type, page_title, page_description, target_keyword, url_slug
Output: {"meta_tags": {...}, "schema_json_ld": {...}, "seo_scores": {...}}
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

VIACT_BASE_URL = "https://www.viact.ai"
VIACT_OG_IMAGE = "https://www.viact.ai/og-default.jpg"

PAGE_TYPE_CONTEXT = {
    "industry":    "Industry-specific AI safety platform page targeting EHS managers in a specific sector.",
    "product":     "Product feature page showcasing a specific viAct AI detection/safety product.",
    "solution":    "Solution page for a specific workplace safety software solution.",
    "blog":        "SEO blog article on an industrial safety or AI technology topic.",
    "case_study":  "Customer case study showing measurable safety outcomes with viAct.",
    "homepage":    "viAct.ai homepage — AI computer vision safety platform for industrial sites.",
    "video_analytics": "Video analytics detection type page (e.g. Fall Detection, PPE Detection).",
}

SCHEMA_TYPES = {
    "industry":    "WebPage",
    "product":     "Product",
    "solution":    "SoftwareApplication",
    "blog":        "BlogPosting",
    "case_study":  "Article",
    "homepage":    "WebSite",
    "video_analytics": "WebPage",
}


# ── LLM wrapper ───────────────────────────────────────────────────────────────

def _groq_call(messages: list, max_tokens: int = 3000) -> str:
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))
    kwargs = dict(
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.3,
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


# ── Slug normaliser ───────────────────────────────────────────────────────────

def _clean_slug(slug: str) -> str:
    slug = slug.strip().lstrip("/")
    if not slug:
        return ""
    return f"/{slug}"


# ── Schema builder ────────────────────────────────────────────────────────────

def _build_schema(page_type: str, title: str, description: str,
                  canonical: str, keyword: str) -> dict:
    schema_type = SCHEMA_TYPES.get(page_type, "WebPage")
    base = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "name": title,
        "description": description,
        "url": canonical,
        "publisher": {
            "@type": "Organization",
            "name": "viAct.ai",
            "url": VIACT_BASE_URL,
            "logo": {
                "@type": "ImageObject",
                "url": f"{VIACT_BASE_URL}/logo.png"
            }
        }
    }
    if page_type == "blog":
        base["@type"] = "BlogPosting"
        base["headline"] = title
        base["keywords"] = keyword
        base["datePublished"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        base["author"] = {"@type": "Organization", "name": "viAct Editorial Team"}
    elif page_type == "product":
        base["@type"] = "Product"
        base["name"] = title
        base["brand"] = {"@type": "Brand", "name": "viAct"}
        base["category"] = "AI Safety Software"
    elif page_type == "solution":
        base["@type"] = "SoftwareApplication"
        base["applicationCategory"] = "BusinessApplication"
        base["operatingSystem"] = "Cloud"
    elif page_type == "homepage":
        base["@type"] = "WebSite"
        base["potentialAction"] = {
            "@type": "SearchAction",
            "target": f"{VIACT_BASE_URL}/search?q={{search_term_string}}",
            "query-input": "required name=search_term_string"
        }
    return base


# ── Main generator ────────────────────────────────────────────────────────────

def generate_meta_tags(
    page_type: str,
    page_title: str,
    page_description: str,
    target_keyword: str,
    url_slug: str,
    secondary_keywords: list = None,
    faqs: list = None,
    progress_callback=None,
) -> dict:
    """
    Generate complete SEO meta + schema for any viAct page.
    Returns dict with meta_tags, schema_json_ld, seo_scores, html_snippet.
    """
    def _prog(msg: str):
        if progress_callback:
            progress_callback(msg)

    canonical = f"{VIACT_BASE_URL}{_clean_slug(url_slug)}"
    page_ctx = PAGE_TYPE_CONTEXT.get(page_type, "Web page for viAct.ai industrial AI platform.")
    sec_kw_str = ", ".join(secondary_keywords or [])

    _prog("Generating meta tags...")

    prompt = f"""You are an SEO expert specialising in B2B SaaS and industrial tech.
Generate all SEO meta tags for a viAct.ai webpage.

PAGE DETAILS:
- Type: {page_type} — {page_ctx}
- Title: {page_title}
- Description: {page_description}
- Primary keyword: "{target_keyword}"
- Secondary keywords: {sec_kw_str or "derive 3-4 related terms"}
- Canonical URL: {canonical}

STRICT RULES:
- meta_title: max 60 chars, start with primary keyword if possible
- meta_description: max 155 chars, include keyword + benefit + soft CTA
- og_title: can be slightly longer/more engaging than meta_title (max 70 chars)
- og_description: max 200 chars, benefit-focused
- twitter_title: max 70 chars
- twitter_description: max 200 chars, punchy
- All secondary keywords must be real search terms, not brand names

OUTPUT: single JSON object:
{{
  "meta_title": "...",
  "meta_description": "...",
  "og_title": "...",
  "og_description": "...",
  "og_image_alt": "Alt text describing viAct AI dashboard or industrial safety scene relevant to {page_title}",
  "twitter_title": "...",
  "twitter_description": "...",
  "focus_keyword": "{target_keyword}",
  "secondary_keywords": ["kw1", "kw2", "kw3", "kw4"],
  "robots": "index, follow",
  "canonical": "{canonical}",
  "faq_schema_pairs": [
    {{"question": "Frequently asked question about {page_title}?", "answer": "Concise answer (max 50 words)."}}
  ]
}}

Generate 3 faq_schema_pairs relevant to {page_title} for FAQ schema markup."""

    raw = _groq_call([{"role": "user", "content": prompt}])

    try:
        data = json.loads(raw)
    except Exception:
        fence = re.search(r"```(?:json)?\s*([\s\S]+?)```", raw)
        data = json.loads(fence.group(1)) if fence else {}

    meta_tags = {
        "meta_title":        data.get("meta_title", page_title[:60]),
        "meta_description":  data.get("meta_description", page_description[:155]),
        "og_title":          data.get("og_title", data.get("meta_title", page_title)),
        "og_description":    data.get("og_description", data.get("meta_description", "")),
        "og_image":          VIACT_OG_IMAGE,
        "og_image_alt":      data.get("og_image_alt", f"viAct AI platform — {page_title}"),
        "og_type":           "article" if page_type in ("blog", "case_study") else "website",
        "og_url":            canonical,
        "twitter_card":      "summary_large_image",
        "twitter_title":     data.get("twitter_title", data.get("meta_title", page_title)),
        "twitter_description": data.get("twitter_description", data.get("meta_description", "")),
        "twitter_site":      "@viactai",
        "canonical":         canonical,
        "robots":            data.get("robots", "index, follow"),
        "focus_keyword":     data.get("focus_keyword", target_keyword),
        "secondary_keywords": data.get("secondary_keywords", []),
    }

    # Build JSON-LD schemas
    webpage_schema = _build_schema(page_type, page_title, page_description, canonical, target_keyword)
    faq_pairs = data.get("faq_schema_pairs", faqs or [])
    faq_schema = None
    if faq_pairs:
        faq_schema = {
            "@context": "https://schema.org",
            "@type": "FAQPage",
            "mainEntity": [
                {
                    "@type": "Question",
                    "name": f["question"],
                    "acceptedAnswer": {"@type": "Answer", "text": f["answer"]}
                }
                for f in faq_pairs if f.get("question")
            ]
        }

    # Build ready-to-paste HTML snippet
    html_lines = [
        f'<title>{meta_tags["meta_title"]}</title>',
        f'<meta name="description" content="{meta_tags["meta_description"]}">',
        f'<link rel="canonical" href="{canonical}">',
        f'<meta name="robots" content="{meta_tags["robots"]}">',
        f'<meta name="keywords" content="{target_keyword}, {", ".join(meta_tags["secondary_keywords"])}">',
        "",
        "<!-- Open Graph -->",
        f'<meta property="og:title" content="{meta_tags["og_title"]}">',
        f'<meta property="og:description" content="{meta_tags["og_description"]}">',
        f'<meta property="og:image" content="{meta_tags["og_image"]}">',
        f'<meta property="og:image:alt" content="{meta_tags["og_image_alt"]}">',
        f'<meta property="og:type" content="{meta_tags["og_type"]}">',
        f'<meta property="og:url" content="{canonical}">',
        "",
        "<!-- Twitter Card -->",
        f'<meta name="twitter:card" content="{meta_tags["twitter_card"]}">',
        f'<meta name="twitter:site" content="{meta_tags["twitter_site"]}">',
        f'<meta name="twitter:title" content="{meta_tags["twitter_title"]}">',
        f'<meta name="twitter:description" content="{meta_tags["twitter_description"]}">',
        "",
        "<!-- JSON-LD: WebPage/Product Schema -->",
        "<script type=\"application/ld+json\">",
        json.dumps(webpage_schema, indent=2),
        "</script>",
    ]
    if faq_schema:
        html_lines += [
            "",
            "<!-- JSON-LD: FAQ Schema -->",
            "<script type=\"application/ld+json\">",
            json.dumps(faq_schema, indent=2),
            "</script>",
        ]

    seo_scores = {
        "meta_title_length":       len(meta_tags["meta_title"]),
        "meta_title_ok":           len(meta_tags["meta_title"]) <= 60,
        "description_length":      len(meta_tags["meta_description"]),
        "description_ok":          len(meta_tags["meta_description"]) <= 155,
        "keyword_in_title":        target_keyword.lower() in meta_tags["meta_title"].lower(),
        "keyword_in_description":  target_keyword.lower() in meta_tags["meta_description"].lower(),
        "has_og_tags":             bool(meta_tags["og_title"]),
        "has_twitter_tags":        bool(meta_tags["twitter_title"]),
        "has_faq_schema":          faq_schema is not None,
        "has_webpage_schema":      True,
        "secondary_keywords_count": len(meta_tags["secondary_keywords"]),
    }

    score = sum(1 for v in seo_scores.values() if v is True or v is True)
    seo_scores["overall_score"] = f"{score}/9"

    return {
        "meta_tags":      meta_tags,
        "schema_json_ld": {
            "webpage": json.dumps(webpage_schema, indent=2),
            "faq":     json.dumps(faq_schema, indent=2) if faq_schema else None,
        },
        "html_snippet":   "\n".join(html_lines),
        "seo_scores":     seo_scores,
        "faq_pairs":      faq_pairs,
        "generation_meta": {
            "page_type":   page_type,
            "page_title":  page_title,
            "canonical":   canonical,
            "model":       PRIMARY_MODEL,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }


# ── CLI entry ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--type",     required=True, help="industry|product|solution|blog|case_study|homepage|video_analytics")
    parser.add_argument("--title",    required=True)
    parser.add_argument("--desc",     required=True)
    parser.add_argument("--keyword",  required=True)
    parser.add_argument("--slug",     required=True, help="e.g. /solutions/ppe-detection")
    args = parser.parse_args()

    result = generate_meta_tags(
        page_type=args.type,
        page_title=args.title,
        page_description=args.desc,
        target_keyword=args.keyword,
        url_slug=args.slug,
        progress_callback=print,
    )
    print(json.dumps(result, indent=2))

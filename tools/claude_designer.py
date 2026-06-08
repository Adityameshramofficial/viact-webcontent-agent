"""
Claude Designer — Generates production HTML product pages via Anthropic API.

Gary's approach: feed Claude the structured content + viact.ai design reference,
and let Claude generate a complete HTML page that matches the website quality.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

VIACT_DESIGN_SYSTEM = """
viAct.ai Design System:
- Background: #0a0a0a (page), #0e0e0e (cards)
- Borders: 1px solid #1e1e1e (cards)
- Primary accent: #ff6a3d (orange — CTA buttons, highlights, top card borders)
- Secondary accent: #3fb950 (green — positive stats, success indicators)
- Text: #c9d1d9 (body copy), #8b949e (muted/labels), #ffffff (headings)
- Font: Jost (Google Fonts) — weights 400, 600, 700, 800
- Card style: bg #0e0e0e, border 1px solid #1e1e1e, border-top 3px solid #ff6a3d, border-radius 10px, padding 20-24px
- Primary buttons: bg #ff6a3d, color #fff, border-radius 6px, font-weight 700, padding 12px 24px, no border
- Secondary buttons: bg transparent, color #ff6a3d, border 1px solid rgba(255,106,61,0.4), border-radius 6px
- Tag/pill style: bg rgba(255,106,61,0.08), color #ff6a3d, border 1px solid rgba(255,106,61,0.18), border-radius 20px, font-size 0.65rem, font-weight 600
- Section padding: 80px 0
- Max content width: 1200px centered
- Step numbers: color #ff6a3d, font-size 2.5rem, font-weight 800
"""


def generate_product_html(content: dict, reference_page_md: str = "") -> str:
    """
    Call Claude API (claude-sonnet-4-6) to generate a production HTML product page.

    Args:
        content: JSON dict from agent3_product_page.generate_product_page()
        reference_page_md: Scraped markdown from existing viact.ai page (tone reference)

    Returns:
        Complete HTML string (single-file, all CSS in <style> tag)
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError("Run: pip install anthropic")

    api_key = get_env("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not set in .env — add it to use Claude Design.")

    client = anthropic.Anthropic(api_key=api_key)

    content_json = json.dumps(content, indent=2, ensure_ascii=False)
    product_name = content.get("product_name", "viAct Product")

    reference_block = ""
    if reference_page_md and reference_page_md not in ("[ACCESS DENIED]", ""):
        reference_block = (
            f"\n\n=== REFERENCE PAGE CONTENT (viact.ai — use for tone and structure reference) ===\n"
            f"{reference_page_md[:2000]}"
        )

    design_ctx = content.get("design_context", {})
    hero = content.get("hero_section", {})
    features = content.get("key_features", [])
    steps = content.get("how_it_works", [])
    use_cases = content.get("use_cases", [])
    stats = content.get("social_proof", {}).get("stats", [])
    testimonials = content.get("testimonials", [])
    faqs = content.get("faqs", [])
    cta = content.get("cta_section", {})
    problem = content.get("problem_statement", {})
    seo = content.get("seo_suite", {})
    image_prompts = {p["id"]: p for p in content.get("image_prompts", [])}

    prompt = f"""You are a senior frontend developer. Build a production-ready, single-file HTML product page for viAct.ai's "{product_name}" product.

## Design System
{VIACT_DESIGN_SYSTEM}

## Structured Content (use ALL fields — do not skip any section)
```json
{content_json[:6000]}
```
{reference_block}

## Build Instructions

### General
- Single HTML file. All CSS in a `<style>` tag in `<head>`. No external CSS. No JavaScript.
- Google Fonts: `<link href="https://fonts.googleapis.com/css2?family=Jost:wght@400;600;700;800&display=swap" rel="stylesheet">`
- Fully responsive. Mobile breakpoint at 768px.
- `<meta name="description" content="...">` and `<title>` from seo_suite.
- `box-sizing: border-box` on *.

### Section Order
nav → hero → problem → features → how-it-works → use-cases → stats-bar → testimonials → faq → cta → footer

### Nav
- Dark bg (#0a0a0a), border-bottom 1px solid #1a1a1a, sticky top, height 64px.
- Left: viAct logo text in white (font-weight 800) with orange dot.
- Right: 3 nav links in #8b949e + "Book a Demo" button in #ff6a3d.
- Mobile: collapse nav links, keep logo and CTA button.

### Hero
- Full-width section, min-height 88vh, dark bg (#0a0a0a), centered content, padding-top 120px.
- Small orange tag above H1: product category (e.g. "AI SAFETY PLATFORM").
- H1 from hero_section.h1 — white, font-size 3rem (mobile: 2rem), font-weight 800, letter-spacing -1px.
- Subheadline below H1 — #8b949e, font-size 1.1rem, max-width 600px.
- Hero body text — #c9d1d9, font-size 0.9rem, max-width 540px, margin-top 16px.
- Two CTA buttons side by side: primary (#ff6a3d filled) + secondary (outlined).
- Hero image placeholder: styled `<div>` with gradient background (dark to slightly lighter), height 400px, border-radius 12px, border 1px solid #1e1e1e. Show image prompt text as a small caption inside.

### Problem Statement
- Section bg #080808, padding 60px 0.
- H2 heading in white. Body text in #8b949e.
- 3 pain point cards in a row — dark cards with red left border (#ef4444), icon (⚠️), text.

### Key Features (4 cards)
- Section bg #0a0a0a, H2 heading centered.
- 2×2 grid on desktop, 1-col on mobile.
- Each card: bg #0e0e0e, border 1px solid #1e1e1e, border-top 3px solid #ff6a3d, border-radius 10px, padding 24px.
- Icon area: 40×40px div, bg rgba(255,106,61,0.1), border 1px solid rgba(255,106,61,0.2), border-radius 10px, emoji from icon_hint.
- Feature title in white, description in #8b949e.
- Feature image placeholder div below text: height 160px, gradient bg, border-radius 8px, shows image prompt.

### How It Works (3 steps)
- Section bg #080808, numbered steps.
- Each step: large orange step number (font-size 4rem, color #ff6a3d, opacity 0.15), title in white, description in #8b949e.
- Horizontal layout on desktop: number | text | connecting arrow between steps.

### Use Cases (3 cards)
- Section bg #0a0a0a.
- 3-column grid on desktop, 1-col on mobile.
- Each card: dark card with green left accent (#3fb950), industry badge (pill), title, description.

### Stats Bar
- Section bg #ff6a3d (full width orange), padding 48px 0.
- 3 stats in a row: large metric in white (font-size 2.8rem, font-weight 800), label below in rgba(255,255,255,0.8).
- Dividers between stats.

### Testimonials (3 cards)
- Section bg #0a0a0a, 3-column grid.
- Each card: dark card, opening quote mark in #ff6a3d (font-size 3rem, opacity 0.3), quote in italic #c9d1d9, role below in #8b949e.
- 5-star rating line above quote.

### FAQ (5 items)
- Section bg #080808.
- Each FAQ: border-bottom 1px solid #1e1e1e, question in white (font-weight 600, padding 20px 0), answer in #8b949e (padding-bottom 20px). All expanded (no JS accordion).

### CTA Section
- Full-width section with gradient: from #ff6a3d to #e55a2b, padding 80px 0, centered.
- Large heading in white, description in rgba(255,255,255,0.85), CTA button in white text + dark bg.

### Footer
- Bg #060606, border-top 1px solid #1a1a1a, padding 40px 0.
- viAct logo text + tagline, nav links, copyright in #2a2a2a.

Return ONLY the complete HTML — start with `<!DOCTYPE html>`. No explanations, no markdown fences."""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    html = message.content[0].text.strip()

    if not html.startswith("<!DOCTYPE"):
        start = html.find("<!DOCTYPE")
        if start >= 0:
            html = html[start:]

    return html

"""
Agent 4 — Universal Dynamic Page Builder

Schema-driven content generator for ANY viAct website page type.
ONE agent, infinite page types. Each page type has its own skill.md file.

ARCHITECTURE:
  - workflows/{slug}.md = skill file per page type (schema + tone + learnings)
  - Agent reads skill.md before generating, writes learnings after
  - Reuses agent2 scraping, agent3 Groq pattern, SYSTEM_INSTRUCTION
  - Self-improving: _analyze_learnings() → appended to skill.md → injected next run
"""
import json
import os
import re
import sys
from datetime import datetime, timezone

import requests

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env
from agent2_data_extractor import ACCESS_DENIED
from generate_webpage_content import SYSTEM_INSTRUCTION

PRIMARY_MODEL  = "llama-3.3-70b-versatile"
FALLBACK_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"

SKILLS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "workflows")

# ── Groq wrapper — identical pattern to agent3 ────────────────────────────────

def _groq_chat(client, messages: list, max_tokens: int = 6000,
               temperature: float = 0.65, response_format: dict | None = None) -> str:
    kwargs = dict(messages=messages, max_tokens=max_tokens, temperature=temperature)
    if response_format:
        kwargs["response_format"] = response_format
    try:
        resp = client.chat.completions.create(model=PRIMARY_MODEL, **kwargs)
        return resp.choices[0].message.content
    except Exception as e:
        err = str(e)
        if "429" in err or "413" in err or "rate_limit" in err.lower() or "too large" in err.lower():
            resp = client.chat.completions.create(model=FALLBACK_MODEL, **kwargs)
            return resp.choices[0].message.content
        raise


ZERO_HALLUCINATION_BLOCK = """
ZERO-HALLUCINATION CONTRACT (non-negotiable):
- Use ONLY the Markdown text provided in REFERENCE_CONTENT and COMPETITOR_CONTENT below.
- If a competitor entry is marked "[ACCESS DENIED]", write "[Data unavailable]" — NEVER invent their features or claims.
- Every statistic must come from provided reference material or a named regulatory source (MOM, BCA, UAE OSHAD, ISO 45001). Write "industry data shows" if none available.
- List all source URLs used in data_sources_used.
- List all ACCESS DENIED URLs in access_denied_urls.

REFERENCE PRIORITY RULE:
- Reference Material = REAL viAct internal data and verified stats — treat as ground truth.
- Cite exact numbers from references. Do NOT round, paraphrase, or replace with generic figures.
"""

# ── Utilities — identical to agent3 ──────────────────────────────────────────

def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return raw.strip()


def _build_competitor_block(competitor_data: dict) -> str:
    lines = []
    for url, result in competitor_data.items():
        md = result.get("markdown", ACCESS_DENIED)
        wc = result.get("word_count", 0)
        if md == ACCESS_DENIED:
            lines.append(f"=== URL: {url} ===\n[ACCESS DENIED — do not invent this content]")
        else:
            lines.append(f"=== URL: {url} ({wc} words) ===\n{md[:1500]}")
    return "\n\n".join(lines) if lines else "(No competitor content provided)"


def _page_type_slug(page_type: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", page_type.lower()).strip("_")


# ── Skill.md — read / write / list ───────────────────────────────────────────

def _skill_path(page_type: str) -> str:
    return os.path.join(SKILLS_DIR, f"{_page_type_slug(page_type)}.md")


def load_skill_md(page_type: str) -> dict:
    """
    Read workflows/{slug}.md → return:
      {"schema": list, "tone_notes": str, "learnings": str, "exists": bool}
    Returns {"exists": False} if file doesn't exist or isn't a dynamic-page-skill.
    """
    path = _skill_path(page_type)
    if not os.path.isfile(path):
        return {"exists": False}

    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except Exception:
        return {"exists": False}

    # Must be a dynamic-page-skill
    if "type: dynamic-page-skill" not in text:
        return {"exists": False}

    def _extract_section(heading: str) -> str:
        pattern = rf"## {re.escape(heading)}\n(.*?)(?=\n## |\Z)"
        m = re.search(pattern, text, re.DOTALL)
        return m.group(1).strip() if m else ""

    # Parse schema from JSON code block
    schema = []
    schema_raw = _extract_section("Schema")
    json_match = re.search(r"```json\n(.*?)```", schema_raw, re.DOTALL)
    if json_match:
        try:
            schema = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            schema = []

    tone_notes  = _extract_section("Tone & Style Notes")
    learnings   = _extract_section("Learnings")

    # Return last 5 learning entries to keep prompt lean
    learning_lines = [l for l in learnings.splitlines() if l.strip()]
    recent = "\n".join(learning_lines[-20:]) if learning_lines else ""

    return {
        "exists": True,
        "schema": schema,
        "tone_notes": tone_notes,
        "learnings": recent,
    }


def save_skill_md(
    page_type: str,
    schema: list[dict],
    tone_notes: str = "",
    learnings_to_append: str = "",
) -> None:
    """
    Create or update workflows/{slug}.md.
    - File doesn't exist → create full template with schema + tone_notes
    - File exists → update schema section + append to Learnings
    """
    path = _skill_path(page_type)
    slug = _page_type_slug(page_type)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    schema_json = json.dumps(schema, indent=2)

    if not os.path.isfile(path):
        # Create new skill file
        content = f"""---
name: {page_type}
type: dynamic-page-skill
created: {today}
---

## Schema
```json
{schema_json}
```

## Tone & Style Notes
{tone_notes if tone_notes else "(Run 'Analyze Reference' to auto-extract tone notes from your reference page)"}

## Quality Gates
{_derive_quality_gates(schema)}

## Learnings
{learnings_to_append if learnings_to_append else "(Learnings will appear here after your first generation run)"}
"""
        os.makedirs(SKILLS_DIR, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return

    # File exists — update schema + append learnings
    with open(path, encoding="utf-8") as f:
        text = f.read()

    # Update schema section
    new_schema_block = f"## Schema\n```json\n{schema_json}\n```"
    text = re.sub(
        r"## Schema\n```json\n.*?```",
        new_schema_block,
        text,
        flags=re.DOTALL,
    )

    # Update tone notes if provided
    if tone_notes:
        text = re.sub(
            r"(## Tone & Style Notes\n).*?(?=\n## |\Z)",
            f"\\g<1>{tone_notes}\n",
            text,
            flags=re.DOTALL,
        )

    # Append to learnings
    if learnings_to_append:
        if "## Learnings" in text:
            text = text.rstrip() + f"\n{learnings_to_append}\n"
        else:
            text += f"\n## Learnings\n{learnings_to_append}\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def list_skill_pages() -> list[str]:
    """Return list of page type names from existing dynamic-page-skill workflow files."""
    result = []
    if not os.path.isdir(SKILLS_DIR):
        return result
    for fname in sorted(os.listdir(SKILLS_DIR)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(SKILLS_DIR, fname)
        try:
            with open(fpath, encoding="utf-8") as f:
                content = f.read(500)
            if "type: dynamic-page-skill" not in content:
                continue
            m = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
            if m:
                result.append(m.group(1).strip())
        except Exception:
            pass
    return result


def _derive_quality_gates(schema: list[dict]) -> str:
    """Auto-generate quality gate summary from schema for the skill.md file."""
    lines = []
    for field in schema:
        name = field["name"]
        ftype = field.get("type", "text")
        parts = []
        if ftype == "array":
            parts.append(f"exactly {field.get('count', '?')} items")
        if "max_chars" in field:
            parts.append(f"max {field['max_chars']} chars")
        if "max_words" in field:
            parts.append(f"max {field['max_words']} words")
        if field.get("required"):
            parts.append("required")
        if parts:
            lines.append(f"- {name}: {', '.join(parts)}")
    return "\n".join(lines) if lines else "(none defined)"


# ── Tone extraction + self-improvement ───────────────────────────────────────

def extract_tone_notes(reference_markdown: str, page_type: str) -> str:
    """
    Single Groq call: analyze scraped reference page → extract tone/style patterns.
    Returns 3-5 bullet points describing the writing style to replicate.
    """
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))

    messages = [
        {"role": "system", "content": "You are a content strategist analyzing writing style."},
        {"role": "user", "content": f"""Analyze this web page content and extract 3-5 bullet points describing:
- Sentence structure and length
- Tone (formal/casual, technical level)
- How headlines are written (fragment vs full sentence, outcome-first vs feature-first)
- Any recurring patterns in how benefits are described

PAGE TYPE: {page_type}

PAGE CONTENT:
{reference_markdown[:2500]}

Return ONLY the bullet points. Start each with "- ". No intro text."""},
    ]
    try:
        return _groq_chat(client, messages, max_tokens=400, temperature=0.3)
    except Exception:
        return ""


def analyze_learnings(result: dict, page_type: str) -> str:
    """
    After generation: analyze cms_fields + errors + retry_count.
    Returns formatted learnings string to append to skill.md.
    Returns empty string if clean run with no insights.
    """
    errors   = result.get("quality_gate_errors", [])
    retries  = result.get("generation_meta", {}).get("retry_count", 0)
    topic    = result.get("page_topic", "")
    ts       = result.get("generation_meta", {}).get("timestamp", datetime.now(timezone.utc).isoformat())

    # Clean run, no retries, no errors → no learnings worth saving
    if not errors and retries == 0:
        return ""

    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))

    error_block = "\n".join(errors) if errors else "(none)"
    cms_sample  = json.dumps({k: str(v)[:100] for k, v in result.get("cms_fields", {}).items()}, indent=2)[:800]

    messages = [
        {"role": "system", "content": "You are a prompt engineer reviewing AI content generation results."},
        {"role": "user", "content": f"""A {page_type} page was generated for topic "{topic}".
Retries needed: {retries}
Quality gate errors: {error_block}
Sample output: {cms_sample}

Write 1-3 short bullet points (max 15 words each) describing what instructions should be added or emphasized next time to avoid these issues.
Start each bullet with "- ". No intro text. If errors are minor or expected, return nothing."""},
    ]
    try:
        bullets = _groq_chat(client, messages, max_tokens=200, temperature=0.3).strip()
        if not bullets or not bullets.startswith("-"):
            return ""
        header = f"### {ts[:19].replace('T', ' ')} UTC (Run: {topic}, {retries} {'retry' if retries == 1 else 'retries'})"
        return f"\n{header}\n{bullets}\n"
    except Exception:
        return ""


# ── Tavily research ───────────────────────────────────────────────────────────

def _tavily_search(query: str, max_results: int = 5) -> list[dict]:
    payload = {
        "api_key": get_env("TAVILY_API_KEY"),
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
    }
    try:
        resp = requests.post("https://api.tavily.com/search", json=payload, timeout=20)
        resp.raise_for_status()
        return resp.json().get("results", [])
    except Exception:
        return []


def research_topic(page_topic: str, page_type: str) -> str:
    """Run 2 Tavily searches → combined research summary string."""
    queries = [
        f"{page_topic} workplace safety statistics challenges",
        f"{page_topic} AI computer vision monitoring industry trends",
    ]
    snippets = []
    for q in queries:
        for r in _tavily_search(q, max_results=4):
            snippet = r.get("content", "")[:400]
            if snippet:
                snippets.append(f"[{r.get('url', '')}]\n{snippet}")
    return "\n\n".join(snippets) if snippets else ""


# ── JSON spec builder ─────────────────────────────────────────────────────────

def _build_json_spec(field_schema: list[dict]) -> str:
    lines = ["Return a JSON object with EXACTLY these fields:"]
    lines.append("{")

    for field in field_schema:
        name  = field["name"]
        ftype = field.get("type", "text")
        desc  = field.get("description", "")
        comment = f"  // {desc}" if desc else ""

        if ftype == "array":
            count = field.get("count", 3)
            item_fields = field.get("item_fields", {})
            if item_fields:
                item_spec = ", ".join(
                    f'"{k}": "<{"max " + str(v["max_chars"]) + " chars" if "max_chars" in v else "max " + str(v["max_words"]) + " words" if "max_words" in v else "text"}>"'
                    for k, v in item_fields.items()
                )
            else:
                item_spec = '"title": "<text>", "body": "<text>"'
            lines.append(f'  "{name}": [{{{item_spec}}}],{comment}  EXACTLY {count} items')

        elif ftype == "image":
            lines.append(f'  "{name}": "<detailed realistic image prompt 30-50 words, APAC industrial setting>",{comment}')

        elif ftype in ("text", "seo"):
            parts = []
            if "max_chars" in field:
                parts.append(f"max {field['max_chars']} chars")
            if "max_words" in field:
                parts.append(f"max {field['max_words']} words")
            constraint = ", ".join(parts) if parts else "text"
            lines.append(f'  "{name}": "<{constraint}>",{comment}')

        else:
            lines.append(f'  "{name}": "<text>",{comment}')

    lines.append('  "data_sources_used": ["<url or source name>"],')
    lines.append('  "access_denied_urls": []')
    lines.append("}")
    return "\n".join(lines)


# ── Validator ─────────────────────────────────────────────────────────────────

def _validate_dynamic_page(content: dict, field_schema: list[dict]) -> list[str]:
    errors = []
    for field in field_schema:
        name  = field["name"]
        ftype = field.get("type", "text")
        value = content.get(name)

        if field.get("required", False) and not value:
            errors.append(f"{name}: required but missing or empty")
            continue
        if value is None:
            continue

        if ftype == "array":
            expected = field.get("count")
            if expected and isinstance(value, list) and len(value) != expected:
                errors.append(f"{name}: expected {expected} items, got {len(value)}")

        elif ftype in ("text", "seo"):
            text = str(value)
            if "max_chars" in field and len(text) > field["max_chars"]:
                errors.append(f"{name}: {len(text)} chars, limit is {field['max_chars']}")
            if "max_words" in field and len(text.split()) > field["max_words"]:
                errors.append(f"{name}: {len(text.split())} words, limit is {field['max_words']}")

    return errors


# ── Prompt assembler ──────────────────────────────────────────────────────────

def _build_messages(
    page_type: str,
    page_topic: str,
    field_schema: list[dict],
    reference_content: str,
    competitor_content: dict,
    research_results: str,
    viact_pages: list[str],
    custom_instructions: str,
    tone_notes: str = "",
    prior_learnings: str = "",
    correction_note: str = "",
) -> list[dict]:
    json_spec        = _build_json_spec(field_schema)
    competitor_block = _build_competitor_block(competitor_content)
    viact_links      = "\n".join(viact_pages[:30]) if viact_pages else "(none)"

    system = f"{ZERO_HALLUCINATION_BLOCK.strip()}\n\n{SYSTEM_INSTRUCTION}"

    parts = [
        f"PAGE TYPE: {page_type}",
        f"PAGE TOPIC: {page_topic}",
        "",
    ]

    if tone_notes:
        parts += [
            "TONE & STYLE NOTES (learned from reference page — follow exactly):",
            tone_notes,
            "",
        ]

    if prior_learnings:
        parts += [
            "LEARNINGS FROM PREVIOUS RUNS (apply these to avoid past mistakes):",
            prior_learnings,
            "",
        ]

    if custom_instructions:
        parts += [f"CUSTOM INSTRUCTIONS:\n{custom_instructions.strip()}", ""]

    if correction_note:
        parts += [
            "⚠️ CORRECTION REQUIRED — Previous output had violations. Fix them:",
            correction_note,
            "",
        ]

    parts += [
        "REFERENCE CONTENT (existing viAct page — match this tone, style, brand voice):",
        (reference_content[:3000] if reference_content else "(not provided)"),
        "",
        "COMPETITOR / RESEARCH CONTENT:",
        competitor_block,
        "",
    ]

    if research_results:
        parts += [
            "TAVILY RESEARCH (fresh industry data — use as supporting context):",
            research_results[:2500],
            "",
        ]

    parts += [
        "KNOWN viAct PAGES (use for internal links where relevant):",
        viact_links,
        "",
        "OUTPUT SPEC:",
        json_spec,
        "",
        "Return ONLY valid JSON. No markdown fences. No explanation. No text outside the JSON object.",
    ]

    return [
        {"role": "system", "content": system},
        {"role": "user",   "content": "\n".join(parts)},
    ]


# ── Main entry point ──────────────────────────────────────────────────────────

def build_dynamic_page(
    page_type: str,
    page_topic: str,
    field_schema: list[dict],
    reference_content: str,
    competitor_content: dict,
    research_results: str,
    viact_pages: list[str],
    custom_instructions: str = "",
    tone_notes: str = "",
    prior_learnings: str = "",
) -> dict:
    """
    Generate all CMS fields for any page type in a single Groq call.
    Validates against schema constraints — retries once if violations found.

    Returns:
      {page_type, page_topic, cms_fields, quality_gate_errors, generation_meta}
    """
    from groq import Groq
    client = Groq(api_key=get_env("GROQ_API_KEY"))

    retry_count = 0

    messages = _build_messages(
        page_type, page_topic, field_schema,
        reference_content, competitor_content,
        research_results, viact_pages, custom_instructions,
        tone_notes=tone_notes, prior_learnings=prior_learnings,
    )

    raw = _groq_chat(client, messages, max_tokens=6000,
                     response_format={"type": "json_object"})
    try:
        result = json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        result = {}

    errors = _validate_dynamic_page(result, field_schema)

    if errors:
        retry_count = 1
        correction_note = "\n".join(f"- {e}" for e in errors)
        retry_msgs = _build_messages(
            page_type, page_topic, field_schema,
            reference_content, competitor_content,
            research_results, viact_pages, custom_instructions,
            tone_notes=tone_notes, prior_learnings=prior_learnings,
            correction_note=correction_note,
        )
        raw2 = _groq_chat(client, retry_msgs, max_tokens=6000,
                          response_format={"type": "json_object"})
        try:
            result = json.loads(_strip_fences(raw2))
        except json.JSONDecodeError:
            pass
        errors = _validate_dynamic_page(result, field_schema)

    return {
        "page_type":          page_type,
        "page_topic":         page_topic,
        "cms_fields":         result,
        "quality_gate_errors": errors,
        "generation_meta": {
            "model_used":  PRIMARY_MODEL,
            "retry_count": retry_count,
            "timestamp":   datetime.now(timezone.utc).isoformat(),
        },
    }

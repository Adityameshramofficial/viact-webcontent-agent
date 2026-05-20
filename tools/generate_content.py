"""Generate platform-specific social media and blog content using Groq (Llama 3.3 70B)."""
import argparse
import json
import sys
import os

if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
if sys.stderr.encoding != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

SYSTEM_INSTRUCTION = """You are the content strategist for viact.ai — an AI-powered platform for construction site safety and monitoring. viact.ai uses computer vision and IoT to detect hazards (missing PPE, unsafe behaviors, restricted zone breaches) in real time.

Your tone is:
- Professional and authoritative, but approachable
- Safety-first: every piece of content reinforces the value of protecting workers
- Concise and data-driven where possible
- Never salesy or hyperbolic

You will receive a brief (topic, scraped article, or document extract) and return structured content for four platforms."""

PROMPT_TEMPLATE = """Based on the following brief, generate content for viact.ai across four platforms. Return ONLY valid JSON with no markdown fences, no commentary, nothing else outside the JSON object.

BRIEF:
{brief}

Required JSON format:
{{
  "linkedin": {{
    "copy": "Full LinkedIn post (150-300 words, professional tone, can use line breaks)",
    "hashtags": ["hashtag1", "hashtag2"]
  }},
  "twitter": {{
    "copy": "Tweet text (max 280 chars, punchy, includes a hook)",
    "hashtags": ["hashtag1", "hashtag2"]
  }},
  "instagram": {{
    "copy": "Instagram caption (engaging, emojis allowed, 100-200 words)",
    "hashtags": ["hashtag1", "hashtag2", "hashtag3", "hashtag4", "hashtag5"]
  }},
  "blog": {{
    "title": "SEO-optimised blog post title",
    "copy": "Full blog post (400-600 words, H2 subheadings using markdown ##, structured for SEO)"
  }},
  "image_prompt": "A descriptive prompt for an AI image generator visualising the theme in a construction site safety context"
}}"""


def generate(brief: str) -> dict:
    from groq import Groq

    client = Groq(api_key=get_env("GROQ_API_KEY"))

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": PROMPT_TEMPLATE.format(brief=brief[:4000])},
        ],
        temperature=0.7,
        max_tokens=8192,
        response_format={"type": "json_object"},
    )

    return json.loads(response.choices[0].message.content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate multi-platform content via Gemini")
    parser.add_argument("--brief", required=True, help="Topic or text brief")
    args = parser.parse_args()

    try:
        result = generate(args.brief)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

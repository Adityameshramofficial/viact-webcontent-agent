"""
Generate an image description / prompt via Groq (Llama 3.3 70B).
Falls back gracefully if the model is unavailable so the pipeline always completes.
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


def generate_image(prompt: str) -> dict:
    try:
        from groq import Groq

        client = Groq(api_key=get_env("GROQ_API_KEY"))

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "user", "content": (
                    "You are a professional AI art director. Rewrite the following concept "
                    "into a detailed, vivid image generation prompt suitable for Midjourney or DALL-E. "
                    "Return only the prompt text, nothing else.\n\n"
                    f"Concept: {prompt}"
                )},
            ],
            temperature=0.8,
            max_tokens=256,
        )

        refined_prompt = response.choices[0].message.content.strip()
        return {"image_url": "", "prompt": refined_prompt, "model": "llama-3.3-70b-versatile"}

    except Exception as e:
        # Non-blocking — pipeline continues without an image
        return {"image_url": "", "prompt": prompt, "warning": str(e)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate image prompt via Nano Banana Pro")
    parser.add_argument("--prompt", required=True, help="Image concept to refine")
    args = parser.parse_args()
    print(json.dumps(generate_image(args.prompt), ensure_ascii=False))

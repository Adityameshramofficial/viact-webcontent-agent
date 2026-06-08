"""
Image generation via Pollinations.ai — free, no API key needed.
"""
import re
import time
import urllib.parse
import requests


def generate_image(
    prompt: str,
    width: int = 1200,
    height: int = 630,
    model: str = "flux",
    seed: int = 42,
) -> bytes | None:
    """
    Generate an image from a text prompt via Pollinations.ai.
    Returns raw JPEG bytes on success, None on failure.
    Free — no API key required.
    Retries up to 3 times with 8s delay to handle queue-full (402) errors.
    """
    encoded = urllib.parse.quote(prompt, safe="")
    models_to_try = [model, "turbo"] if model != "turbo" else ["turbo", "flux"]

    for attempt in range(3):
        for m in models_to_try:
            url = (
                f"https://image.pollinations.ai/prompt/{encoded}"
                f"?width={width}&height={height}&model={m}&nologo=true&seed={seed}"
            )
            try:
                resp = requests.get(url, timeout=120, stream=False)
                if resp.status_code == 200 and resp.content:
                    return resp.content
                if resp.status_code == 402:
                    # Queue full — wait and retry
                    print(f"[generate_image] Queue full (model={m}), attempt {attempt+1}/3 — waiting 10s")
                    time.sleep(10)
                    continue
                print(f"[generate_image] HTTP {resp.status_code} model={m}")
            except Exception as e:
                print(f"[generate_image] Error: {e}")
        time.sleep(8)

    return None


def extract_dims(prompt: str, default_w: int = 1200, default_h: int = 630):
    """Extract WxH or W×H from prompt text. Returns (width, height)."""
    m = re.search(r"(\d{2,4})[x×](\d{2,4})", prompt, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    return default_w, default_h

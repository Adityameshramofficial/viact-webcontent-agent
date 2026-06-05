"""
Image generation via Pollinations.ai — free, no API key needed.
"""
import re
import urllib.parse
import requests


POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/{prompt}"


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
    """
    encoded = urllib.parse.quote(prompt, safe="")
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&model={model}&nologo=true&seed={seed}"
    )
    try:
        resp = requests.get(url, timeout=90, stream=False)
        if resp.status_code == 200 and resp.content:
            return resp.content
    except Exception:
        pass
    return None


def extract_dims(prompt: str, default_w: int = 1200, default_h: int = 630):
    """Extract WxH or W×H from prompt text. Returns (width, height)."""
    m = re.search(r"(\d{3,4})[x×](\d{3,4})", prompt, re.IGNORECASE)
    if m:
        return int(m.group(1)), int(m.group(2))
    return default_w, default_h

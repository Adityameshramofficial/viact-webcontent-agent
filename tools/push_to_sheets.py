"""Append generated content rows to a Google Sheet."""
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from utils import get_env

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
BASE_DIR = os.path.join(os.path.dirname(__file__), "..")
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")

COLUMNS = ["Date", "Platform", "Post Copy", "Hashtags", "Image URL", "Input Source", "Status"]


def get_sheets_service():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    creds = None
    if os.path.exists(TOKEN_PATH):
        creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return build("sheets", "v4", credentials=creds)


def ensure_header(service, sheet_id: str):
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range="Sheet1!A1:G1"
    ).execute()
    existing = result.get("values", [])
    if not existing or existing[0] != COLUMNS:
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range="Sheet1!A1",
            valueInputOption="RAW",
            body={"values": [COLUMNS]},
        ).execute()


def content_to_rows(content: dict, input_source: str, image_url: str) -> list:
    today = date.today().isoformat()
    rows = []

    for platform in ["linkedin", "twitter", "instagram"]:
        p = content.get(platform, {})
        copy = p.get("copy", "")
        hashtags = " ".join(f"#{h.lstrip('#')}" for h in p.get("hashtags", []))
        rows.append([today, platform.capitalize(), copy, hashtags, image_url, input_source, "Draft"])

    blog = content.get("blog", {})
    blog_copy = f"{blog.get('title', '')}\n\n{blog.get('copy', '')}"
    rows.append([today, "Blog", blog_copy, "", image_url, input_source, "Draft"])

    return rows


def push(content: dict, input_source: str = "", image_url: str = "") -> int:
    sheet_id = get_env("SHEET_ID")
    service = get_sheets_service()
    ensure_header(service, sheet_id)

    rows = content_to_rows(content, input_source, image_url)

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()

    return len(rows)


# ---------------------------------------------------------------------------
# Webpage Content pipeline — separate tab, separate schema
# All additions below are additive — existing push() is unchanged.
# ---------------------------------------------------------------------------

WEBPAGE_TAB = "Webpage Content"
WEBPAGE_COLUMNS = [
    "Date",               # A
    "Autorun#",           # B
    "Topic",              # C
    "Decision Logic",     # D — copy to Gary/Surendra's email
    "Webpage Body",       # E — full Markdown
    "SEO Suite (JSON)",   # F — meta title, desc, keywords
    "Schema FAQs (JSON)", # G — 5-item JSON array
    "Schema JSON-LD",     # H — paste into <head>
    "Extended FAQs (JSON)",  # I — 2 on-page only
    "GEO Package (JSON)", # J — opening 200 words + tips
    "Visual Strategy (JSON)", # K — Nano Banana prompts
    "Internal Links (JSON)",  # L
    "Competitor URLs",    # M
    "Input Source",       # N
    "Unverified",         # O — "Yes" if no reference provided
    "Status",             # P
]


def ensure_webpage_tab(service, sheet_id: str):
    """Create the 'Webpage Content' tab if absent and write the header row."""
    meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
    existing_titles = [s["properties"]["title"] for s in meta.get("sheets", [])]

    if WEBPAGE_TAB not in existing_titles:
        service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": WEBPAGE_TAB}}}]},
        ).execute()

    # Write header row (overwrite if different)
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"{WEBPAGE_TAB}!A1",
        valueInputOption="RAW",
        body={"values": [WEBPAGE_COLUMNS]},
    ).execute()


def push_webpage(
    content: dict,
    decision_logic: str = "",
    input_source: str = "",
    competitor_urls: list[str] | None = None,
    autorun_num: int | None = None,
    unverified: bool = False,
) -> int:
    """
    Append one row to the 'Webpage Content' tab.
    Returns 1 if successful.
    """
    sheet_id = get_env("SHEET_ID")
    service = get_sheets_service()
    ensure_webpage_tab(service, sheet_id)

    # Auto-increment autorun# if not passed
    if autorun_num is None:
        existing = service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range=f"{WEBPAGE_TAB}!A:A",
        ).execute()
        autorun_num = max(len(existing.get("values", [])), 1)

    seo = content.get("seo_suite", {})
    row = [
        date.today().isoformat(),
        str(autorun_num),
        content.get("topic", ""),
        decision_logic or content.get("decision_logic", ""),
        content.get("webpage_body", ""),
        json.dumps(seo, ensure_ascii=False),
        json.dumps(content.get("schema_faqs", []), ensure_ascii=False),
        content.get("schema_json_ld", ""),
        json.dumps(content.get("extended_faqs", []), ensure_ascii=False),
        json.dumps(content.get("geo_package", {}), ensure_ascii=False),
        json.dumps(content.get("nano_banana_prompts", content.get("visual_strategy", [])), ensure_ascii=False),
        json.dumps(content.get("internal_links", []), ensure_ascii=False),
        ", ".join(competitor_urls or []),
        input_source,
        "Yes" if unverified else "No",
        "Draft",
    ]

    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range=f"{WEBPAGE_TAB}!A1",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()

    return 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Push content rows to Google Sheets")
    parser.add_argument("--source", default="", help="Input source label (url/topic/file)")
    parser.add_argument("--image-url", default="", help="Image URL to attach to rows")
    parser.add_argument("--mode", choices=["social", "webpage"], default="social")
    args = parser.parse_args()

    try:
        content = json.load(sys.stdin)
        if args.mode == "webpage":
            count = push_webpage(content, input_source=args.source)
        else:
            count = push(content, input_source=args.source, image_url=args.image_url)
        print(json.dumps({"rows_written": count}))
    except Exception as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        sys.exit(1)

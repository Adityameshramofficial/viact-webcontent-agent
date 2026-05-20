# Workflow: Generate Social & Web Content

## Objective
Generate ready-to-publish content for LinkedIn, Twitter/X, Instagram, and Website/Blog from a topic brief, URL, or document. Deliver all posts as rows in the viact.ai Google Sheet.

## Required Inputs
| Input | Description |
|---|---|
| `--brief "<text>"` | A plain-text topic or description |
| `--url "<url>"` | A URL to scrape and repurpose |
| `--file "<path>"` | Path to a `.txt`, `.pdf`, or `.docx` document |

Provide exactly one of the above.

## Required Environment Variables (`.env`)
| Key | Description |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key for content generation |
| `SHEET_ID` | Google Sheets spreadsheet ID (from the sheet URL) |
| `NANO_BANANA_API_KEY` | Nano Banana 2 API key for image generation |
| `NANO_BANANA_API_URL` | Nano Banana 2 API endpoint URL |

Google OAuth: `credentials.json` and `token.json` must be present in the project root.

## Steps

### Step 1 — Resolve the brief

**If `--url` input:**
```bash
cd tools
python scrape_url.py --url "<url>"
```
Extract the `body` field from the JSON output. Use it as `<brief>`.

**If `--file` input:**
```bash
cd tools
python parse_doc.py --file "<path>"
```
Extract the `text` field from the JSON output. Use it as `<brief>`.

**If `--brief` input:**
Use the text directly as `<brief>`. No tool needed.

---

### Step 2 — Generate platform content
```bash
cd tools
python generate_content.py --brief "<brief>"
```
Returns JSON with keys: `linkedin`, `twitter`, `instagram`, `blog`, `image_prompt`.
Save to a variable / pipe to next step.

---

### Step 3 — Generate image
```bash
cd tools
python generate_image.py --prompt "<image_prompt from Step 2>"
```
Returns `{ "image_url": "..." }`. If Nano Banana keys are not set, returns an empty URL with a warning — continue without blocking.

---

### Step 4 — Push to Google Sheets
```bash
cd tools
echo '<content JSON from Step 2>' | python push_to_sheets.py --source "<url|topic|filename>" --image-url "<image_url from Step 3>"
```
Returns `{ "rows_written": 4 }` on success (4 rows: LinkedIn, Twitter, Instagram, Blog).

---

### Step 5 — Confirm
Report to user:
- Number of rows written
- Link: `https://docs.google.com/spreadsheets/d/<SHEET_ID>`

## Expected Outputs
- 4 new rows in Google Sheet (one per platform)
- Columns: Date, Platform, Post Copy, Hashtags, Image URL, Input Source, Status
- Status defaults to `Draft`

## Edge Cases

| Situation | Handling |
|---|---|
| URL returns 403/blocked | Inform user, ask for manual paste of article text |
| Claude returns malformed JSON | Retry once; if still broken, log raw response and ask user to review |
| Nano Banana API unavailable | `generate_image.py` returns empty URL gracefully — rows still get written |
| Google OAuth not set up | Run `push_to_sheets.py` once manually; browser will prompt for Google login |
| Brief too long (>8000 chars) | Tools truncate at 8000 chars automatically |
| Sheet ID missing | `push_to_sheets.py` raises `EnvironmentError` — add `SHEET_ID` to `.env` |

## Notes
- Claude model: `claude-sonnet-4-6` — fast and high quality for structured output tasks
- All content is tagged `Draft` so the user can review before publishing
- `.tmp/` stores scraped HTML cache files (`scrape_<hash>.json`) — safe to delete anytime
- If rate-limited by Claude API, wait 60 seconds and retry
- Google OAuth token (`token.json`) is auto-refreshed; only needs manual login once

"""
One-time setup: OAuth login, create 'viact.ai Content Calendar' Google Sheet,
write the Sheet ID back into .env automatically.
"""
import os
import re

from dotenv import load_dotenv
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
TOKEN_PATH = os.path.join(BASE_DIR, "token.json")
ENV_PATH = os.path.join(BASE_DIR, ".env")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

COLUMNS = ["Date", "Platform", "Post Copy", "Hashtags", "Image URL", "Input Source", "Status"]


def get_creds():
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
    return creds


def create_sheet(service) -> str:
    body = {
        "properties": {"title": "viact.ai Content Calendar"},
        "sheets": [{"properties": {"title": "Sheet1"}}],
    }
    spreadsheet = service.spreadsheets().create(body=body, fields="spreadsheetId").execute()
    return spreadsheet["spreadsheetId"]


def write_header(service, sheet_id: str):
    service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="Sheet1!A1",
        valueInputOption="RAW",
        body={"values": [COLUMNS]},
    ).execute()


def update_env(sheet_id: str):
    with open(ENV_PATH, "r") as f:
        content = f.read()
    content = re.sub(r"^SHEET_ID=.*$", f"SHEET_ID={sheet_id}", content, flags=re.MULTILINE)
    with open(ENV_PATH, "w") as f:
        f.write(content)


def main():
    print("Step 1/4 — Authenticating with Google (browser will open)...")
    creds = get_creds()
    print("         Authenticated.")

    print("Step 2/4 — Creating 'viact.ai Content Calendar' Google Sheet...")
    service = build("sheets", "v4", credentials=creds)
    sheet_id = create_sheet(service)
    print(f"         Created. Sheet ID: {sheet_id}")

    print("Step 3/4 — Writing column headers...")
    write_header(service, sheet_id)
    print("         Headers written.")

    print("Step 4/4 — Saving Sheet ID to .env...")
    update_env(sheet_id)
    print("         .env updated.")

    print()
    print("Setup complete!")
    print(f"Sheet URL: https://docs.google.com/spreadsheets/d/{sheet_id}")


if __name__ == "__main__":
    main()

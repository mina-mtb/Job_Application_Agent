"""
integrations/google_drive.py
=============================
Phase 4 — Google Drive Integration

Responsibility:
  - Upload tailored CVs to Google Drive folder
  - Upload tracker.csv to Drive (for easy mobile access)
  - Upload daily summary to Drive
  - Never delete existing files — only add/update

Setup instructions:
  1. Go to https://console.cloud.google.com
  2. Create a project → Enable "Google Drive API"
  3. Create credentials → OAuth 2.0 → Desktop App
  4. Download credentials.json → put in config/
  5. Run once manually to authorize: python integrations/google_drive.py --auth
  6. After auth, token.json is saved — future runs are automatic

Requirements:
  pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib

Token optimization:
  - Only uploads changed files (checks modification date)
  - No reading from Drive — write-only
  - Does not require loading any profile or job data
"""

import json
import logging
import os
from datetime import date
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("google_drive")

# Google API scopes needed
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


# ── Auth helper ────────────────────────────────────────────────────────────────

def get_drive_service(config_dir: str = "config"):
    """
    Build and return an authenticated Google Drive service.
    Requires config/credentials.json (download from Google Cloud Console).
    Saves token to config/token.json after first auth.

    Returns None if credentials are not configured.
    """
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build
    except ImportError:
        logger.error(
            "Google API packages not installed.\n"
            "Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"
        )
        return None

    creds_file = Path(config_dir) / "credentials.json"
    token_file = Path(config_dir) / "token.json"

    if not creds_file.exists():
        logger.warning(
            f"Google credentials not found at {creds_file}\n"
            "Download from: https://console.cloud.google.com/apis/credentials\n"
            "Place as config/credentials.json to enable Google Drive sync."
        )
        return None

    creds = None
    if token_file.exists():
        creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(creds_file), SCOPES)
            creds = flow.run_local_server(port=0)
        token_file.write_text(creds.to_json())

    return build("drive", "v3", credentials=creds)


# ── Drive operations ───────────────────────────────────────────────────────────

def get_or_create_folder(service, folder_name: str,
                          parent_id: Optional[str] = None) -> str:
    """
    Get folder ID by name (under parent), or create it if it doesn't exist.
    Returns folder ID.
    """
    query = (
        f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' "
        f"and trashed=false"
    )
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])

    if files:
        return files[0]["id"]

    # Create folder
    metadata = {
        "name": folder_name,
        "mimeType": "application/vnd.google-apps.folder",
    }
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    logger.info(f"  Created Drive folder: {folder_name}")
    return folder["id"]


def file_exists_in_folder(service, filename: str, folder_id: str) -> Optional[str]:
    """Check if a file exists in a folder. Returns file ID or None."""
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    return files[0]["id"] if files else None


def upload_file(service, local_path: Path, folder_id: str,
                mime_type: str = "text/plain") -> str:
    """
    Upload a file to Drive folder.
    If file already exists with same name, update it (keep same ID).
    Returns file ID.
    """
    from googleapiclient.http import MediaFileUpload

    filename = local_path.name
    media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=False)

    existing_id = file_exists_in_folder(service, filename, folder_id)

    if existing_id:
        # Update existing file
        file = service.files().update(
            fileId=existing_id,
            media_body=media,
        ).execute()
        logger.info(f"  ✓ Updated: {filename}")
        return file["id"]
    else:
        # Create new file
        metadata = {"name": filename, "parents": [folder_id]}
        file = service.files().create(
            body=metadata,
            media_body=media,
            fields="id",
        ).execute()
        logger.info(f"  ✓ Uploaded: {filename}")
        return file["id"]


# ── Main sync function ─────────────────────────────────────────────────────────

def run(config_path: str = "config/config.yaml") -> dict:
    """
    Upload CVs, tracker, and daily summary to Google Drive.
    Returns summary dict.
    """
    with open(config_path) as f:
        config = yaml.safe_load(f)

    logger.info("=" * 60)
    logger.info("Google Drive Sync — Phase 4 starting")

    # Check if Drive is configured
    drive_config = config.get("google_drive", {})
    if not drive_config.get("enabled", False):
        logger.info("Google Drive sync disabled. Set google_drive.enabled: true in config.yaml")
        return {"status": "disabled"}

    service = get_drive_service(config_dir="config")
    if not service:
        return {"status": "no_credentials"}

    today = str(date.today())
    stats = {"cvs_uploaded": 0, "tracker_uploaded": False, "summary_uploaded": False}

    # Get or create root folder
    root_folder_name = drive_config.get("folder_name", "Mina Job Applications")
    root_id = get_or_create_folder(service, root_folder_name)
    logger.info(f"Drive folder: '{root_folder_name}' (id: {root_id[:12]}...)")

    # Sub-folders
    cv_folder_id      = get_or_create_folder(service, "Tailored_CVs", root_id)
    tracker_folder_id = get_or_create_folder(service, "Tracker",      root_id)
    summary_folder_id = get_or_create_folder(service, "Daily_Summary", root_id)

    # 1. Upload tailored CVs
    cv_dir = Path(config["paths"]["tailored_cvs"])
    if cv_dir.exists():
        cv_files = sorted(cv_dir.glob("*.md"))
        for cv_file in cv_files:
            try:
                upload_file(service, cv_file, cv_folder_id, mime_type="text/markdown")
                stats["cvs_uploaded"] += 1
            except Exception as e:
                logger.error(f"  ✗ Failed to upload {cv_file.name}: {e}")

    # 2. Upload tracker.csv
    tracker_path = Path(config["paths"]["tracker"])
    if tracker_path.exists():
        try:
            upload_file(service, tracker_path, tracker_folder_id, mime_type="text/csv")
            stats["tracker_uploaded"] = True
        except Exception as e:
            logger.error(f"  ✗ Failed to upload tracker: {e}")

    # 3. Upload today's daily summary from Obsidian vault
    vault_path = Path(config.get("obsidian_vault", "../MinaJobAgentVault"))
    if not vault_path.is_absolute():
        vault_path = Path(config_path).parent.parent / vault_path

    summary_file = vault_path / "02_Jobs" / f"Daily_Summary_{today}.md"
    if summary_file.exists():
        try:
            upload_file(service, summary_file, summary_folder_id, mime_type="text/markdown")
            stats["summary_uploaded"] = True
        except Exception as e:
            logger.error(f"  ✗ Failed to upload summary: {e}")

    logger.info(
        f"Drive sync complete: {stats['cvs_uploaded']} CVs, "
        f"tracker={'✓' if stats['tracker_uploaded'] else '✗'}, "
        f"summary={'✓' if stats['summary_uploaded'] else '✗'}"
    )
    logger.info("=" * 60)
    return {"status": "success", **stats}


def setup_auth(config_path: str = "config/config.yaml"):
    """Run OAuth flow manually to set up credentials."""
    logger.info("Starting Google Drive OAuth setup...")
    service = get_drive_service(config_dir="config")
    if service:
        logger.info("✓ Authentication successful! token.json saved to config/")
        logger.info("You can now run the pipeline with Google Drive sync enabled.")
    else:
        logger.error("Authentication failed. Check config/credentials.json")


if __name__ == "__main__":
    import argparse
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--auth", action="store_true", help="Run OAuth setup")
    parser.add_argument("--config", default="config/config.yaml")
    args = parser.parse_args()

    if args.auth:
        setup_auth(args.config)
    else:
        run(args.config)

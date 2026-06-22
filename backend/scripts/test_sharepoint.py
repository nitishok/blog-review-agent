"""
Smoke test for SharePoint integration (Stage 1).

Usage:
    cd backend
    python -m dotenv -f .env run python scripts/test_sharepoint.py

Or with dotenv loaded manually:
    source .env && python scripts/test_sharepoint.py

Tests:
  1. Auth — acquire an MSAL token successfully
  2. List  — list .docx files in the SharePoint Marketing site root
  3. Fetch — download the first .docx found
  4. Upload round-trip — write it back under a test filename, then delete it
"""

import os
import sys

# Load .env from backend directory
from pathlib import Path
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path, override=True)

# Add backend to path so we can import services
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.sharepoint import _get_token, list_folder_docx, fetch_docx, upload_docx, _b64url
import requests


def check(label: str, fn):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print('='*60)
    try:
        result = fn()
        print(f"✅ PASS")
        return result
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return None


def test_auth():
    token = _get_token()
    assert token and len(token) > 20, "Token looks invalid"
    print(f"   Token acquired (length={len(token)})")
    return token


def test_list():
    site_url = os.environ["SHAREPOINT_SITE_URL"]
    # Use the site's root documents library
    folder_url = site_url.rstrip("/") + "/Shared%20Documents"
    print(f"   Listing: {folder_url}")
    files = list_folder_docx(folder_url)
    print(f"   Found {len(files)} .docx file(s)")
    for f in files[:5]:
        print(f"     - {f['name']}")
    return files


def test_fetch(files):
    if not files:
        print("   Skipped — no .docx files found to fetch")
        return None
    target = files[0]
    print(f"   Fetching: {target['name']} ({target['url']})")
    content = fetch_docx(target["url"])
    print(f"   Downloaded {len(content):,} bytes")
    assert len(content) > 100, "File too small — likely an error response"
    return content, target


def test_upload_roundtrip(content_and_target):
    if not content_and_target:
        print("   Skipped — no content from fetch step")
        return
    content, target = content_and_target

    # Upload to a test copy
    original_url = target["url"]
    test_url = original_url.rsplit("/", 1)[0] + "/_smoke_test_roundtrip.docx"
    print(f"   Uploading test copy to: {test_url}")
    upload_docx(test_url, content)
    print(f"   Upload succeeded")

    # Verify we can fetch it back
    fetched = fetch_docx(test_url)
    assert fetched == content, "Round-trip content mismatch!"
    print(f"   Round-trip verified ({len(fetched):,} bytes match)")

    # Clean up: delete the test file via Graph API
    token = _get_token()
    headers = {"Authorization": f"Bearer {token}"}
    delete_url = f"https://graph.microsoft.com/v1.0/shares/u!{_b64url(test_url)}/driveItem"
    resp = requests.delete(delete_url, headers=headers)
    if resp.status_code in (204, 200):
        print(f"   Test file deleted ✅")
    else:
        print(f"   Warning: could not delete test file (status={resp.status_code}) — delete manually")


if __name__ == "__main__":
    print("\nBlogReviewAgent — SharePoint Smoke Test")

    token = check("1. Auth (MSAL token acquisition)", test_auth)
    files = check("2. List .docx files in SharePoint", test_list)
    content_and_target = check("3. Fetch first .docx", lambda: test_fetch(files))
    check("4. Upload round-trip", lambda: test_upload_roundtrip(content_and_target))

    print(f"\n{'='*60}")
    print("Done.")

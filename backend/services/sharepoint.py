import io
import os

import msal
import requests


def _get_token() -> str:
    authority = f"https://login.microsoftonline.com/{os.environ['AZURE_TENANT_ID']}"
    app = msal.ConfidentialClientApplication(
        os.environ["AZURE_CLIENT_ID"],
        authority=authority,
        client_credential=os.environ["AZURE_CLIENT_SECRET"],
    )
    result = app.acquire_token_for_client(
        scopes=["https://graph.microsoft.com/.default"]
    )
    if "access_token" not in result:
        raise RuntimeError(f"MSAL token error: {result.get('error_description')}")
    return result["access_token"]


def _headers() -> dict:
    return {"Authorization": f"Bearer {_get_token()}"}


def fetch_docx(sharepoint_url: str) -> bytes:
    """Download a .docx file from a SharePoint URL via Microsoft Graph."""
    # Convert SharePoint URL to Graph API drive item URL
    encoded = requests.utils.quote(sharepoint_url, safe="")
    graph_url = f"https://graph.microsoft.com/v1.0/shares/u!{_b64url(sharepoint_url)}/driveItem/content"
    response = requests.get(graph_url, headers=_headers())
    response.raise_for_status()
    return response.content


def upload_docx(sharepoint_url: str, content: bytes) -> None:
    """Upload updated .docx back to the same SharePoint location."""
    graph_url = f"https://graph.microsoft.com/v1.0/shares/u!{_b64url(sharepoint_url)}/driveItem/content"
    headers = _headers()
    headers["Content-Type"] = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    response = requests.put(graph_url, headers=headers, data=content)
    response.raise_for_status()


def list_folder_docx(folder_url: str) -> list[dict]:
    """List all .docx files in a SharePoint folder (for training data ingestion)."""
    graph_url = f"https://graph.microsoft.com/v1.0/shares/u!{_b64url(folder_url)}/driveItem/children"
    response = requests.get(graph_url, headers=_headers())
    response.raise_for_status()
    items = response.json().get("value", [])
    return [
        {"name": item["name"], "url": item["webUrl"]}
        for item in items
        if item["name"].endswith(".docx")
    ]


def _b64url(url: str) -> str:
    import base64
    encoded = base64.urlsafe_b64encode(url.encode()).rstrip(b"=").decode()
    return encoded

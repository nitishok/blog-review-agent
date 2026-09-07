"""
local_blogs.py — Local-file mode for testing without JIRA/SharePoint.

Set LOCAL_BLOGS_MODE=1 in backend/.env to activate.
Reads .docx files from the blogs/ folder at the repo root.
All JIRA/SharePoint code remains untouched.
"""

import os
import re
from pathlib import Path

BLOGS_DIR = Path(__file__).parent.parent.parent / "blogs"


def is_local_mode() -> bool:
    return os.environ.get("LOCAL_BLOGS_MODE", "").strip() == "1"


def _slug(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", name).strip("-").upper()


def get_local_queue() -> list[dict]:
    tickets = []
    for i, path in enumerate(sorted(BLOGS_DIR.glob("*.docx")), start=1):
        ticket_id = f"LOCAL-{i:03d}"
        tickets.append({
            "id": ticket_id,
            "summary": f"[New Blog] - {path.stem}",
            "status": "LOCAL",
            "assignee": None,
            "reporter": None,
            "updated": "",
            "description": str(path),
            "review_ready": False,
            "_local_path": str(path),
        })
    return tickets


def get_local_docx(ticket_id: str) -> bytes:
    """Return the raw .docx bytes for a local ticket."""
    for i, path in enumerate(sorted(BLOGS_DIR.glob("*.docx")), start=1):
        if f"LOCAL-{i:03d}" == ticket_id:
            return path.read_bytes()
    raise FileNotFoundError(f"No local blog found for {ticket_id}")


def save_local_docx(ticket_id: str, content: bytes) -> None:
    """Write redlined bytes back alongside the original as <name>_redlined.docx."""
    for i, path in enumerate(sorted(BLOGS_DIR.glob("*.docx")), start=1):
        if f"LOCAL-{i:03d}" == ticket_id:
            out = path.parent / f"{path.stem}_redlined.docx"
            out.write_bytes(content)
            return
    raise FileNotFoundError(f"No local blog found for {ticket_id}")

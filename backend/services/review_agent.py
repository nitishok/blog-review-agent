import asyncio
import os
from pathlib import Path

import anthropic

from services.docx_service import extract_text
from services.jira import get_review_queue, get_sharepoint_url
from services.sharepoint import fetch_docx

# In-memory cache: ticket_id -> review result
_review_cache: dict[str, dict] = {}

STYLE_FILE = Path(__file__).parent.parent.parent / "review-style.md"


def _load_style() -> str:
    if STYLE_FILE.exists():
        return STYLE_FILE.read_text(encoding="utf-8")
    return ""


def generate_review(doc_text: str, ticket_context: dict) -> list[dict]:
    """
    Call Claude to generate redline suggestions for a document.

    Returns list of:
    {
        "original_text": str,
        "suggestion": str,
        "rationale": str,
    }
    """
    style = _load_style()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    system_prompt = f"""You are the CEO of an Appian-focused IT services company reviewing marketing content.
Your job is to redline this content based on your established review style.

## Your Review Style
{style}

## Instructions
Analyze the document and return a JSON array of suggested changes. Each change must be:
{{
  "original_text": "exact phrase or sentence from the document",
  "suggestion": "your improved version",
  "rationale": "one sentence explaining why"
}}

Only flag changes that meaningfully improve the content. Be selective — 3 to 8 changes per document.
Return ONLY the JSON array, no other text."""

    user_prompt = f"""Content type: {ticket_context.get('content_type', 'marketing content')}
Target audience: {ticket_context.get('audience', 'business executives')}
Campaign: {ticket_context.get('campaign', 'N/A')}

---

{doc_text}"""

    message = client.messages.create(
        model=model,
        max_tokens=2048,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt,
    )

    import json
    raw = message.content[0].text.strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw.strip())


async def pregenerate_queue():
    """Eagerly pre-generate reviews for all tickets in the CEO Review queue."""
    try:
        tickets = get_review_queue()
        for ticket in tickets:
            ticket_id = ticket["id"]
            if ticket_id not in _review_cache:
                await _pregenerate_ticket(ticket_id, ticket)
    except Exception as e:
        print(f"[pregenerate] Error: {e}")


async def _pregenerate_ticket(ticket_id: str, ticket: dict):
    try:
        sharepoint_url = get_sharepoint_url(ticket_id)
        if not sharepoint_url:
            _review_cache[ticket_id] = {"error": "No SharePoint URL found in ticket"}
            return
        docx_bytes = fetch_docx(sharepoint_url)
        doc_text = extract_text(docx_bytes)
        suggestions = await asyncio.to_thread(generate_review, doc_text, ticket)
        _review_cache[ticket_id] = {
            "ticket": ticket,
            "original_text": doc_text,
            "suggestions": suggestions,
            "sharepoint_url": sharepoint_url,
            "docx_bytes": docx_bytes,
        }
    except Exception as e:
        _review_cache[ticket_id] = {"error": str(e)}


def get_cached_review(ticket_id: str) -> dict | None:
    return _review_cache.get(ticket_id)


def invalidate_cache(ticket_id: str):
    _review_cache.pop(ticket_id, None)

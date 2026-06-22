"""
review_agent.py — Generate redline suggestions using Claude.

Uses prompt caching on the system prompt (style guide) so repeated calls
for different tickets in the same queue pass are fast and cheap.
"""

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Optional

import anthropic

from services.docx_service import extract_text
from services.jira import get_review_queue, get_sharepoint_url
from services.sharepoint import fetch_docx

# In-memory cache: ticket_id -> review result
_review_cache: dict = {}

STYLE_FILE = Path(__file__).parent.parent.parent / "review-style.md"


def _load_style() -> str:
    if STYLE_FILE.exists():
        return STYLE_FILE.read_text(encoding="utf-8")
    return "(No style guide found — apply general editorial judgment.)"


def _infer_content_type(ticket_summary: str) -> str:
    """Extract content type from ticket summary prefix e.g. [Blog], [Email]."""
    match = re.match(r'\[([^\]]+)\]', ticket_summary or "")
    return match.group(1) if match else "marketing content"


def generate_review(doc_text: str, ticket_context: dict) -> list:
    """
    Call Claude to generate redline suggestions for a document.

    Uses prompt caching on the system prompt block (style guide) so the
    cache block is reused across all tickets reviewed in the same session.

    Returns list of:
        {
            "original_text": str,   # exact phrase from the document
            "suggestion":    str,   # improved version
            "rationale":     str,   # one sentence explaining why
        }
    """
    style = _load_style()
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    model = os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6")

    content_type = _infer_content_type(ticket_context.get("summary", ""))

    system_prompt_text = f"""You are the CEO of Princeton Blue, an Appian-focused IT services company, \
reviewing marketing content before publication.

Your job is to redline this content so it sounds like you wrote it — not the marketing team.
Apply your review style ruthlessly but selectively (3–8 changes per document).

## Your Review Style
{style}

## Output Format
Return ONLY a JSON array. No prose, no markdown fences. Each element:
{{
  "original_text": "exact phrase or sentence copied verbatim from the document",
  "suggestion": "your improved version of that phrase",
  "rationale": "one sentence — why this change makes it stronger"
}}

If the document is strong and needs fewer than 3 changes, return fewer. \
Never invent changes just to meet a quota."""

    user_prompt = f"""Content type: {content_type}
Ticket: {ticket_context.get('id', 'N/A')} — {ticket_context.get('summary', '')}

---

{doc_text}"""

    message = client.messages.create(
        model=model,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": system_prompt_text,
                # Cache the style guide — same across all tickets in a session
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": user_prompt}],
    )

    # Log cache performance
    usage = message.usage
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_write = getattr(usage, "cache_creation_input_tokens", 0)
    print(
        f"[review_agent] tokens — input: {usage.input_tokens}, "
        f"output: {usage.output_tokens}, "
        f"cache_write: {cache_write}, cache_read: {cache_read}"
    )

    raw = message.content[0].text.strip()
    # Strip markdown code fences if model adds them despite instructions
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    return json.loads(raw.strip())


async def pregenerate_queue():
    """Eagerly pre-generate reviews for all tickets in the review queue."""
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


def get_cached_review(ticket_id: str) -> Optional[dict]:
    return _review_cache.get(ticket_id)


def invalidate_cache(ticket_id: str):
    _review_cache.pop(ticket_id, None)

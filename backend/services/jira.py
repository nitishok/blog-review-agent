import os
import requests as _requests
from typing import Optional
from jira import JIRA

_client: Optional[JIRA] = None


def get_client() -> JIRA:
    global _client
    if _client is None:
        _client = JIRA(
            server=os.environ["JIRA_URL"],
            basic_auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
        )
    return _client


def _v3_search(jql: str, max_results: int = 50) -> list[dict]:
    """Call the Jira Cloud v3 search/jql endpoint directly (v2 was removed 2026)."""
    base = os.environ["JIRA_URL"].rstrip("/")
    url = f"{base}/rest/api/3/search/jql"
    auth = (os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"])
    params = {
        "jql": jql,
        "maxResults": max_results,
        "fields": "summary,status,assignee,reporter,updated,description",
        "expand": "changelog",
    }
    resp = _requests.get(url, params=params, auth=auth)
    resp.raise_for_status()
    return resp.json().get("issues", [])


def _serialize_v3(issue: dict) -> dict:
    fields = issue.get("fields", {})
    assignee = fields.get("assignee") or {}
    reporter = fields.get("reporter") or {}

    # Flatten description: v3 returns Atlassian Document Format (ADF), extract plain text
    description_raw = fields.get("description") or ""
    if isinstance(description_raw, dict):
        description_raw = _adf_to_text(description_raw)

    return {
        "id": issue["key"],
        "summary": fields.get("summary", ""),
        "status": (fields.get("status") or {}).get("name", ""),
        "assignee": assignee.get("emailAddress"),
        "reporter": reporter.get("emailAddress"),
        "updated": fields.get("updated", ""),
        "description": description_raw,
    }


def _adf_to_text(adf: dict) -> str:
    """Recursively extract plain text from an Atlassian Document Format node."""
    if not isinstance(adf, dict):
        return ""
    if adf.get("type") == "text":
        return adf.get("text", "")
    parts = []
    for child in adf.get("content", []):
        parts.append(_adf_to_text(child))
    return " ".join(p for p in parts if p)


def get_review_queue() -> list[dict]:
    """Return all tickets currently in Pramod's review status."""
    status = os.environ.get("JIRA_REVIEW_STATUS", "PRAMOD")
    project = os.environ.get("JIRA_PROJECT", "MA2")
    jql = f'project = "{project}" AND status = "{status}" ORDER BY updated DESC'
    issues = _v3_search(jql, max_results=50)
    return [_serialize_v3(issue) for issue in issues]


def get_ticket(ticket_id: str) -> dict:
    issue = get_client().issue(ticket_id, expand="changelog")
    return _serialize(issue)


def get_sharepoint_url(ticket_id: str) -> Optional[str]:
    """Extract SharePoint doc URL from ticket description (ADF format)."""
    base = os.environ["JIRA_URL"].rstrip("/")
    auth = (_requests.auth.HTTPBasicAuth if hasattr(_requests.auth, "HTTPBasicAuth") else None)
    resp = _requests.get(
        f"{base}/rest/api/3/issue/{ticket_id}",
        params={"fields": "description"},
        auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
    )
    resp.raise_for_status()
    description = resp.json().get("fields", {}).get("description") or {}
    return _extract_sharepoint_url(description)


def _extract_sharepoint_url(node: dict) -> Optional[str]:
    """
    Recursively walk an ADF document tree and return the first SharePoint URL found.

    Handles two common patterns Jira uses:
      - inlineCard:  {"type": "inlineCard", "attrs": {"url": "https://...sharepoint..."}}
      - link mark:   {"type": "text", "marks": [{"type": "link", "attrs": {"href": "https://...sharepoint..."}}]}
    """
    if not isinstance(node, dict):
        return None

    # inlineCard
    if node.get("type") == "inlineCard":
        url = (node.get("attrs") or {}).get("url", "")
        if "sharepoint.com" in url:
            return url

    # link mark on a text node
    for mark in node.get("marks", []):
        if mark.get("type") == "link":
            href = (mark.get("attrs") or {}).get("href", "")
            if "sharepoint.com" in href:
                return href

    # recurse into children
    for child in node.get("content", []):
        result = _extract_sharepoint_url(child)
        if result:
            return result

    return None


def get_previous_assignee(ticket_id: str) -> Optional[str]:
    """Find who was assigned before the CEO by scanning changelog."""
    issue = get_client().issue(ticket_id, expand="changelog")
    ceo_email = os.environ.get("JIRA_EMAIL", "")
    previous = None
    for history in issue.changelog.histories:
        for item in history.items:
            if item.field == "assignee":
                if item.toString and ceo_email.lower() in (item.toString or "").lower():
                    previous = item.fromString
                elif item.toString and previous is None:
                    previous = item.toString
    return previous


def get_previous_status(ticket_id: str) -> Optional[str]:
    """Find the status the ticket was in before CEO Review."""
    issue = get_client().issue(ticket_id, expand="changelog")
    review_status = os.environ.get("JIRA_REVIEW_STATUS", "CEO Review")
    for history in reversed(issue.changelog.histories):
        for item in history.items:
            if item.field == "status" and item.toString == review_status:
                return item.fromString
    return None


def transition_ticket(ticket_id: str, target_status: str, assignee_email: Optional[str]):
    client = get_client()
    transitions = client.transitions(ticket_id)
    transition_id = next(
        (t["id"] for t in transitions if t["name"].lower() == target_status.lower()),
        None,
    )
    if transition_id:
        client.transition_issue(ticket_id, transition_id)
    if assignee_email:
        client.assign_issue(ticket_id, assignee_email)


def _serialize(issue) -> dict:
    return {
        "id": issue.key,
        "summary": issue.fields.summary,
        "status": issue.fields.status.name,
        "assignee": getattr(issue.fields.assignee, "emailAddress", None),
        "reporter": getattr(issue.fields.reporter, "emailAddress", None),
        "updated": str(issue.fields.updated),
        "description": issue.fields.description or "",
    }

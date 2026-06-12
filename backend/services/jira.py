import os
from jira import JIRA

_client: JIRA | None = None


def get_client() -> JIRA:
    global _client
    if _client is None:
        _client = JIRA(
            server=os.environ["JIRA_URL"],
            basic_auth=(os.environ["JIRA_EMAIL"], os.environ["JIRA_API_TOKEN"]),
        )
    return _client


def get_review_queue() -> list[dict]:
    """Return all tickets currently in CEO Review status."""
    status = os.environ.get("JIRA_REVIEW_STATUS", "CEO Review")
    jql = f'status = "{status}" ORDER BY updated DESC'
    issues = get_client().search_issues(jql, maxResults=50, expand="changelog")
    return [_serialize(issue) for issue in issues]


def get_ticket(ticket_id: str) -> dict:
    issue = get_client().issue(ticket_id, expand="changelog")
    return _serialize(issue)


def get_sharepoint_url(ticket_id: str) -> str | None:
    """Extract SharePoint doc URL from ticket description or custom field."""
    issue = get_client().issue(ticket_id)
    description = issue.fields.description or ""
    # Look for SharePoint URLs in description
    import re
    match = re.search(r'https://[^\s]+\.sharepoint\.com[^\s]*', description)
    return match.group(0) if match else None


def get_previous_assignee(ticket_id: str) -> str | None:
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


def get_previous_status(ticket_id: str) -> str | None:
    """Find the status the ticket was in before CEO Review."""
    issue = get_client().issue(ticket_id, expand="changelog")
    review_status = os.environ.get("JIRA_REVIEW_STATUS", "CEO Review")
    for history in reversed(issue.changelog.histories):
        for item in history.items:
            if item.field == "status" and item.toString == review_status:
                return item.fromString
    return None


def transition_ticket(ticket_id: str, target_status: str, assignee_email: str | None):
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

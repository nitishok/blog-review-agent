"""
Smoke test for JIRA integration (Stage 1).

Usage:
    cd /path/to/blog-review-agent
    python3 backend/scripts/test_jira.py

Tests:
  1. Auth     — connect to JIRA and fetch current user info
  2. Queue    — list tickets in "CEO Review" status
  3. Ticket   — fetch a single ticket with changelog
  4. History  — extract previous status + assignee from changelog
  5. SharePoint URL — parse SharePoint link from ticket description
  6. Transitions — list available transitions for a ticket (dry run, no change)
"""

import os
import sys
from pathlib import Path

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(env_path, override=True)

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.services.jira import (
    get_client,
    get_review_queue,
    get_ticket,
    get_sharepoint_url,
    get_previous_assignee,
    get_previous_status,
)


def check(label: str, fn):
    print(f"\n{'='*60}")
    print(f"TEST: {label}")
    print("=" * 60)
    try:
        result = fn()
        print("✅ PASS")
        return result
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return None


def test_auth():
    client = get_client()
    me = client.myself()
    print(f"   Connected as: {me['displayName']} <{me['emailAddress']}>")
    print(f"   JIRA URL: {os.environ['JIRA_URL']}")
    return client


def test_queue():
    tickets = get_review_queue()
    status = os.environ.get("JIRA_REVIEW_STATUS", "CEO Review")
    print(f"   Status filter: \"{status}\"")
    print(f"   Tickets found: {len(tickets)}")
    for t in tickets:
        print(f"     [{t['id']}] {t['summary'][:70]}  (assignee={t['assignee']})")
    return tickets


def test_ticket(tickets):
    if not tickets:
        print("   Skipped — no tickets in queue")
        return None
    ticket_id = tickets[0]["id"]
    t = get_ticket(ticket_id)
    print(f"   Fetched: [{t['id']}] {t['summary']}")
    print(f"   Status:  {t['status']}")
    print(f"   Updated: {t['updated']}")
    return ticket_id


def test_history(ticket_id):
    if not ticket_id:
        print("   Skipped")
        return
    prev_status = get_previous_status(ticket_id)
    prev_assignee = get_previous_assignee(ticket_id)
    print(f"   Previous status:   {prev_status or '(not found in changelog)'}")
    print(f"   Previous assignee: {prev_assignee or '(not found in changelog)'}")


def test_sharepoint_url(ticket_id):
    # Always test against MA2-587 which we know has an inlineCard SharePoint URL
    for tid in filter(None, [ticket_id, "MA2-587"]):
        url = get_sharepoint_url(tid)
        if url:
            print(f"   [{tid}] SharePoint URL: {url[:100]}...")
            return url
    print("   No SharePoint URL found in any tested ticket")
    return None


def test_transitions(ticket_id):
    if not ticket_id:
        print("   Skipped")
        return
    client = get_client()
    transitions = client.transitions(ticket_id)
    print(f"   Available transitions for {ticket_id}:")
    for t in transitions:
        print(f"     [{t['id']}] {t['name']}")


if __name__ == "__main__":
    print("\nBlogReviewAgent — JIRA Smoke Test")

    check("1. Auth (connect + whoami)", test_auth)
    tickets = check("2. Queue (CEO Review tickets)", test_queue)
    ticket_id = check("3. Fetch single ticket", lambda: test_ticket(tickets))
    check("4. Changelog — previous status + assignee", lambda: test_history(ticket_id))
    check("5. SharePoint URL from description", lambda: test_sharepoint_url(ticket_id))
    check("6. Available transitions (dry run)", lambda: test_transitions(ticket_id))

    print(f"\n{'='*60}")
    print("Done.")

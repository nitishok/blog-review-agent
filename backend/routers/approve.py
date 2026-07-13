from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services.docx_service import write_comments
from services.jira import get_previous_assignee, get_previous_status, transition_ticket
from services.review_agent import get_cached_review, invalidate_cache
from services.sharepoint import upload_docx
from services.style_learner import learn_from_approval

router = APIRouter()


class ApproveRequest(BaseModel):
    ticket_id: str
    final_suggestions: list[dict]


@router.post("/approve")
async def approve(req: ApproveRequest):
    """
    Step 1: Write accepted suggestions as Word comments and upload to SharePoint.
    Does NOT transition the JIRA ticket — call /send-to-author when ready.
    """
    cached = get_cached_review(req.ticket_id)
    if not cached:
        raise HTTPException(status_code=404, detail="No cached review found")

    # Write suggestions as Word comments into the doc
    updated_docx = write_comments(cached["docx_bytes"], req.final_suggestions)

    # Upload redlined doc back to SharePoint
    upload_docx(cached["sharepoint_url"], updated_docx)

    # Learn from differences between agent suggestions and final edits
    learn_from_approval(cached["suggestions"], req.final_suggestions)

    # Store final suggestions in cache so send-to-author can access them
    cached["final_suggestions"] = req.final_suggestions
    cached["redline_uploaded"] = True

    return {"status": "redline_uploaded", "ticket_id": req.ticket_id}


@router.post("/send-to-author/{ticket_id}")
async def send_to_author(ticket_id: str):
    """
    Step 2: Transition JIRA ticket back to the original author.
    Call this only after reviewing the redlined Word doc in SharePoint.
    """
    cached = get_cached_review(ticket_id)
    if not cached:
        raise HTTPException(status_code=404, detail="No cached review found")
    if not cached.get("redline_uploaded"):
        raise HTTPException(status_code=400, detail="Redline not yet uploaded — call /approve first")

    previous_status = get_previous_status(ticket_id)
    previous_assignee = get_previous_assignee(ticket_id)

    if previous_status:
        transition_ticket(ticket_id, previous_status, previous_assignee)

    invalidate_cache(ticket_id)

    return {"status": "sent_to_author", "ticket_id": ticket_id}

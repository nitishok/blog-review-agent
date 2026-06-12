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
    final_suggestions: list[dict]  # CEO's (possibly edited) suggestions


@router.post("/approve")
async def approve(req: ApproveRequest):
    cached = get_cached_review(req.ticket_id)
    if not cached:
        raise HTTPException(status_code=404, detail="No cached review found")

    # Write CEO's final suggestions as Word comments into the doc
    updated_docx = write_comments(cached["docx_bytes"], req.final_suggestions)

    # Upload back to SharePoint
    upload_docx(cached["sharepoint_url"], updated_docx)

    # Get previous state before transitioning
    previous_status = get_previous_status(req.ticket_id)
    previous_assignee = get_previous_assignee(req.ticket_id)

    # Revert JIRA ticket status and reassign
    if previous_status:
        transition_ticket(req.ticket_id, previous_status, previous_assignee)

    # Learn from any differences between agent suggestions and CEO final edits
    learn_from_approval(cached["suggestions"], req.final_suggestions)

    invalidate_cache(req.ticket_id)

    return {"status": "approved", "ticket_id": req.ticket_id}

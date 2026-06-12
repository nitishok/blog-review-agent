from fastapi import APIRouter, HTTPException

from services.review_agent import get_cached_review

router = APIRouter()


@router.get("/review/{ticket_id}")
async def get_review(ticket_id: str):
    cached = get_cached_review(ticket_id)
    if cached is None:
        raise HTTPException(status_code=404, detail="Review not ready yet")
    if "error" in cached:
        raise HTTPException(status_code=500, detail=cached["error"])
    return {
        "ticket_id": ticket_id,
        "ticket": cached["ticket"],
        "original_text": cached["original_text"],
        "suggestions": cached["suggestions"],
        "sharepoint_url": cached["sharepoint_url"],
    }

import asyncio

from fastapi import APIRouter

from services.jira import get_review_queue
from services.review_agent import get_cached_review, pregenerate_queue

router = APIRouter()


@router.get("/queue")
async def queue():
    tickets = get_review_queue()
    # Trigger pre-generation for any ticket not yet cached
    asyncio.create_task(pregenerate_queue())
    return [
        {
            **ticket,
            "review_ready": get_cached_review(ticket["id"]) is not None,
        }
        for ticket in tickets
    ]

import asyncio

from fastapi import APIRouter

from services.jira import get_review_queue
from services.local_blogs import is_local_mode, get_local_queue
from services.review_agent import get_cached_review, pregenerate_queue

router = APIRouter()


@router.get("/queue")
async def queue():
    tickets = get_local_queue() if is_local_mode() else get_review_queue()
    # Trigger pre-generation for any ticket not yet cached
    asyncio.create_task(pregenerate_queue())
    return [
        {
            **{k: v for k, v in ticket.items() if k != "_local_path"},
            "review_ready": get_cached_review(ticket["id"]) is not None,
        }
        for ticket in tickets
    ]

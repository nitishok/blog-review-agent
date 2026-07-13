import asyncio
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

from routers import approve, queue, review
from services.review_agent import pregenerate_queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(pregenerate_queue())
    yield


app = FastAPI(title="BlogReviewAgent", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(queue.router)
app.include_router(review.router)
app.include_router(approve.router)

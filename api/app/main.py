from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.db import Base, engine
from app.routers import donations, paypal_config


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Good enough until we add migrations; creates missing tables only.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Community Giving API", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(donations.router)
app.include_router(paypal_config.router)


@app.get("/health")
def health() -> dict:
    return {"ok": True}

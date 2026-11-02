from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute

from app.config import get_settings
from app.db import Base, engine
from app.routers import admin, catalogue, donations, donors, internal, paypal_config, rounds, webhooks
from app.stubs import Planned, planned_handler

DESCRIPTION = """
Core API for the Community Giving Platform. Owns all money logic; the only service with PayPal credentials.

* Money is integer minor units in fields ending in `_cents`, with a currency code (USD).
* Errors are `{"detail": {"error": CODE, "message": text}}`.
* Routes not built yet return their example response with an `X-Stub` header (or **501 NOT_IMPLEMENTED** when `STUB_EXAMPLES=false`). Don't treat their data as real.
* `/admin/*` needs `Authorization: Bearer <ADMIN_TOKEN>`; `/internal/*` (agents) needs `Bearer <INTERNAL_TOKEN>`.
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Good enough until we add migrations; creates missing tables only.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(
    title="Community Giving API",
    version="0.2.0",
    description=DESCRIPTION,
    lifespan=lifespan,
    # Operation ids are the function names, so generated clients get readable method names.
    generate_unique_id_function=lambda route: route.name,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in get_settings().cors_origins.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Stub"],
)
for module in (catalogue, donations, donors, rounds, admin, internal, webhooks, paypal_config):
    app.include_router(module.router)
app.add_exception_handler(Planned, planned_handler)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def _check_unique_operation_ids() -> None:
    names = [r.name for r in app.routes if isinstance(r, APIRoute) and r.include_in_schema]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"Duplicate route function names: {dupes}"


_check_unique_operation_ids()

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.routing import APIRoute

from app import projections
from app.config import get_settings
from app.db import create_schema, engine
from app.openapi_docs import document
from app.routers import admin, agent_public, catalogue, donations, donors, internal, paypal_config, rounds, webhooks
from app.stubs import Planned, planned_handler

DESCRIPTION = """
Core API for the Community Giving Platform. Owns all money logic; the only service with PayPal credentials.

* Money is integer minor units in fields ending in `_cents`, with a currency code (USD).
* Errors are `{"detail": {"error": CODE, "message": text}}`.
* Routes not built yet return their example response with an `X-Stub` header (or **501 NOT_IMPLEMENTED** when `STUB_EXAMPLES=false`). Don't treat their data as real.
* Authorization: admin routes (paths under /admin/) take the admin console's bearer token, ADMIN_TOKEN; agent routes (under /internal/) take the agent service's bearer token, INTERNAL_TOKEN. Both go in the Authorization header (see the HTTPBearer security scheme).
"""


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Creates missing tables and new nullable columns (see create_schema).
    create_schema(engine)
    settings = app.dependency_overrides.get(get_settings, get_settings)()
    stop = projections.start(settings.projection_interval_seconds) if settings.projection_interval_seconds else None
    yield
    if stop:
        stop.set()


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
for module in (catalogue, donations, donors, rounds, admin, internal, webhooks, paypal_config, agent_public):
    app.include_router(module.router)


def _openapi() -> dict:
    """FastAPI's spec plus the descriptions and examples in app/openapi_docs.py."""
    if app.openapi_schema is None:
        app.openapi_schema = document(
            get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
        )
    return app.openapi_schema


app.openapi = _openapi
app.add_exception_handler(Planned, planned_handler)


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"ok": True}


def _check_unique_operation_ids() -> None:
    names = [r.name for r in app.routes if isinstance(r, APIRoute) and r.include_in_schema]
    dupes = {n for n in names if names.count(n) > 1}
    assert not dupes, f"Duplicate route function names: {dupes}"


_check_unique_operation_ids()

"""Helpers for routes that are in the spec but not built yet.

With STUB_EXAMPLES on (the default), a planned route answers with its response model's example
and an `X-Stub` header, so the API doubles as the mock P2 and P3 build against. Off, it answers 501.
"""

from typing import NoReturn, get_args, get_origin

from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.schemas import ErrorOut

PLANNED = {501: {"model": ErrorOut, "description": "In the spec, not built yet"}}


class Planned(Exception):
    def __init__(self, task: str):
        self.task = task


def planned(task: str) -> NoReturn:
    raise Planned(task)


def _example(model) -> object | None:
    if get_origin(model) is list:
        item = _example(get_args(model)[0])
        return None if item is None else [item]
    extra = getattr(model, "model_config", {}).get("json_schema_extra") or {}
    return extra.get("example")


async def planned_handler(request: Request, exc: Planned) -> JSONResponse:
    settings = request.app.dependency_overrides.get(get_settings, get_settings)()
    route = request.scope.get("route")
    example = _example(route.response_model) if route is not None else None
    if settings.stub_examples and example is not None:
        return JSONResponse(example, status_code=route.status_code or 200, headers={"X-Stub": exc.task})
    return JSONResponse(
        {"detail": {"error": "NOT_IMPLEMENTED", "message": f"Planned: {exc.task}"}}, status_code=501
    )

"""Read-only GETs to the core API's public endpoints.

/projects/{id}/funding-history, /projects/{id}/stories and /categories. Nothing here writes,
and the internal token is only sent when the endpoint is under /internal.
"""
from __future__ import annotations

import httpx

from .config import Settings, settings

TIMEOUT = httpx.Timeout(90.0, connect=15.0)

# /categories feeds a draft lookup the web client will abandon after 20 s, so it gets its own
# short budget rather than the 90 s the funding/story reads use.
CATEGORIES_TIMEOUT = httpx.Timeout(3.0, connect=3.0)


class CoreError(RuntimeError):
    pass


class Core:
    def __init__(self, cfg: Settings | None = None, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.cfg = cfg or settings()
        self.base = self.cfg.core_api_url.rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base, timeout=TIMEOUT, transport=transport)

    def _headers(self, path: str) -> dict[str, str]:
        if path.startswith("/internal") and self.cfg.internal_token:
            return {"Authorization": f"Bearer {self.cfg.internal_token}"}
        return {}

    async def get(self, path: str, **params: object) -> object:
        try:
            r = await self._client.get(path, params={k: v for k, v in params.items() if v is not None},
                                       headers=self._headers(path))
            r.raise_for_status()
            return r.json()
        except httpx.HTTPStatusError as exc:
            raise CoreError(f"GET {path} -> {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise CoreError(f"GET {path} unreachable: {exc}") from exc

    async def funding_history(self, project_id: int) -> list[dict]:
        data = await self.get(f"/projects/{project_id}/funding-history")
        return data if isinstance(data, list) else []

    async def stories(self, project_id: int) -> list[dict]:
        data = await self.get(f"/projects/{project_id}/stories")
        return data if isinstance(data, list) else []

    async def categories(self) -> list[dict]:
        """Public GET /categories: [{id, name, project_count}]. Public, so no token is sent.

        Uses a 3 s timeout: a slow catalogue must not use up the draft endpoint's budget.
        """
        try:
            r = await self._client.get("/categories", headers=self._headers("/categories"),
                                       timeout=CATEGORIES_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise CoreError(f"GET /categories -> {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise CoreError(f"GET /categories unreachable: {exc}") from exc
        return [c for c in data if isinstance(c, dict)] if isinstance(data, list) else []

    async def aclose(self) -> None:
        await self._client.aclose()


# Canned catalogue for FAKE_CORE. Ids and names match what that API serves today, so a fake
# draft resolves the same category ids a real one would.
FAKE_CATEGORIES = [
    {"id": 1, "name": "Health", "project_count": 2},
    {"id": 2, "name": "Education", "project_count": 4},
    {"id": 3, "name": "Environment", "project_count": 1},
    {"id": 4, "name": "Water", "project_count": 1},
]


class FakeCore(Core):
    """FAKE_CORE / test double: canned public reads, no network."""

    def __init__(self, funding: dict[int, list[dict]] | None = None,
                 stories: dict[int, list[dict]] | None = None,
                 categories: list[dict] | None = None) -> None:
        self.cfg = settings()
        self.base = "fake"
        self._funding = funding or {}
        self._stories = stories or {}
        self._categories = FAKE_CATEGORIES if categories is None else categories
        self._client = None  # type: ignore[assignment]

    async def funding_history(self, project_id: int) -> list[dict]:
        return self._funding.get(project_id, [])

    async def stories(self, project_id: int) -> list[dict]:
        return self._stories.get(project_id, [])

    async def categories(self) -> list[dict]:
        return [dict(c) for c in self._categories]

    async def aclose(self) -> None:
        return None


def build_core(cfg: Settings | None = None) -> Core:
    cfg = cfg or settings()
    return FakeCore() if cfg.fake_core else Core(cfg)

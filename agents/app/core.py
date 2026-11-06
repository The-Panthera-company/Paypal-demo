"""Read-only GETs to the core API's public endpoints.

Only the endpoints the spec lists: /projects/{id}/funding-history and /projects/{id}/stories.
Nothing here writes, and the internal token is only sent when the endpoint is under /internal.
"""
from __future__ import annotations

import httpx

from .config import Settings, settings

TIMEOUT = httpx.Timeout(90.0, connect=15.0)


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

    async def aclose(self) -> None:
        await self._client.aclose()


class FakeCore(Core):
    """FAKE_CORE / test double: canned public reads, no network."""

    def __init__(self, funding: dict[int, list[dict]] | None = None,
                 stories: dict[int, list[dict]] | None = None) -> None:
        self.cfg = settings()
        self.base = "fake"
        self._funding = funding or {}
        self._stories = stories or {}
        self._client = None  # type: ignore[assignment]

    async def funding_history(self, project_id: int) -> list[dict]:
        return self._funding.get(project_id, [])

    async def stories(self, project_id: int) -> list[dict]:
        return self._stories.get(project_id, [])

    async def aclose(self) -> None:
        return None


def build_core(cfg: Settings | None = None) -> Core:
    cfg = cfg or settings()
    return FakeCore() if cfg.fake_core else Core(cfg)

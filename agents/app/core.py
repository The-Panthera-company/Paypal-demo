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

# /mandates/constraints feeds the same draft, so it gets the same short budget.
CONSTRAINTS_TIMEOUT = httpx.Timeout(3.0, connect=3.0)

# /projects feeds the same draft, and only its tags are used: same short budget.
PROJECTS_TIMEOUT = httpx.Timeout(3.0, connect=3.0)

# The most projects one tag lookup asks for. The draft needs the tag vocabulary, not the
# whole catalogue, and a smaller page keeps the core query cheap.
PROJECTS_LIMIT = 200


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

    async def constraints(self) -> dict:
        """Public GET /mandates/constraints: the limits the API enforces on a mandate.

        Weights are on the API 0-100 scale, not fractions. Uses a 3 s timeout: a slow
        constraints read must not use up the draft endpoint budget.
        """
        try:
            r = await self._client.get("/mandates/constraints",
                                       headers=self._headers("/mandates/constraints"),
                                       timeout=CONSTRAINTS_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise CoreError(f"GET /mandates/constraints -> {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise CoreError(f"GET /mandates/constraints unreachable: {exc}") from exc
        if not isinstance(data, dict):
            raise CoreError("GET /mandates/constraints did not return an object")
        return data

    async def projects(self, limit: int = PROJECTS_LIMIT) -> list[dict]:
        """Public GET /projects?limit=N: the projects, for their tags.

        Only the tag vocabulary is wanted here, so anything that is not a dict is dropped
        rather than trusted. The page can come back bare or wrapped in {"items": [...]} -
        the API has answered both ways, and a wrapper read as a project would silently
        yield no tags at all.
        """
        try:
            r = await self._client.get("/projects", params={"limit": limit},
                                       headers=self._headers("/projects"),
                                       timeout=PROJECTS_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except httpx.HTTPStatusError as exc:
            raise CoreError(f"GET /projects -> {exc.response.status_code}") from exc
        except httpx.HTTPError as exc:
            raise CoreError(f"GET /projects unreachable: {exc}") from exc
        if isinstance(data, dict):
            data = data.get("items")
        if not isinstance(data, list):
            raise CoreError("GET /projects did not return a list")
        return [p for p in data if isinstance(p, dict)]

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

# The tag vocabulary the fake core knows about. Deliberately includes "faith-based": the
# case a donor most needs checked before a tag goes into an exclusion list.
FAKE_PROJECTS = [
    {"id": 1, "title": "Sunday school meals", "tags": ["faith-based", "girls"]},
    {"id": 2, "title": "Well repair", "tags": ["water", "Environment"]},
    {"id": 3, "title": "Girls STEM club", "tags": ["girls", "education"]},
    {"id": 4, "title": "Clean water fund", "tags": ["water"]},
]


# Canned constraints for FAKE_CORE. These are the live API values, on the API 0-100 weight
# scale, so a fake draft enforces exactly what a real one would.
FAKE_CONSTRAINTS = {
    "default_weights": {"few_backers": 35, "progress": 25, "urgency": 20,
                        "evidence": 10, "days_since_funded": 10},
    "max_weight_shift": 20,
    "max_budget_cents": 1000000,
    "max_tags": 20,
    "max_tag_length": 40,
    "min_per_project_cents": 100,
    "max_per_project_cents": 1000000,
    "min_approval_threshold_cents": 100,
    "max_approval_threshold_cents": 1000000,
}


class FakeCore(Core):
    """FAKE_CORE / test double: canned public reads, no network."""

    def __init__(self, funding: dict[int, list[dict]] | None = None,
                 stories: dict[int, list[dict]] | None = None,
                 categories: list[dict] | None = None,
                 constraints: dict | None = None,
                 projects: list[dict] | None = None) -> None:
        self.cfg = settings()
        self.base = "fake"
        self._funding = funding or {}
        self._stories = stories or {}
        self._categories = FAKE_CATEGORIES if categories is None else categories
        self._constraints = FAKE_CONSTRAINTS if constraints is None else constraints
        self._projects = FAKE_PROJECTS if projects is None else projects
        self._client = None  # type: ignore[assignment]

    async def funding_history(self, project_id: int) -> list[dict]:
        return self._funding.get(project_id, [])

    async def stories(self, project_id: int) -> list[dict]:
        return self._stories.get(project_id, [])

    async def categories(self) -> list[dict]:
        return [dict(c) for c in self._categories]

    async def constraints(self) -> dict:
        return dict(self._constraints)

    async def projects(self, limit: int = PROJECTS_LIMIT) -> list[dict]:
        return [dict(p) for p in self._projects[:limit]]

    async def aclose(self) -> None:
        return None


def build_core(cfg: Settings | None = None) -> Core:
    cfg = cfg or settings()
    return FakeCore() if cfg.fake_core else Core(cfg)

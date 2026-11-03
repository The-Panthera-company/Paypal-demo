"""The tools call the right core API routes with the internal token and pass API errors through."""

import asyncio
import json

import httpx
import pytest

import server
from mcp.server.mcpserver.exceptions import ToolError


@pytest.fixture
def api(monkeypatch):
    """A fake core API recording each request; reply with `api.reply = (status, body)`."""

    class Fake:
        requests: list[httpx.Request] = []
        reply: tuple[int, object] = (200, {})

        def handler(self, request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if request.url.path == "/rounds/current":
                return httpx.Response(200, json={"id": 7})
            status, body = self.reply
            return httpx.Response(status, json=body)

    fake = Fake()
    fake.requests = []
    client = httpx.Client(base_url="http://api.test", headers={"Authorization": "Bearer t0ken"},
                          transport=httpx.MockTransport(fake.handler))
    monkeypatch.setattr(server, "_client", client)
    return fake


def call(name: str, **arguments):
    return asyncio.run(server.server.call_tool(name, arguments))


def payload(result) -> object:
    if result.structured_content is not None:
        content = result.structured_content
        return content.get("result", content) if isinstance(content, dict) and set(content) == {"result"} else content
    return json.loads(result.content[0].text)


def test_checked_donation_posts_to_the_api_with_the_token(api):
    api.reply = (200, {"status": "rejected", "donation_id": None, "rule_result": "excluded_tag", "reason": "tagged"})
    result = call("request_checked_donation", mandate_run_id=5, project_id=2, amount_cents=300, reason="few backers")
    assert not result.is_error
    assert payload(result)["rule_result"] == "excluded_tag"
    req = api.requests[-1]
    assert (req.method, req.url.path) == ("POST", "/internal/checked-donations")
    assert req.headers["Authorization"] == "Bearer t0ken"
    assert json.loads(req.content) == {"mandate_run_id": 5, "project_id": 2, "amount_cents": 300, "reason": "few backers"}


def test_search_projects_maps_filters(api):
    api.reply = (200, [{"id": 1, "title": "Lanet Library"}])
    result = call("search_projects", category_id=2, exclude_tags=["faith-based", "stem"], sort="fewest_backers")
    assert payload(result) == [{"id": 1, "title": "Lanet Library"}]
    params = dict(api.requests[-1].url.params)
    assert params == {"category_id": "2", "exclude_tags": "faith-based,stem", "sort": "fewest_backers", "limit": "50"}


def test_payout_request_sends_the_four_checks(api):
    api.reply = (200, {"status": "held_for_admin", "payout_id": None, "reason": "Held: dated_in_window"})
    call("request_milestone_payout", milestone_id=3, receipt_total_within_10pct=True, supplier_matches_plan=True,
         photo_not_duplicate=True, dated_in_window=False, summary="Receipt dated last year")
    body = json.loads(api.requests[-1].content)
    assert body["checks"]["dated_in_window"] is False and body["summary"] == "Receipt dated last year"


def test_leaderboard_uses_the_open_round(api):
    api.reply = (200, {"round_id": 7, "rows": []})
    assert payload(call("get_leaderboard"))["round_id"] == 7
    assert api.requests[-1].url.path == "/rounds/7/leaderboard"


def test_api_errors_become_tool_errors_with_the_code(api):
    """Called in-process the ToolError is raised; over MCP the client gets it as an error result."""
    api.reply = (404, {"detail": {"error": "MANDATE_RUN_NOT_FOUND", "message": "Record the run first"}})
    with pytest.raises(ToolError, match="MANDATE_RUN_NOT_FOUND: Record the run first"):
        call("request_checked_donation", mandate_run_id=99, project_id=1, amount_cents=100, reason="x")


def test_read_tools_are_marked_read_only():
    tools = {t.name: t for t in asyncio.run(server.server.list_tools())}
    assert tools["search_projects"].annotations.read_only_hint is True
    assert tools["request_checked_donation"].annotations.read_only_hint is False

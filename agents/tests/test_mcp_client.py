"""Normalization tests: mcp 2.x wraps tool results as {"result": ...}."""
import pytest

from app.mcp_client import FakeMcpClient, _normalize


def test_wrapped_list_is_unwrapped():
    assert _normalize({"result": [{"id": 1}]}) == [{"id": 1}]


def test_bare_list_passes_through():
    assert _normalize([{"id": 1}]) == [{"id": 1}]


def test_wrapped_dict_is_unwrapped():
    assert _normalize({"result": {"id": 2}}) == {"id": 2}


def test_multi_key_dict_with_result_is_left_alone():
    value = {"result": [1], "other": 2}
    assert _normalize(value) == value


def test_scalar_passes_through():
    assert _normalize(None) is None
    assert _normalize(7) == 7


@pytest.mark.asyncio
async def test_fake_client_returns_list_for_wrapped_response():
    mcp = FakeMcpClient({"search_projects": {"result": [{"id": 1, "title": "a"}]}})
    out = await mcp.call("search_projects", limit=1)
    assert isinstance(out, list)
    assert out == [{"id": 1, "title": "a"}]


@pytest.mark.asyncio
async def test_fake_client_returns_list_for_bare_response():
    mcp = FakeMcpClient({"search_projects": [{"id": 1}]})
    out = await mcp.call("search_projects", limit=1)
    assert isinstance(out, list)


@pytest.mark.asyncio
async def test_fake_client_defaults_are_lists():
    mcp = FakeMcpClient()
    assert isinstance(await mcp.call("search_projects"), list)
    assert isinstance(await mcp.call("list_active_mandates"), list)

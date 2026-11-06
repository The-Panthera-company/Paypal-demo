"""Normalization tests.

mcp 2.x answers a list tool with ONE content block per item, and the shape is decided by
the tool name (LIST_TOOLS), never by counting blocks.
"""
import json

import pytest

from app.mcp_client import (
    LIST_TOOLS,
    FakeMcpClient,
    McpUnavailable,
    _coerce_shape,
    _normalize,
    _unwrap,
)


class _Block:
    def __init__(self, text):
        self.text = text


class _Result:
    def __init__(self, blocks, is_error=False, structured=None):
        self.content = [_Block(b) for b in blocks]
        self.isError = is_error
        self.structuredContent = structured


# --- list tools: 0, 1 and 3 blocks -------------------------------------------


def test_list_tool_with_zero_blocks_returns_empty_list():
    out = _unwrap(_Result([]), "search_projects")
    assert out == []


def test_list_tool_with_one_block_returns_one_item_list():
    out = _unwrap(_Result([json.dumps({"id": 1})]), "search_projects")
    assert isinstance(out, list)
    assert out == [{"id": 1}]


def test_list_tool_with_three_blocks_returns_three_items():
    blocks = [json.dumps({"id": i}) for i in (1, 2, 3)]
    out = _unwrap(_Result(blocks), "search_projects")
    assert isinstance(out, list)
    assert out == [{"id": 1}, {"id": 2}, {"id": 3}]


def test_list_tool_with_single_block_holding_list_is_flattened():
    out = _unwrap(_Result([json.dumps([{"id": 1}, {"id": 2}])]), "list_active_mandates")
    assert out == [{"id": 1}, {"id": 2}]


def test_both_list_tools_are_in_the_set():
    assert {"search_projects", "list_active_mandates"} <= LIST_TOOLS


# --- object tools -------------------------------------------------------------


def test_object_tool_with_one_block_returns_dict():
    out = _unwrap(_Result([json.dumps({"id": 9, "title": "a"})]), "get_project")
    assert isinstance(out, dict)
    assert out == {"id": 9, "title": "a"}


@pytest.mark.parametrize(
    "tool",
    [
        "get_project",
        "record_mandate_run",
        "request_checked_donation",
        "open_watchdog_case",
        "request_milestone_payout",
        "log_decision",
        "get_leaderboard",
    ],
)
def test_every_object_tool_returns_a_dict(tool):
    out = _unwrap(_Result([json.dumps({"id": 1})]), tool)
    assert isinstance(out, dict)


def test_object_tool_with_no_blocks_returns_none():
    assert _unwrap(_Result([]), "get_project") is None


# --- generic normalization ----------------------------------------------------


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


def test_plain_text_block_returns_text():
    assert _unwrap(_Result(["not json"]), "get_project") == "not json"


def test_unwrap_raises_on_error_result():
    with pytest.raises(McpUnavailable):
        _unwrap(_Result(["boom"], is_error=True), "get_project")


# --- FakeMcpClient mirrors the rule -------------------------------------------


def test_coerce_shape_list_tool_from_none():
    assert _coerce_shape("search_projects", None) == []


def test_coerce_shape_list_tool_from_dict():
    assert _coerce_shape("search_projects", {"id": 1}) == [{"id": 1}]


def test_coerce_shape_object_tool_from_dict():
    assert _coerce_shape("get_project", {"id": 1}) == {"id": 1}


@pytest.mark.asyncio
async def test_fake_client_list_tool_returns_list_for_one_item():
    mcp = FakeMcpClient({"search_projects": [{"id": 1}]})
    out = await mcp.call("search_projects", limit=1)
    assert isinstance(out, list)
    assert out == [{"id": 1}]


@pytest.mark.asyncio
async def test_fake_client_list_tool_returns_empty_list():
    mcp = FakeMcpClient({"search_projects": None})
    assert await mcp.call("search_projects", q="zzzzqqqq") == []


@pytest.mark.asyncio
async def test_fake_client_defaults_match_tool_shape():
    mcp = FakeMcpClient()
    assert isinstance(await mcp.call("search_projects"), list)
    assert isinstance(await mcp.call("list_active_mandates"), list)
    for tool in (
        "get_project",
        "record_mandate_run",
        "request_checked_donation",
        "open_watchdog_case",
        "request_milestone_payout",
        "log_decision",
        "get_leaderboard",
    ):
        assert isinstance(await mcp.call(tool), dict), tool

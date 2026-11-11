"""Graph detector tests. Pure functions over seeded events, plus scan() through fakes."""
from datetime import datetime, timedelta, timezone

import pytest

from app.agents import graph
from app.agents.watchdog import FakeEventsSource, WatchdogAgent
from app.mcp_client import FakeMcpClient

NOW = datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)


def ev(pid, donor, amount=500, days_ago=1, status="captured"):
    return {
        "donation_id": f"{pid}-{donor}-{days_ago}",
        "project_id": pid,
        "donor_id": donor,
        "status": status,
        "amount_cents": amount,
        "captured_at": (NOW - timedelta(days=days_ago)).isoformat(),
        "donor_created_at": (NOW - timedelta(days=days_ago + 5)).isoformat(),
        "owner_donor_id": 900,
        "is_guest": False,
    }


def ring(donors=(1, 2, 3, 4), projects=(10, 11, 12), amount=500, days=(1, 2, 3)):
    """Every donor backs every project: the textbook ring."""
    events = []
    for i, donor in enumerate(donors):
        for j, project in enumerate(projects):
            events.append(ev(project, donor, amount, days[(i + j) % len(days)]))
    return events


def test_ring_of_four_over_three_projects_is_one_hit():
    clusters = graph.find_clusters(ring(), NOW)
    assert len(clusters) == 1
    assert clusters[0]["donor_ids"] == [1, 2, 3, 4]
    assert clusters[0]["projects"] == [10, 11, 12]


def test_unrelated_donors_alone_are_not_a_cluster():
    events = [ev(10 + i, i + 1) for i in range(4)]
    assert graph.find_clusters(events, NOW) == []


def test_two_donors_sharing_one_project_are_not_a_cluster():
    events = [ev(10, 1), ev(10, 2), ev(11, 1), ev(12, 2)]
    assert graph.find_clusters(events, NOW) == []


def test_ratio_just_under_the_floor_is_not_a_cluster():
    # Donor 1 backs {10,11,12}; donor 2 backs {10,11,12,13}: shared 3 of min(3,4)=3 -> 1.0.
    # Build the failing case instead: donor 1 shares 2 of its 4 projects -> 0.5.
    donor_one = [10, 11, 12, 13]
    donor_two = [10, 11, 14, 15]
    events = [ev(p, 1) for p in donor_one] + [ev(p, 2) for p in donor_two]
    clusters = graph.find_clusters(events, NOW)
    assert clusters == [], "2 shared of min(4,4) = 0.50 is below the 0.60 floor"


def test_ratio_exactly_at_the_floor_with_two_shared_is_a_cluster():
    # 3 shared of min(5,5) = 0.60 exactly.
    donor_one = [10, 11, 12, 20, 21]
    donor_two = [10, 11, 12, 30, 31]
    events = [ev(p, 1) for p in donor_one] + [ev(p, 2) for p in donor_two]
    clusters = graph.find_clusters(events, NOW)
    assert len(clusters) == 1
    assert clusters[0]["donor_ids"] == [1, 2]


def test_refunded_gifts_are_ignored():
    events = ring()
    events.append(ev(13, 5, 500, 1, status="refunded"))
    clusters = graph.find_clusters(events, NOW)
    assert len(clusters) == 1
    assert 5 not in clusters[0]["donor_ids"]


def test_events_older_than_the_window_are_ignored():
    old = ring(days=(31, 32, 33))
    assert graph.find_clusters(old, NOW) == []


def test_null_donor_or_project_is_skipped():
    events = ring()
    events.append({**ev(10, 1), "donor_id": None})
    events.append({**ev(10, 1), "project_id": None})
    assert len(graph.find_clusters(events, NOW)) == 1


def test_evidence_donor_ids_are_ints_from_the_input():
    events = ring()
    hit = graph.hits(graph.find_clusters(events, NOW))[0]
    ids = hit["evidence"]["donor_ids"]
    assert all(type(d) is int for d in ids)
    assert set(ids) <= {e["donor_id"] for e in events}


def test_graph_has_no_names_and_edges_point_at_real_nodes():
    events = ring()
    hit = graph.hits(graph.find_clusters(events, NOW))[0]
    g = hit["evidence"]["graph"]
    donor_nodes = [n for n in g["nodes"] if n["type"] == "donor"]
    assert all(n["label"] == f"Donor {n['id']}" for n in donor_nodes)
    ids = {n["id"] for n in g["nodes"]}
    for edge in g["edges"]:
        assert edge["source"] in ids and edge["target"] in ids


def test_graph_labels_use_titles_when_known():
    events = ring()
    clusters = graph.find_clusters(events, NOW)
    hit = graph.hits(clusters, {10: "Borehole Two"})[0]
    labels = {n["id"]: n["label"] for n in hit["evidence"]["graph"]["nodes"]}
    assert labels[10] == "Borehole Two"
    assert labels[11] == "Project 11"


def test_metrics_mirror_analyse_ring():
    """The same formulas CollusionGraph.analyseRing uses, applied to our graph."""
    events = ring()
    hit = graph.hits(graph.find_clusters(events, NOW))[0]
    ev_ = hit["evidence"]
    g = ev_["graph"]
    cluster = {str(d) for d in ev_["donor_ids"]}
    nodes, edges = g["nodes"], g["edges"]
    donors = [n for n in nodes if n["type"].lower() == "donor"]
    ring_edges = [e for e in edges if str(e["source"]) in cluster]
    backers = {}
    for edge in ring_edges:
        backers.setdefault(str(edge["target"]), set()).add(str(edge["source"]))
    shared = sum(1 for s in backers.values() if len(s) >= 2)
    projects = len(backers)
    assert ev_["counts"]["donors"] == len(donors)
    assert ev_["counts"]["projects"] == projects
    assert ev_["counts"]["shared"] == shared
    assert ev_["counts"]["total_cents"] == sum(e["weight"] for e in ring_edges)
    assert ev_["ratio"] == pytest.approx(shared / projects, abs=1e-4)


def test_case_project_is_the_heaviest_tie_to_lowest_id():
    events = ring()
    events.append(ev(12, 1, 5000, 1))  # project 12 now holds most of the money
    clusters = graph.find_clusters(events, NOW)
    assert clusters[0]["project_id"] == 12


def test_large_gifts_with_concentrated_support_are_skipped():
    """Two projects, four donors, every gift above $10: ordinary neighbours, not a ring."""
    events = ring(donors=(1, 2, 3, 4), projects=(10, 11), amount=5000)
    assert graph.find_clusters(events, NOW) == []


def test_large_gifts_spread_wide_are_still_reported():
    """The guard needs both halves: big gifts over three projects is still a ring."""
    events = ring(donors=(1, 2, 3, 4), projects=(10, 11, 12), amount=5000)
    assert len(graph.find_clusters(events, NOW)) == 1


def test_one_project_dominating_the_money_is_skipped():
    """Large gifts where one project holds >=80%: a committed backer, not collusion."""
    events = [ev(10, d, 9000, 1) for d in (1, 2, 3, 4)]
    events += [ev(11, d, 500, 2) for d in (1, 2, 3, 4)]
    events += [ev(12, d, 500, 3) for d in (1, 2, 3, 4)]
    assert graph.find_clusters(events, NOW) == []


def test_small_gifts_are_never_guarded_away():
    """The same shape at $5 a gift is exactly what this rule exists to catch."""
    events = ring(donors=(1, 2, 3, 4), projects=(10, 11), amount=500)
    assert len(graph.find_clusters(events, NOW)) == 1


@pytest.mark.asyncio
async def test_scan_opens_one_case_for_the_seeded_ring():
    mcp = FakeMcpClient({"get_project": lambda **kw: {"id": kw["project_id"],
                                                    "title": f"Project {kw['project_id']}"}})
    agent = WatchdogAgent(mcp=mcp, source=FakeEventsSource(ring()))
    opened = await agent.scan(NOW)
    cases = [o for o in opened if o["rule"] == "collusion_cluster"]
    assert len(cases) == 1
    calls = [c for c in mcp.calls if c[0] == "open_watchdog_case"]
    assert len([c for c in calls if c[1]["rule"] == "collusion_cluster"]) == 1


@pytest.mark.asyncio
async def test_a_second_scan_opens_nothing():
    mcp = FakeMcpClient({"get_project": lambda **kw: {"id": kw["project_id"],
                                                    "title": f"Project {kw['project_id']}"}})
    agent = WatchdogAgent(mcp=mcp, source=FakeEventsSource(ring()))
    await agent.scan(NOW)
    first = [c for c in mcp.calls if c[0] == "open_watchdog_case"]
    second = await agent.scan(NOW + timedelta(minutes=5))
    after = [c for c in mcp.calls if c[0] == "open_watchdog_case"]
    assert len(first) == 1
    assert len(after) == 1, "the same donor set must not be reported twice"
    assert second == []


@pytest.mark.asyncio
async def test_graph_beats_reciprocal_backing_when_it_is_larger():
    """Four co-backing donors: the pair rule would name two, the cluster names four."""
    mcp = FakeMcpClient({"get_project": lambda **kw: {"id": kw["project_id"],
                                                    "title": "P"}})
    agent = WatchdogAgent(mcp=mcp, source=FakeEventsSource(ring()))
    await agent.scan(NOW)
    rules = [c[1]["rule"] for c in mcp.calls if c[0] == "open_watchdog_case"]
    assert "collusion_cluster" in rules
    assert "reciprocal_backing" not in rules, "the larger cluster covers the pair"

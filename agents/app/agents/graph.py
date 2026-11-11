"""Collusion graph: shared-backer clusters over donation events. No LLM, no networkx.

Input is the same event shape the Watchdog rules use: donor_id (Donor.id int), project_id,
amount_cents, captured_at, status. Only "captured" events count and the window is relative to
an injected `now`, so a scan is reproducible.

Clustering is union-find over donors: a donor backs the set of projects they gave to; two
donors are joined when they share at least `min_shared` projects AND that overlap is at least
`min_ratio` of the smaller donor's project set. Every connected component of two or more
donors becomes one cluster.

False-positive guard, in one sentence: a cluster is skipped when none of its gifts is small
(every gift above `small_gift_cents`) AND the spending looks like ordinary concentrated
support - one project holds at least 80% of the cluster's money, or the cluster touches only
two projects while having at least four donors. Both shapes are what a few committed
neighbours look like; neither is what a ring bought with many small gifts looks like. The
guard needs both halves, so a ring of large gifts spread over three or more projects is still
reported.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

log = logging.getLogger(__name__)

CONFIG: dict[str, Any] = {
    "window_days": 30,
    "min_projects_per_donor": 2,
    "min_shared": 2,
    "min_ratio": 0.60,
    # $10: a gift at or below this is "small" and never counts as concentrated support.
    "small_gift_cents": 1000,
    "min_cluster_donors": 2,
    # Guard thresholds (see the module docstring).
    "concentrated_share": 0.80,
    "concentrated_projects": 2,
    "concentrated_donors": 4,
}

RULE = "collusion_cluster"


def _parse(ts: Any) -> datetime | None:
    if not ts:
        return None
    try:
        value = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _usable(event: dict) -> bool:
    """Captured, identified, positively priced."""
    if event.get("status") != "captured":
        return False
    if event.get("donor_id") is None or event.get("project_id") is None:
        return False
    return (event.get("amount_cents") or 0) > 0


class _Union:
    """Union-find keyed by donor id. Smallest id wins, so roots are stable."""

    def __init__(self) -> None:
        self.parent: dict[int, int] = {}

    def find(self, item: int) -> int:
        self.parent.setdefault(item, item)
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        a, b = self.find(left), self.find(right)
        if a != b:
            self.parent[max(a, b)] = min(a, b)


def _is_concentrated(per_project: dict[int, int], donors: int) -> bool:
    """Ordinary concentrated support: one project dominates the money, or only two projects."""
    total = sum(per_project.values())
    if not total:
        return False
    if max(per_project.values()) / total >= CONFIG["concentrated_share"]:
        return True
    return (len(per_project) <= CONFIG["concentrated_projects"]
            and donors >= CONFIG["concentrated_donors"])

def _window_start(now: datetime) -> datetime:
    return now - timedelta(days=CONFIG["window_days"])


def _collect(events: Iterable[dict], now: datetime):
    """One pass: donor -> projects, (donor, project) -> cents, and the event timestamps."""
    start = _window_start(now)
    by_donor: dict[int, set[int]] = {}
    pair_cents: dict[tuple[int, int], int] = {}
    stamps: list[datetime] = []
    for event in events:
        if not _usable(event):
            continue
        captured = _parse(event.get("captured_at"))
        if captured is None or captured < start or captured > now:
            continue
        donor, project = int(event["donor_id"]), int(event["project_id"])
        by_donor.setdefault(donor, set()).add(project)
        cents = int(event.get("amount_cents") or 0)
        pair_cents[(donor, project)] = pair_cents.get((donor, project), 0) + cents
        stamps.append(captured)
    return by_donor, pair_cents, stamps, start


def _shared(left: set[int], right: set[int]) -> set[int]:
    return left & right


def _ratio(left: set[int], right: set[int]) -> float:
    """Overlap relative to the smaller set: the donor with less to lose is what matters."""
    shared = _shared(left, right)
    smaller = min(len(left), len(right))
    return len(shared) / smaller if smaller else 0.0


def find_clusters(events: Iterable[dict], now: datetime | None = None) -> list[dict]:
    """Every shared-backer cluster in the window, richest first. No titles, no network."""
    now = now or datetime.now(timezone.utc)
    by_donor, pair_cents, stamps, start = _collect(list(events), now)

    members = {d: ps for d, ps in by_donor.items()
               if len(ps) >= CONFIG["min_projects_per_donor"]}
    if len(members) < CONFIG["min_cluster_donors"]:
        return []

    ids = sorted(members)
    union = _Union()
    for index, left in enumerate(ids):
        for right in ids[index + 1:]:
            if len(_shared(members[left], members[right])) < CONFIG["min_shared"]:
                continue
            if _ratio(members[left], members[right]) >= CONFIG["min_ratio"]:
                union.union(left, right)

    groups: dict[int, list[int]] = {}
    for donor in ids:
        groups.setdefault(union.find(donor), []).append(donor)

    clusters = []
    for root in sorted(groups):
        donors = sorted(groups[root])
        if len(donors) < CONFIG["min_cluster_donors"]:
            continue
        cluster = _describe(donors, members, pair_cents, stamps, start, now)
        if cluster is not None:
            clusters.append(cluster)

    clusters.sort(key=lambda c: (-c["total_cents"], c["donor_ids"][0]))
    return clusters


def _describe(donors: list[int], members: dict, pair_cents: dict, stamps: list[datetime],
              start: datetime, now: datetime) -> dict | None:
    """Turn one component into a cluster, or None when the false-positive guard fires."""
    per_project: dict[int, int] = {}
    edges: list[tuple[int, int, int]] = []
    for donor in donors:
        for project in sorted(members[donor]):
            cents = pair_cents.get((donor, project), 0)
            if cents:
                edges.append((donor, project, cents))
                per_project[project] = per_project.get(project, 0) + cents

    total = sum(per_project.values())
    if not total:
        return None

    small = all(cents <= CONFIG["small_gift_cents"] for _, _, cents in edges)
    if not small and _is_concentrated(per_project, len(donors)):
        log.info("collusion cluster %s skipped: large gifts, concentrated support", donors)
        return None

    # Density is a property of the donor graph, so it must be measured over donor pairs:
    # how many of the possible pairs actually share enough projects to be linked. Dividing
    # donor->project edges by donor pairs would mix two different units.
    possible = len(donors) * (len(donors) - 1) / 2
    linked_pairs = sum(
        1 for index, left in enumerate(donors) for right in donors[index + 1:]
        if len(_shared(members[left], members[right])) >= CONFIG["min_shared"]
    )
    # "shared" is the number of PROJECTS backed by two or more cluster donors - the same
    # quantity CollusionGraph.analyseRing computes, so ratio = shared/projects stays <= 1.
    # The donor-pair count is reported separately as linked_pairs.
    shared_projects = sum(
        1 for project in per_project
        if sum(1 for donor in donors if project in members[donor]) >= 2
    )
    projects = sorted(per_project)
    case_project = min(projects, key=lambda p: (-per_project[p], p))
    cluster_stamps = [s for s in stamps if start <= s <= now]

    return {
        "donor_ids": donors,
        "projects": projects,
        "project_id": case_project,
        "total_cents": total,
        "per_project_cents": per_project,
        "shared": shared_projects,
        "linked_pairs": linked_pairs,
        # Linked donor pairs / all possible donor pairs: 1.0 means everyone cross-backs with
        # everyone. Always between 0 and 1.
        "density": round(linked_pairs / possible, 4) if possible else 0.0,
        "edges": edges,
        "from": min(cluster_stamps) if cluster_stamps else start,
        "to": max(cluster_stamps) if cluster_stamps else now,
    }


def evidence_graph(cluster: dict, titles: dict[int, str] | None = None) -> dict:
    """The nodes/edges shape CollusionGraph.tsx renders.

    Donors come first as type "donor" with label "Donor <id>" - never a name. Projects are
    whatever type is left over, labelled with the public title when one was fetched.
    Edges run donor -> project with the cents given as weight, which is what analyseRing
    sums for `total` and what it follows to count shared projects.
    """
    titles = titles or {}
    nodes = [{"id": donor, "type": "donor", "label": f"Donor {donor}"}
             for donor in cluster["donor_ids"]]
    for project in cluster["projects"]:
        nodes.append({"id": project, "type": "project",
                      "label": titles.get(project) or f"Project {project}"})
    edges = [{"source": donor, "target": project, "weight": cents}
             for donor, project, cents in cluster["edges"]]
    return {"nodes": nodes, "edges": edges}


def evidence(cluster: dict, titles: dict[int, str] | None = None) -> dict:
    """The evidence dict the API validates: sorted int donor_ids plus a renderable graph."""
    donor_ids = sorted(int(d) for d in cluster["donor_ids"])
    return {
        "donor_ids": donor_ids,
        "counts": {
            "donors": len(donor_ids),
            "projects": len(cluster["projects"]),
            "shared": cluster["shared"],
            "total_cents": cluster["total_cents"],
        },
        "ratio": round(cluster["shared"] / len(cluster["projects"]), 4) if cluster["projects"] else 0.0,
        "density": cluster["density"],
        "window": {
            "from": cluster["from"].isoformat(),
            "to": cluster["to"].isoformat(),
            "days": CONFIG["window_days"],
        },
        "graph": evidence_graph(cluster, titles),
    }


def hits(clusters: list[dict], titles: dict[int, str] | None = None) -> list[dict]:
    """One Watchdog hit per cluster. project_id is the cluster's heaviest project."""
    return [{"project_id": c["project_id"], "rule": RULE, "evidence": evidence(c, titles)}
            for c in clusters]


async def project_titles(mcp, project_ids: Iterable[int]) -> dict[int, str]:
    """Public titles for the cluster projects only, failing soft: no title, no problem."""
    found: dict[int, str] = {}
    for project_id in sorted(set(project_ids)):
        try:
            project = await mcp.call("get_project", project_id=int(project_id))
        except Exception as exc:  # noqa: BLE001 - a missing title must never lose a case
            log.info("no title for project %s: %s", project_id, exc)
            continue
        if isinstance(project, dict):
            title = str(project.get("title") or "").strip()
            if title:
                found[int(project_id)] = title
    return found

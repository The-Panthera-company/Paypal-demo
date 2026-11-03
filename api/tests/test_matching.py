"""Allocation math against the System Design worked example (Education, 10,000 pool)."""

from app.matching import closest_to_goal_split, crowd_split, quadratic_score, split


def test_scores_match_worked_example():
    assert quadratic_score([(25, 1)] * 16) == 6000  # Lanet Library
    assert quadratic_score([(25, 1)] * 9) == 1800  # Kaptembwo Desks
    assert quadratic_score([(100, 1)] * 4) == 1200  # Girls' STEM Club: same money, fewer people
    assert quadratic_score([]) == 0  # New Reading Corner
    assert quadratic_score([(5000, 1)]) == 0  # one person alone earns no score


def test_guest_counts_half():
    assert quadratic_score([(100, 1), (100, 0.5)]) == 100  # 2 * 10 * 5
    assert quadratic_score([(100, 1), (100, 1)]) == 200


def test_crowd_split_matches_worked_example_before_caps():
    scores = {1: 6000, 2: 1800, 3: 1200, 4: 0}
    assert crowd_split(10_000, scores, floor_pct=20) == {1: 5833, 2: 2100, 3: 1567, 4: 500}


def test_crowd_split_without_scores_is_equal():
    assert crowd_split(900, {1: 0, 2: 0, 3: 0}) == {1: 300, 2: 300, 3: 300}


def test_split_always_adds_up_and_is_deterministic():
    out = split(1000, {3: 1, 1: 1, 2: 1})
    assert out == {1: 334, 2: 333, 3: 333}  # leftover cent to the lowest id
    assert sum(split(999_999, {1: 0.3, 2: 0.3, 7: 0.4}).values()) == 999_999


def test_closest_to_goal_fills_nearest_first_then_shares_rest():
    assert closest_to_goal_split(3000, {1: 120_000, 2: 1000}) == {1: 2000, 2: 1000}
    assert closest_to_goal_split(3000, {1: 500, 2: 1000}) == {1: 1250, 2: 1750}  # both full, 1500 left

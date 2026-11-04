"""Cache stability: a projection may only ever change at its tail."""
from __future__ import annotations

import _helpers as H


def test_same_input_same_projection(lc):
    msgs = H.conversation([H.CODE, H.BIG, H.BIG, H.CODE, H.CODE])
    first, first_stats = lc.project(msgs, session="t", seq=1)
    second, second_stats = lc.project(msgs, session="t", seq=99)   # seq must not matter
    assert first is not None and second is not None
    assert first_stats["cut_sig"] == second_stats["cut_sig"]
    assert first_stats["proj_hash"] == second_stats["proj_hash"]


def test_cut_points_only_grow(lc):
    """Appending a turn must never move an earlier cut: a cut that moves rewrites the
    middle of the prefix and re-bills everything after it."""
    bodies = [H.CODE, H.BIG, H.BIG, H.BIG, H.BIG, H.BIG]
    previous = None
    for depth in range(3, len(bodies) + 1):
        msgs = H.conversation(bodies[:depth])
        projected, stats = lc.project(msgs, session="t", seq=depth)
        if projected is None:
            continue
        signature = [tuple(x[:2]) for x in stats["cut_sig"]]
        if previous is not None:
            assert signature[:len(previous)] == previous, f"cut points moved at depth {depth}"
        previous = signature


def test_shared_prefix_survives_a_new_turn(lc):
    """Compare two consecutive requests: everything except the last message must match."""
    bodies = [H.CODE, H.BIG, H.BIG, H.BIG]
    previous_projection = None
    for depth in range(3, len(bodies) + 1):
        msgs = H.conversation(bodies[:depth])
        projected, _ = lc.project(msgs, session="t", seq=depth)
        if projected is None:
            continue
        if previous_projection is not None:
            shared = 0
            for before, after in zip(previous_projection, projected):
                if before.get("role") == after.get("role") and \
                        (before.get("content") or "") == (after.get("content") or ""):
                    shared += 1
                else:
                    break
            drift = len(previous_projection) - shared
            assert drift <= 2, f"projection changed {drift} messages before its tail"
        previous_projection = projected

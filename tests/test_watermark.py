"""Watermark regression tests.

The engine used to read ``sizes[pos]`` instead of ``sizes[pos - 1]`` when deciding
where the first cut lands. A short session (three segments) then never crossed the
watermark at all and silently never cut anything.
"""
from __future__ import annotations

import _helpers as H


def test_first_turn_crossing_the_watermark_is_cut_first(lc_nokeep):
    msgs = H.conversation([H.BIG, H.SMALL, H.SMALL])
    projected, stats = lc_nokeep.project(msgs, session="t", seq=1)
    assert stats["segments"] == 4
    assert stats["first_cut"] == 0, f"expected the first turn, got {stats['first_cut']}"
    assert stats["cuts"] >= 1 and projected is not None


def test_cut_starts_at_the_turn_that_crossed(lc_nokeep):
    msgs = H.conversation([H.SMALL, H.BIG, H.SMALL])
    projected, stats = lc_nokeep.project(msgs, session="t", seq=1)
    assert stats["first_cut"] == 1, f"expected first_cut=1, got {stats['first_cut']}"
    assert stats["cuts"] == 1
    # hard-line gates and the size floor still apply: the tiny turn is not cut
    assert stats["skips"].get("not_eligible") == 1


def test_below_the_watermark_nothing_happens(lc):
    msgs = [H.system(100)] + H.turn(1, H.SMALL) + [{"role": "user", "content": "继续。"}]
    projected, stats = lc.project(msgs, session="t", seq=1)
    assert projected is None and stats["cuts"] == 0 and stats["first_cut"] is None


def test_watermark_is_configurable(lc_nokeep):
    lc_nokeep.MIN_TOTAL = 10 ** 9
    msgs = H.conversation([H.BIG, H.BIG, H.BIG])
    projected, stats = lc_nokeep.project(msgs, session="t", seq=1)
    assert projected is None and stats["first_cut"] is None

    lc_nokeep.MIN_TOTAL = 6000
    projected, stats = lc_nokeep.project(msgs, session="t", seq=1)
    assert projected is not None and stats["cuts"] >= 1

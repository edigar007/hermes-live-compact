"""The 1.0.6 keep window, and window-relative sizing.

The failure this fixes was measured on 0.2.0: a cut removed exactly the details the next
turn needed, and the model would not go read the backup on its own. Keeping the newest
rounds as raw text is more reliable than handing over a path.
"""
from __future__ import annotations

import _helpers as H


def test_sizing_is_window_relative(lc):
    assert lc.sizing(1_000_000) == (44800, 3, 32000)
    assert lc.sizing(200_000) == (8960, 3, 6400)
    # Nothing sane happens on a tiny window: scale down, never protect more than we cut.
    assert lc.sizing(128_000)[0] > lc.sizing(128_000)[2]


def test_keep_window_always_fits_inside_the_watermark(lc):
    """Upstream's caveat: keep_tokens > min_total means the engine protects everything it
    was asked to cut and silently never cuts again."""
    for window in (8_000, 32_000, 64_000, 128_000, 200_000, 400_000, 1_000_000, 2_000_000):
        min_total, _rounds, keep_tokens = lc.sizing(window)
        assert min_total > keep_tokens, f"window {window}: {min_total} <= {keep_tokens}"


def test_unknown_window_falls_back_to_configured_min_total(lc):
    min_total, _rounds, keep_tokens = lc.sizing(0)
    assert min_total == lc.MIN_TOTAL
    assert keep_tokens < min_total


def test_newest_rounds_are_never_cut(lc):
    """Default settings on a six-turn session: the newest three turns stay verbatim."""
    bodies = [H.BIG + f" #mark{i}" for i in range(6)]
    msgs = H.conversation(bodies)
    projected, stats = lc.project(msgs, session="t", seq=1)

    assert projected is not None and stats["cuts"] >= 1
    assert stats["protected_rounds"] >= 3
    cut_positions = [c["pos"] for c in stats["cut"]]
    assert max(cut_positions) < stats["protected_from"], "a protected turn was cut anyway"

    joined = "\n".join(m.get("content") or "" for m in projected if isinstance(m.get("content"), str))
    for index in range(6 - stats["protected_rounds"], 6):
        assert f"#mark{index}" in joined, f"turn {index} was inside the keep window but got cut"


def test_protection_grows_until_the_token_budget_is_met(lc):
    bodies = [H.BIG + f" #mark{i}" for i in range(9)]
    msgs = H.conversation(bodies)
    _projected, stats = lc.project(msgs, session="t", seq=1, window=1_000_000)
    assert stats["keep_tokens"] == 32000
    assert stats["protected_tokens"] >= 32000, "keep window stopped short of its token budget"


def test_short_session_is_covered_by_the_keep_window(lc):
    """Three turns and a keep window of three rounds: cut nothing, say why."""
    msgs = H.conversation([H.BIG, H.BIG, H.BIG])
    projected, stats = lc.project(msgs, session="t", seq=1)
    assert projected is None
    assert stats["skips"].get("covered_by_keep_window") == 1


def test_keep_window_off_restores_aggressive_cutting(lc_nokeep):
    msgs = H.conversation([H.BIG, H.BIG, H.BIG])
    projected, stats = lc_nokeep.project(msgs, session="t", seq=1)
    assert projected is not None and stats["cuts"] >= 1

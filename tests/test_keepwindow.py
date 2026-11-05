"""The 1.0.6 keep window, and window-relative sizing.

The failure this fixes was measured on 0.2.0: a cut removed exactly the details the next
turn needed, and the model would not go read the backup on its own. Keeping the newest
rounds as raw text is more reliable than handing over a path.
"""
from __future__ import annotations

import _helpers as H


def test_sizing_is_window_relative(lc):
    # Upstream 1.0.6 numbers at 1M (watermark 20k / keep 3 rounds / 32k), scaled by window.
    assert lc.sizing(1_000_000) == (20000, 3, 32000)
    assert lc.sizing(200_000) == (4000, 3, 6400)
    assert lc.sizing(128_000) == (2560, 3, 4096)


def test_watermark_is_never_pinned_to_the_keep_window(lc):
    """0.3.2 did ``watermark = max(keep * 1.4, 2% window)``, which turned a 1M install's
    20 000 watermark into 44 800 and made ordinary sessions look like the engine never ran.
    The two knobs are independent: keep bounds protection, not the trigger."""
    for window in (128_000, 200_000, 1_000_000, 2_000_000):
        min_total, _rounds, keep_tokens = lc.sizing(window)
        assert min_total == max(2048, int(window * 0.02))
        assert keep_tokens == int(window * 0.032)


def test_a_multi_turn_session_still_cuts_at_every_window(lc):
    """The behavioural guard the old inequality test was standing in for."""
    bodies = [H.BIG + f" #w{i}" for i in range(8)]
    msgs = H.conversation(bodies)
    for window in (128_000, 200_000, 1_000_000):
        projected, stats = lc.project(msgs, session=f"w{window}", seq=1, window=window)
        assert stats["cuts"] >= 1, f"window {window}: {stats}"


def test_unknown_window_falls_back_to_configured_min_total(lc):
    min_total, rounds, keep_tokens = lc.sizing(0)
    assert min_total == lc.MIN_TOTAL
    assert rounds == lc.KEEP_ROUNDS == 3
    assert keep_tokens == lc.KEEP_ROUND_TOKENS == 32000


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

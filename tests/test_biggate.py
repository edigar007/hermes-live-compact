"""The 1.0.6 BIG_GATE: past 650k of history the engine hands the session back.

Upstream (`index.js`): `if (measurement.totalTokens < MIN_PRESSURE || measurement.totalTokens
>= BIG_GATE) return;` — one whole-session gate, not a per-turn one. Above it the host is going
to compress anyway, so continuing to project only adds risk.
"""
from __future__ import annotations

import _helpers as H


def test_default_gate_matches_upstream(lc):
    assert lc.BIG_GATE == 650_000


def test_history_at_the_gate_is_not_projected(lc):
    msgs = H.conversation([H.BIG + f" #{i}" for i in range(6)])
    # Shrink the gate instead of building a 650k-token transcript: the gate compares the
    # estimated size of the request against the constant, so a low gate exercises it exactly.
    saved = lc.BIG_GATE
    lc.BIG_GATE = lc.estimate_messages_tokens_rough(msgs) // 2
    try:
        projected, stats = lc.project(msgs, session="gate", seq=1)
    finally:
        lc.BIG_GATE = saved

    assert projected is None
    assert stats["cuts"] == 0
    assert "above_big_gate" in stats["skips"], stats["skips"]
    assert stats["skips"]["above_big_gate"] == stats["tokens_before"]


def test_history_just_below_the_gate_still_cuts(lc):
    msgs = H.conversation([H.BIG + f" #{i}" for i in range(6)])
    saved = lc.BIG_GATE
    lc.BIG_GATE = lc.estimate_messages_tokens_rough(msgs) * 2
    try:
        projected, stats = lc.project(msgs, session="gate", seq=2)
    finally:
        lc.BIG_GATE = saved

    assert stats["cuts"] >= 1
    assert "above_big_gate" not in stats["skips"]


def test_gate_can_be_disabled(lc):
    """big_gate = 0 means "never stop" — the knob is documented as an off switch."""
    msgs = H.conversation([H.BIG + f" #{i}" for i in range(6)])
    saved = lc.BIG_GATE
    lc.BIG_GATE = 0
    try:
        _projected, stats = lc.project(msgs, session="gate", seq=3)
    finally:
        lc.BIG_GATE = saved

    assert "above_big_gate" not in stats["skips"]

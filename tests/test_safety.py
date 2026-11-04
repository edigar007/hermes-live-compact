"""Safety valves: no cut when the backup cannot be written, and a clean off switch."""
from __future__ import annotations

import _helpers as H


def test_card_with_a_backup_requires_a_written_backup(lc):
    msgs = H.conversation([H.BIG, H.BIG, H.BIG])
    projected, stats = lc.project(msgs, session="t", seq=1)
    assert projected is not None and stats["cuts"] >= 1
    with_path = [c for c in stats["cut"] if c["card_has_path"]]
    assert with_path, "a large tool result should produce a card that points at a backup"
    for cut in with_path:
        assert cut["shadow"] is True, "card pointed at a backup that was not written"
    written = list(lc.SHADOW_DIR.glob("*.txt"))
    assert written and all(f.stat().st_size > 0 for f in written)


def test_no_cut_when_the_shadow_cannot_be_written(lc):
    lc.SHADOW_MAX_MB = 0                      # budget exhausted -> every write fails
    msgs = H.conversation([H.BIG + " tag=A", H.BIG + " tag=B", H.BIG + " tag=C"])
    projected, stats = lc.project(msgs, session="t", seq=2)
    assert projected is None, "cut happened although the backup could not be written"
    assert stats["skips"].get("shadow_unwritable", 0) >= 1


def test_disabled_engine_is_a_passthrough(lc):
    lc.ENABLED = False
    msgs = H.conversation([H.BIG, H.BIG])
    projected, stats = lc.project(msgs, session="t", seq=1)
    assert projected is None and stats["skips"].get("disabled") == 1


def test_card_never_grows(lc):
    """A card must be smaller than what it replaces, or the cut is refused."""
    lc.CARD_RATIO = 0.0                      # force every candidate to fail
    msgs = H.conversation([H.BIG, H.BIG])
    projected, stats = lc.project(msgs, session="t", seq=1)
    assert projected is None and stats["skips"].get("card_too_big", 0) >= 1

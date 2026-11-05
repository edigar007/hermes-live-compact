"""Safety valves: no cut when the backup cannot be written, and a clean off switch."""
from __future__ import annotations

import _helpers as H


def test_card_with_a_backup_requires_a_written_backup(lc_nokeep):
    msgs = H.conversation([H.BIG, H.BIG, H.BIG])
    projected, stats = lc_nokeep.project(msgs, session="t", seq=1)
    assert projected is not None and stats["cuts"] >= 1
    with_path = [c for c in stats["cut"] if c["card_has_path"]]
    assert with_path, "a large tool result should produce a card that points at a backup"
    for cut in with_path:
        assert cut["shadow"] is True, "card pointed at a backup that was not written"
        assert cut["raw"] >= 1, "no raw tool file was recorded for a cut turn"
    written = list(lc_nokeep.SHADOW_DIR.rglob("*.txt"))
    assert written and all(f.stat().st_size > 0 for f in written)
    # 1.0.6: every raw file has a sidecar with the hash/size it claims.
    for meta in lc_nokeep.SHADOW_DIR.rglob("raw-*.meta.json"):
        assert meta.is_file()


def test_raw_files_are_per_session(lc_nokeep):
    msgs = H.conversation([H.BIG, H.BIG, H.BIG])
    lc_nokeep.project(msgs, session="sess-A", seq=1)
    dirs = [d.name for d in lc_nokeep.SHADOW_DIR.iterdir() if d.is_dir()]
    assert dirs == ["sess-A"], f"shadow files leaked outside their session dir: {dirs}"


def test_no_cut_when_the_shadow_cannot_be_written(lc_nokeep):
    lc_nokeep.SHADOW_MAX_MB = 0               # budget exhausted -> every write fails
    msgs = H.conversation([H.BIG + " tag=A", H.BIG + " tag=B", H.BIG + " tag=C"])
    projected, stats = lc_nokeep.project(msgs, session="t", seq=2)
    assert projected is None, "cut happened although the backup could not be written"
    assert stats["skips"].get("shadow_unwritable", 0) >= 1


def test_disabled_engine_is_a_passthrough(lc):
    lc.ENABLED = False
    msgs = H.conversation([H.BIG, H.BIG])
    projected, stats = lc.project(msgs, session="t", seq=1)
    assert projected is None and stats["skips"].get("disabled") == 1


def test_card_never_grows(lc_nokeep):
    """A card must be smaller than what it replaces, or the cut is refused."""
    lc_nokeep.CARD_RATIO = 0.0                # force every candidate to fail
    msgs = H.conversation([H.BIG, H.BIG])
    projected, stats = lc_nokeep.project(msgs, session="t", seq=1)
    assert projected is None and stats["skips"].get("card_too_big", 0) >= 1

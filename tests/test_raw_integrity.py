"""Data truth: what a card names must be what is actually on disk.

The 1.0.6 alignment claimed "raw tool output is persisted before it can be lost, with a
hash pointer". Until now the suite only asserted ``meta.is_file()`` — so a file whose
content no longer matched its own name, or a card naming a file that never landed, would
still pass. These tests check the claim instead of the existence.
"""
from __future__ import annotations

import hashlib
import json
import re

import _helpers as H

RAW_NAME_RE = re.compile(r"raw-[0-9a-f]{16}\.txt")


def _raw_files(lc):
    return sorted(p for p in lc.SHADOW_DIR.rglob("raw-*.txt") if p.is_file())


def _meta_of(path):
    return json.loads(path.with_suffix(".meta.json").read_text(encoding="utf-8"))


def test_raw_file_is_byte_identical_to_the_tool_output(lc_nokeep):
    """The file is the tool result itself — not a projection, not a summary."""
    msgs = H.conversation([H.BIG, H.CODE, H.BIG])
    lc_nokeep.project(msgs, session="truth", seq=1)
    files = _raw_files(lc_nokeep)
    assert files, "no raw tool output was persisted"
    originals = {H.BIG, H.CODE}
    for path in files:
        payload = path.read_bytes()
        assert payload.decode("utf-8") in originals, f"{path.name} is not a verbatim tool result"
        meta = _meta_of(path)
        assert meta["sha256"] == hashlib.sha256(payload).hexdigest(), f"{path.name} meta hash lies"
        assert meta["bytes"] == len(payload), f"{path.name} meta size lies"
        assert meta["name"] == "read_file"
        assert meta["turn"] in (1, 2, 3)


def test_raw_file_name_matches_its_own_content(lc_nokeep):
    """``raw-<sha16>.txt`` must be the hash OF THE FILE, or the name is not a pointer."""
    msgs = H.conversation([H.BIG, H.CODE])
    lc_nokeep.project(msgs, session="name", seq=1)
    files = _raw_files(lc_nokeep)
    assert files
    for path in files:
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        assert path.name == f"raw-{digest}.txt", f"{path.name} does not hash to its own content"


def test_card_never_names_a_file_that_is_not_on_disk(lc_nokeep):
    """A pointer the model cannot follow is worse than no pointer."""
    msgs = H.conversation([H.BIG, H.BIG, H.BIG])
    projected, stats = lc_nokeep.project(msgs, session="ptr", seq=1)
    assert projected is not None and stats["cuts"] >= 1
    cards = [m.get("content") or "" for m in projected if m.get("role") == "assistant"]
    names = set(RAW_NAME_RE.findall("\n".join(cards)))
    assert names, "cards carried no raw pointer even though tool output was dropped"
    on_disk = {p.name for p in lc_nokeep.SHADOW_DIR.rglob("raw-*.txt")}
    missing = names - on_disk
    assert not missing, f"cards point at files that were never written: {sorted(missing)}"


def test_a_corrupted_raw_file_is_repaired_not_trusted(lc_nokeep):
    """Content-addressed means re-usable — but only after checking it still holds."""
    msgs = H.conversation([H.BIG, H.BIG])
    lc_nokeep.project(msgs, session="corrupt", seq=1)
    path = _raw_files(lc_nokeep)[0]
    expected = hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_bytes(path.read_bytes()[:200])          # truncated, still non-empty
    lc_nokeep.project(msgs, session="corrupt", seq=2)  # same session, same content
    assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, (
        "a truncated raw file was silently reused: its name no longer matches its content"
    )


def test_shadow_backup_holds_the_prompt_text_not_the_card(lc_nokeep):
    """The backup exists to recover detail the card dropped, so it must be pre-projection."""
    msgs = H.conversation([H.BIG, H.BIG, H.BIG])
    projected, stats = lc_nokeep.project(msgs, session="shadow", seq=1)
    assert projected is not None and stats["cuts"] >= 1
    backups = [p for p in lc_nokeep.SHADOW_DIR.rglob("*.txt") if not p.name.startswith("raw-")]
    assert backups, "no cut-span backup was written"
    text = backups[0].read_text(encoding="utf-8")
    assert H.BIG.splitlines()[-1] in text, "the backup lost the tail of the original tool output"
    assert "工具输出已省略" not in text, "the backup contains the card, not the original"


def test_a_truncated_shadow_backup_is_repaired(lc_nokeep):
    """Same rule for the span backup: reuse only if it still holds the span."""
    msgs = H.conversation([H.BIG, H.BIG, H.BIG])
    lc_nokeep.project(msgs, session="shadowfix", seq=1)
    backups = [p for p in lc_nokeep.SHADOW_DIR.rglob("*.txt") if not p.name.startswith("raw-")]
    assert backups
    path = backups[0]
    expected = path.read_bytes()
    path.write_bytes(expected[:100])
    projected, stats = lc_nokeep.project(msgs, session="shadowfix", seq=2)
    assert projected is not None and stats["cuts"] >= 1
    assert path.read_bytes() == expected, "a truncated backup was reused as if it were the span"


def test_no_meta_sidecar_without_its_file(lc_nokeep):
    """The sidecar is written after the payload; an orphan would advertise a phantom."""
    msgs = H.conversation([H.BIG, H.CODE])
    lc_nokeep.project(msgs, session="sidecar", seq=1)
    metas = list(lc_nokeep.SHADOW_DIR.rglob("raw-*.meta.json"))
    assert metas, "no sidecar metadata was written at all"
    for meta in metas:
        payload = meta.with_name(meta.name[: -len(".meta.json")] + ".txt")
        assert payload.is_file() and payload.stat().st_size > 0, f"orphan sidecar {meta.name}"
        assert _meta_of(payload)["sha256"] == hashlib.sha256(payload.read_bytes()).hexdigest()


def test_raw_write_is_idempotent_and_stable(lc_nokeep):
    """Same text twice -> one file, one name, byte-identical (this is what keeps the cache)."""
    msgs = H.conversation([H.BIG])
    lc_nokeep.project(msgs, session="idem", seq=1)
    first = {p.name: p.read_bytes() for p in _raw_files(lc_nokeep)}
    lc_nokeep.project(msgs, session="idem", seq=2)
    second = {p.name: p.read_bytes() for p in _raw_files(lc_nokeep)}
    assert first and first == second, "the same tool output produced different raw files"

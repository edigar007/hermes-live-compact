"""Tool evidence: exit codes, failure excerpts, raw pointers.

1.0.6 tightened two things that were wrong in 0.2.0:

  * ``[exit code: 1]`` used to count anywhere in a tool result, so a note *mentioning* a
    failure was read as a failure of the current call. It only counts at the end now.
  * a long failing result lost its error lines to the "omitted, N chars" line. The head,
    the failure markers and the tail are now quoted (``fitFailure``).
"""
from __future__ import annotations

import _helpers as H


def test_exit_code_only_counts_at_the_end(lc):
    assert lc.exit_code("boom\n[exit code: 1]") == 1
    assert lc.exit_code("boom\n[exit code: 1]\n\n") == 1
    assert lc.exit_code("notes mention [exit code: 1] in the middle\nall good") is None
    assert lc.exit_code('{"output": "ok", "exit_code": 0}') == 0
    assert lc.exit_code('{"output": "boom", "exit_code": 2}') == 2
    assert lc.exit_code("plain text") is None


def test_failure_excerpt_keeps_head_markers_and_tail(lc):
    text = "\n".join(
        ["step 1 ok", "step 2 ok"] + [f"line {i} ok" for i in range(300)]
        + ["ERROR settle failed on ORD-1511", "ERROR unique constraint on settle_ledger", "final: aborted"]
    )
    excerpt = lc.failure_excerpt(text)
    assert excerpt.startswith("step 1 ok")
    assert "ERROR settle failed on ORD-1511" in excerpt
    assert "final: aborted" in excerpt
    assert len(excerpt.split("\n")) <= 2 + lc.FAIL_MARK_LINES + 2 + 2


def test_long_failing_result_keeps_its_error_line(lc):
    body = "\n".join(["boot"] + [f"ok {i}" for i in range(400)]
                     + ["FATAL cannot bind port 8092", "[exit code: 1]"])
    events = [{"name": "terminal", "text": body, "exit": lc.exit_code(body)}]
    text, _skipped, needs_backup = lc.tool_excerpt(events, "/tmp/x.txt", {0: "raw-abc.txt"}, 7)
    assert needs_backup is True
    assert "退出码 1" in text
    assert "FATAL cannot bind port 8092" in text
    assert "raw-abc.txt" in text


def test_evidence_line_per_tool_call(lc):
    events = [
        {"name": "read_file", "text": "ok", "exit": None},
        {"name": "terminal", "text": "boom\n[exit code: 2]", "exit": 2},
    ]
    lines = lc.evidence_lines(events, {0: "raw-a.txt", 1: "raw-b.txt"}, 4)
    assert lines[0] == "- 第4轮 `read_file` → raw-a.txt"
    assert lines[1] == "- 第4轮 `terminal` 失败（退出码 2） → raw-b.txt"


def test_evidence_skips_calls_without_a_raw_file(lc):
    events = [{"name": "read_file", "text": "ok", "exit": 0}]
    assert lc.evidence_lines(events, {}, 1) == []


def test_card_carries_evidence_and_pointer_for_a_cut_turn(lc_nokeep):
    msgs = H.conversation([H.BIG, H.BIG, H.BIG])
    projected, stats = lc_nokeep.project(msgs, session="t", seq=1)
    assert projected is not None
    cards = [m["content"] for m in projected
             if isinstance(m.get("content"), str) and m["content"].startswith("[压缩摘录]")]
    assert cards
    assert any("工具证据:" in card and "`read_file`" in card for card in cards)
    assert any("raw-" in card for card in cards)

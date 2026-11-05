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


def _turn_with_tool(tool_text):
    return [
        {"role": "user", "content": "看日志，把 ERROR 找出来。"},
        {"role": "assistant", "content": None,
         "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "read_file"}}]},
        {"role": "tool", "tool_call_id": "c1", "content": tool_text},
        {"role": "assistant", "content": "好了。"},
    ]


def test_tool_evidence_lines_are_kept_when_they_fit(lc):
    body = _turn_with_tool(
        "ERROR settle_ledger seq 9211 unique constraint\n"
        "ERROR settle_ledger seq 9212 unique constraint\n"
        + "\n".join(f"INFO line {i}" for i in range(30))
    )
    card = lc.build_card(body, "", "/tmp/x.txt")
    assert card["ok"] is True
    assert card["tool_claims"] > 0
    assert "settle_ledger seq 9211" in card["text"]


def test_log_failure_lines_are_claims(lc):
    """A timestamped ERROR line is a claim even though it does not start with ``Error:``."""
    assert lc.LOG_FAIL_RE.match("2026-11-04 09:12:57 ERROR settle worker=w1 order=ORD-1511")
    assert lc.LOG_FAIL_RE.match("[warn] WARNING disk almost full")
    assert not lc.LOG_FAIL_RE.match("我上一轮说过这里有个 ERROR，但已经修好了")
    body = _turn_with_tool(
        "2026-11-04 09:00:00 INFO  settle worker=w0 order=ORD-1300 status=ok\n"
        "2026-11-04 09:12:57 ERROR settle worker=w1 order=ORD-1511 status=fail\n"
        + "\n".join(f"2026-11-04 09:13:{i:02d} INFO  settle worker=w0 status=ok" for i in range(20))
    )
    card = lc.build_card(body, "", "/tmp/x.txt")
    assert card["ok"] is True
    assert "ERROR settle worker=w1 order=ORD-1511" in card["text"]


def test_near_duplicate_lines_are_capped(lc):
    """An 800-line log whose rows differ only in a number is one fact, not 800."""
    body = _turn_with_tool(
        "\n".join(f"2026-11-04 09:00:{i % 60:02d} INFO settle_ledger seq={9000 + i} status=ok"
                  for i in range(200))
    )
    card = lc.build_card(body, "", "/tmp/x.txt")
    assert card["ok"] is True
    assert card["tool_claims"] == 200, "every numbered row should match as a claim"
    assert card["kept"] <= 2, f"shape cap did not apply: kept {card['kept']} lines"
    assert card["deferred"] >= 190


def test_failure_lines_outrank_bulk_lines(lc):
    body = _turn_with_tool(
        "\n".join([f"2026-11-04 09:00:{i % 60:02d} INFO settle_ledger seq={9000 + i} status=ok"
                   for i in range(200)]
                  + ["2026-11-04 09:03:31 ERROR settle_ledger code=E211 detail=unique constraint seq 9211",
                     "2026-11-04 09:08:53 ERROR settle_ledger code=E533 detail=unique constraint seq 9533",
                     "2026-11-04 09:12:57 ERROR settle_ledger code=E777 detail=unique constraint seq 9777"])
    )
    card = lc.build_card(body, "", "/tmp/x.txt")
    text = card["text"]
    assert card["ok"] is True
    assert text.index("code=E211") < text.index("INFO settle_ledger"), "failures must come first"
    for code in ("E211", "E533", "E777"):
        assert code in text, f"{code} was crowded out of the card"


def test_huge_tool_output_does_not_block_the_cut(lc):
    """Tool lines are evidence, not instructions: those that do not fit are deferred, and
    the cut still happens because the raw file is on disk."""
    body = _turn_with_tool(
        "\n".join(f"ERROR settle_ledger seq {9000 + i} detail=unique constraint" for i in range(1200))
    )
    card = lc.build_card(body, "", "/tmp/x.txt")
    assert card["ok"] is True, "a bulky tool result must not veto the cut"
    assert card["missing"] == 0
    assert card["kept"] * 1 <= 8000  # budget respected

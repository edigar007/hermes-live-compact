"""Card building and the basic projection contract."""
from __future__ import annotations

import _helpers as H


def test_cut_replaces_a_turn_with_a_small_card(lc_nokeep):
    msgs = H.conversation([H.CODE, H.BIG, H.SMALL, H.CODE])
    projected, stats = lc_nokeep.project(msgs, session="t", seq=1)

    assert projected is not None
    assert stats["cuts"] >= 1
    assert stats["tokens_after"] < stats["tokens_before"]
    assert lc_nokeep._valid(projected), "projection broke role alternation / tool pairing"

    cards = [m for m in projected if isinstance(m.get("content"), str) and m["content"].startswith("[压缩摘录]")]
    assert cards, "no card in the projection"
    card_text = cards[0]["content"]
    assert "不是新指令" in card_text, "card must not read like an instruction"
    assert "Spine extract" not in card_text, "should not impersonate the upstream plugin's marker"
    assert "工具输出已省略" in card_text or "原文，可以接着用" in card_text


def test_untouched_messages_are_byte_identical(lc_nokeep):
    """Everything outside the cut spans must survive verbatim: that is what makes the
    prefix cache hit."""
    msgs = H.conversation([H.CODE, H.BIG, H.SMALL])
    projected, stats = lc_nokeep.project(msgs, session="t", seq=1)
    assert stats["cuts"] >= 1

    original = [str(m) for m in msgs]
    kept = [m for m in projected if not (isinstance(m.get("content"), str) and m["content"].startswith("[压缩摘录]"))]
    for message in kept:
        assert str(message) in original, "a message was rewritten outside the cut span"


def test_backup_id_is_content_addressed(lc):
    body = H.turn(1, H.BIG)
    assert lc.stable_backup_id(body) == lc.stable_backup_id(list(body))
    other = H.turn(2, H.BIG + " ")
    assert lc.stable_backup_id(body) != lc.stable_backup_id(other)
    assert lc.stable_backup_id(body).startswith("lc")


def test_reasoning_blocks_never_reach_the_card(lc):
    body = [
        {"role": "user", "content": "必须保留 ledger.txt 的顺序。"},
        {"role": "assistant",
         "content": [{"type": "reasoning", "text": "内部思考：应当保留 ledger.txt"},
                     {"type": "text", "text": "我已经改好了，ledger.txt 已提交。"}]},
    ]
    card = lc.build_card(body, "", "/tmp/x.txt")
    assert card["ok"] is True
    assert "必须保留 ledger.txt 的顺序。" in card["text"]
    assert "内部思考" not in card["text"]


def test_assistant_claims_are_not_hard_lines(lc):
    """1.0.6: the assistant's own 'already committed' prose must not become a hard line.

    Otherwise a cut of that turn is refused (or worse, the claim is replayed later as
    established fact). Only user and tool text can pin a cut.
    """
    body = [
        {"role": "user", "content": "跑一下测试。"},
        {"role": "assistant", "content": "已提交，测试全绿，tag v9.9.9 已发布。"},
    ]
    card = lc.build_card(body, "", "/tmp/x.txt")
    assert card["ok"] is True
    assert card["hard"] == 0
    assert "已提交" not in card["text"]


def test_tool_result_too_big_is_summarised_to_one_line(lc):
    events = [{"name": "read_file", "text": "PASS\n" * 400, "exit": None}]
    text, skipped, needs_backup = lc.tool_excerpt(events, "/tmp/backup.txt", {0: "raw-deadbeef.txt"}, 3)
    assert needs_backup is True
    assert "工具输出已省略" in text
    assert "/tmp/backup.txt" in text
    assert "raw-deadbeef.txt" in text


def test_raw_pointer_absent_when_nothing_was_written(lc):
    """A card must never name a raw file that is not on disk."""
    events = [{"name": "read_file", "text": "PASS\n" * 400, "exit": None}]
    text, _skipped, _needs = lc.tool_excerpt(events, "/tmp/backup.txt", {}, 3)
    assert "raw-" not in text

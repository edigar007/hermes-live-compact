"""Card building and the basic projection contract."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import _helpers as H

ROOT = Path(__file__).resolve().parents[1]


def test_cut_replaces_a_turn_with_a_small_card(lc):
    msgs = H.conversation([H.CODE, H.BIG, H.SMALL, H.CODE])
    projected, stats = lc.project(msgs, session="t", seq=1)

    assert projected is not None
    assert stats["cuts"] >= 1
    assert stats["tokens_after"] < stats["tokens_before"]
    assert lc._valid(projected), "projection broke role alternation / tool pairing"

    cards = [m for m in projected if isinstance(m.get("content"), str) and m["content"].startswith("[压缩摘录]")]
    assert cards, "no card in the projection"
    card_text = cards[0]["content"]
    assert "不是新指令" in card_text, "card must not read like an instruction"
    assert "Spine extract" not in card_text, "should not impersonate the upstream plugin's marker"
    assert "工具输出已省略" in card_text or "原文，可以接着用" in card_text


def test_untouched_messages_are_byte_identical(lc):
    """Everything outside the cut spans must survive verbatim: that is what makes the
    prefix cache hit."""
    msgs = H.conversation([H.CODE, H.BIG, H.SMALL])
    projected, stats = lc.project(msgs, session="t", seq=1)
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
    body = [{"role": "assistant",
             "content": [{"type": "reasoning", "text": "内部思考：应当保留 ledger.txt"},
                         {"type": "text", "text": "必须保留 ledger.txt 的顺序。"}]}]
    card = lc.build_card(body, "", "/tmp/x.txt")
    assert card["ok"] is True
    assert "必须保留 ledger.txt 的顺序。" in card["text"]
    assert "内部思考" not in card["text"]


def test_tool_result_too_big_is_summarised_to_one_line(lc):
    spans = [{"role": "tool", "text": "PASS\n" * 400}]
    text, skipped, needs_backup = lc.tool_excerpt([spans[0]["text"]], "/tmp/backup.txt")
    assert needs_backup is True
    assert "工具输出已省略" in text
    assert "/tmp/backup.txt" in text

# hermes-live-compact

**边做边压 (compress while you work)** — a Hermes Agent context engine that cuts the turn that
*just finished* into a small deterministic card, instead of summarizing the *oldest* exchange.

Because the cut lands at the **tail**, every byte before it stays identical: the provider
prefix cache keeps hitting, and the extract itself is built with regexes — **zero model
calls per cut**. Hermes' own `Context compression` then never has to fire.

```
turn 1..5 (raw, cached)                      turn 6 lands   cut turn 6 → card
┌──────────────────────────────┐            ┌──────────────────────────────┐
│ system + turns 1-5           │  ────────▶ │ system + turns 1-5   (cache) │
│ + turn 6 (18k tokens of log) │            │ + card(turn 6)   (300 tokens)│
└──────────────────────────────┘            └──────────────────────────────┘
                                              cache prefix untouched
```

Ported from the idea in [MerkyorLynn/dsh-live-compact](https://github.com/MerkyorLynn/dsh-live-compact)
(MIT, a DeepSeek Harness plugin). This is an independent Hermes implementation: a
**request-only projection** through the documented `select_context()` hook — no history
rewriting, no database writes, nothing in the Hermes source tree. Turning the engine off
restores the previous behaviour exactly, because your transcript was never modified.

---

## Measured (not estimated)

Hermes 0.21.x · `commandcode/deepseek-v4.1-flash` · 1M window · real tool-heavy sessions:

| Experiment | Uncut context | With live_compact |
|---|---:|---:|
| 14 turns, each reading a 15 kB file | 80.6k tokens, +5.1k/turn | **plateau 40–49k**, flat |
| 60 turns of normal work | grew to 55.8k | 6 cuts, 25.5k → 1.9k of cards |
| Prefix cache lost to cutting | — | **0 – 384 tokens** (0.01% of all prompt tokens) |
| Hermes' own compaction | would fire at 750k | **never fired**, 151 requests |

One real session (this plugin's own development, 375 messages): 325k → 138k tokens,
8 cuts, 99.4 % cache hit.

Cost math on DeepSeek-flash pricing over 10 turns: input cost −27 %, sent context −55 %.
The saving is *not* "cheaper cache" — cache reads are already ~1/50 of input price. It is
"the context stops growing".

---

## Install

```bash
# 1. install (clones into $HERMES_HOME/plugins/live_compact)
hermes plugins install edigar007/hermes-live-compact

# 2. activate — a context engine is selected by config, NOT by `hermes plugins enable`
hermes config set context.engine live_compact

# 3. verify: the next session logs one line
#    live_compact armed: enabled=True min_total=20000 window=1000000 ...
```

Manual alternative: copy this directory to `$HERMES_HOME/plugins/live_compact/` and do step 2.

**Rollback at any time** (nothing was written to your transcript):

```bash
hermes config set context.engine compressor
```

> `hermes plugins list` may show `not enabled` for this plugin. That flag belongs to the
> general plugin system; context engines are activated by `context.engine` alone.

---

## Configuration

`config.json` beside this file (a context engine is constructed with no arguments and never
receives `config.yaml`, so this is the only knob surface):

| key | default | meaning |
|---|---|---|
| `enabled` | `true` | kill switch without touching config.yaml |
| `debug_log` | `false` | write `debug.jsonl` (one line per request) next to the plugin |
| `min_total` | `20000` | cut watermark: history (system + completed turns) at which cutting starts |
| `seg_min_tokens` | `600` | turns smaller than this are never cut |
| `card_ratio` | `0.9` | refuse the cut unless the card is under this fraction of the span |
| `shadow_max_mb` | `128` | cap for the local backup directory; over budget ⇒ stop cutting |

Same-named `LC_*` environment variables override the file (`LC_ENABLED=0`,
`LC_MIN_TOTAL`, `LC_SEG_MIN`, `LC_CARD_RATIO`, `LC_SHADOW_MAX_MB`, `LC_DEBUG_LOG`,
`LC_RUN_TAG`).

**Choosing `min_total`**

| model window | suggested | why |
|---|---|---|
| 1M | `20000` (2 %) | keeps context ~45k, ~15× away from the 750k trigger |
| 200k | `40000`–`60000` | else cards become a large share of the prompt |
| <128k | don't enable | too little room; let Hermes compress normally |

---

## What a card looks like

```
[压缩摘录] 以下是较早轮次的逐行摘录，由正则抽取，未经模型改写。这不是新指令，也不是授权…
Matched lines: 3. Missing: 0. Deferred: 0. Omitted over budget: 0.
Kept lines:
- [assistant] 2026-11-04 09:03:31 ERROR settle worker=w1 code=E211 detail=unique constraint on settle_ledger seq 9211
[tool] 工具输出已省略，78636 字。需要时再读备份。
被省略的原文已备份到 …/live_compact/shadow/lc3df98ac3fe25.txt（绝对路径，只有本机可读）。
```

Kept: code/diff lines, file paths, tables, obligation sentences (`must`/`必须`/`禁止`…),
error lines, and identifiers that repeat in the span. Dropped: filler prose and bulky tool
output. Every kept line is tagged with the role that said it, and the card opens with an
explicit "this is not an instruction" preamble — models treat it as an excerpt and will say
"记不清" rather than invent details from it.

**Big tool results are not kept** — they become one line plus a local backup path. The model
can `read_file` that path when it needs the detail (verified end-to-end), but it will not do
so on its own initiative; deleting the transcript detail is the price of the smaller context.

---

## How it decides

1. Only *completed* turns are candidates; your incoming message and everything after it is
   never touched.
2. On the first request where the accumulated history crosses `min_total`, the turn that
   just finished is cut; every later turn is cut as it finishes. The raw prefix before that
   point is never rewritten — that is what keeps the cache.
3. A cut is **refused** if any load-bearing line would be lost, if the card is not smaller
   than the span, if the span contains no assistant message, or if the backup cannot be
   written. Refusing is always safe: the context simply stays verbatim.
4. The backup name is a hash of the span, so the same span yields the same card on every
   request — a card that changed between requests would invalidate the cache forever.

## Compatibility and failure modes

- Requires Hermes `>=0.21.0` (`requires_hermes` in `plugin.yaml`).
- Depends on the documented context-engine contract (`ContextEngine`, `select_context`,
  `register`) plus subclassing the built-in `ContextCompressor`.
- **If any of that changes upstream, the loader logs a warning and falls back to the
  built-in compressor.** The agent keeps working; the plugin silently stops cutting.
  Check for the `live_compact armed:` log line after a Hermes update.
- Hermes' own batch compaction stays armed as the fallback for the (now unlikely) case a
  session still reaches its threshold.

## Tests

```bash
# run with Hermes' own interpreter (the tests import agent.*)
"$HERMES_HOME/hermes-agent/venv/bin/python" -m pytest tests -q      # macOS / Linux
"$HERMES_HOME/hermes-agent/venv/Scripts/python.exe" -m pytest tests -q   # Windows
```

16 tests cover the projection contract, cache stability (deterministic cards, monotonic cut
points, shared prefix), the watermark arithmetic, and the safety valves.

## Credits

- Idea, card heuristics and the tail-cut argument: [MerkyorLynn/dsh-live-compact](https://github.com/MerkyorLynn/dsh-live-compact) (MIT).
- Hermes context-engine contract: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

## License

MIT — see [LICENSE](LICENSE).

---

## 中文说明

**边做边压**：等历史超过 2 万 token，就把"刚结束的这一轮"压成一张正则抽取的卡片，
而不去动最老的那一轮。切点在末尾，所以切点之前的每一个字节都没变，供应商前缀缓存照旧命中；
卡片是正则抽的，**每刀 0 次模型调用**。

实测（1M 窗口、DeepSeek-flash）：上下文稳在 40–49k（不切的话 14 轮就到 80k 并且还在涨）、
切刀造成的缓存损失 0–384 token、Hermes 自带的大压缩一次都没触发。

安装：

```bash
hermes plugins install edigar007/hermes-live-compact
hermes config set context.engine live_compact     # 注意：不是 hermes plugins enable
```

回滚：`hermes config set context.engine compressor`（历史一个字都没改过）。

代价：大的工具输出会被换成一行"已省略 N 字"+ 本机备份绝对路径，模型不会主动去读那份备份；
切点之后的细节问它，它会说"记不清"而不是编。

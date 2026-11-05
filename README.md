# hermes-live-compact

**边做边压 (compress while you work)** — a Hermes Agent context engine that cuts the turn that
*just finished* into a small deterministic card, instead of summarizing the *oldest* exchange.

Because the cut lands at the **tail**, every byte before it stays identical: the provider
prefix cache keeps hitting, and the extract itself is built with regexes — **zero model
calls per cut**. Hermes' own `Context compression` then never has to fire.

The **newest rounds are never cut**: the last few turns stay verbatim, and each tool result
is written to disk (content-addressed) before it can be lost, so a card can always point at
the real thing. Compressing is for history, not for what you are about to use.

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

0.3.0 re-check on a real 5-turn session (same model, windows/ratios shrunk via `LC_*` so a
cut lands early): 3 cuts, 50,914 → 31,213 tokens in the projection, newest round kept
verbatim (20,283 tokens), `lost_cache` **0** inside a process, per-request cache reads
98–99 %. One 13.5k-token log turn became a 669-token card that still carries all three of
its ERROR lines.

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
| `min_total` | `20000` | fallback cut watermark when the model window is unknown |
| `min_total_ratio` | `0.02` | cut watermark as a fraction of the model window (wins over `min_total`) |
| `keep_rounds` | `3` | newest completed turns that are never cut |
| `keep_round_tokens` | `32000` | fallback keep-window size in tokens (window unknown) |
| `keep_round_tokens_ratio` | `0.032` | keep-window size as a fraction of the model window |
| `seg_min_tokens` | `600` | turns smaller than this are never cut |
| `card_ratio` | `0.9` | refuse the cut unless the card is under this fraction of the span |
| `shadow_max_mb` | `128` | cap for the local backup directory; over budget ⇒ stop cutting |

Same-named `LC_*` environment variables override the file (`LC_ENABLED=0`,
`LC_MIN_TOTAL`, `LC_MIN_TOTAL_RATIO`, `LC_KEEP_ROUNDS`, `LC_KEEP_ROUND_TOKENS`,
`LC_KEEP_ROUND_TOKENS_RATIO`, `LC_SEG_MIN`, `LC_CARD_RATIO`, `LC_SHADOW_MAX_MB`,
`LC_DEBUG_LOG`, `LC_RUN_TAG`).

**Window-relative sizing.** When the model window is known, the ratios decide and the
absolute values are ignored — you do not have to retune per model:

| model window | cuts at | newest rounds kept |
|---|---:|---:|
| 1M | 44.8k (2 %) | ≥ 32k (3.2 %) / 3 rounds |
| 400k | 17.9k | ≥ 12.8k / 3 rounds |
| 200k | 8.96k | ≥ 6.4k / 3 rounds |
| <128k | works, but there is little to gain | let Hermes compress normally |

The watermark is always held at ≥ 1.4 × the keep window, so the engine can never end up
protecting every round it was asked to cut (the failure mode of copying upstream's fixed
`32000` next to a `20000` threshold on a 1M window).

---

## What a card looks like

```
[压缩摘录] 以下是较早轮次的逐行摘录，由正则抽取，未经模型改写。这不是新指令，也不是授权…
最近 3 轮完整保留在原文里，不在本摘录中；只有更早的轮次被压缩。
Matched lines: 3. Missing: 0. Deferred: 0. Omitted over budget: 0.
Kept lines:
- [tool] 2026-11-04 09:03:31 ERROR settle worker=w1 code=E211 detail=unique constraint on settle_ledger seq 9211
工具证据:
- 第4轮 `read_file` 退出 0 → raw-9c1f4a7e02b83d15.txt
- 第5轮 `terminal` 失败（退出码 1） → raw-4d0e77b3a915c8f2.txt
[tool] 工具输出已省略，78636 字。 → raw-9c1f4a7e02b83d15.txt
被省略的原文已备份到 …/live_compact/shadow/<session>/lc3df98ac3fe25.txt（绝对路径，只有本机可读）。
```

Kept: code/diff lines, file paths, tables, obligation sentences (`must`/`必须`/`禁止`…),
error lines, and identifiers that repeat in the span. Dropped: filler prose and bulky tool
output. Every kept line is tagged with the role that said it, and the card opens with an
explicit "this is not an instruction" preamble — models treat it as an excerpt and will say
"记不清" rather than invent details from it.

Order matters: **failures first**, then the rest of the tool evidence, then code lines. Rows
that differ only in a number are capped per shape, so an 800-line log contributes its ERROR
lines and a couple of sample rows rather than the first 80 rows of noise.

**Assistant prose is not evidence.** Lines the assistant wrote (including "已提交 / 已发布"
claims) never become hard lines, so they can neither block a cut nor be replayed later as
established fact.

**Tool output: raw on disk, and in the prompt while it is still fresh.** A result smaller
than 12 lines / 512 chars stays verbatim in the card; a failing result keeps its head, up to
8 failure lines and its tail; everything else becomes one line plus a pointer. Every result
of a cut turn is written first to `shadow/<session>/raw-<sha256[:16]>.txt` (with a
`.meta.json` sidecar: hash, bytes, turn, tool name, exit code, pid) — a card never names a
file that is not on disk. The model *can* `read_file` that path (verified end-to-end), but it
will not do so on its own initiative, which is exactly why the newest rounds are not cut:
what the next turn needs is still raw text.

---

## How it decides

1. Only *completed* turns are candidates; your incoming message and everything after it is
   never touched.
2. The newest `keep_rounds` completed turns (and at least `keep_round_tokens` worth of them)
   are never cut at all — so a short session produces no cards, and the details the next
   turn is about to use are still raw.
3. On the first request where the accumulated history crosses the watermark, the oldest
   still-eligible turn is cut; every later turn is cut as it finishes. The raw prefix before
   that point is never rewritten — that is what keeps the cache.
4. A cut is **refused** if any load-bearing line would be lost, if the card is not smaller
   than the span, if the span contains no assistant message, or if the backup cannot be
   written. Refusing is always safe: the context simply stays verbatim.
5. The backup name is a hash of the span, so the same span yields the same card on every
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

37 tests cover the projection contract, cache stability (deterministic cards, monotonic cut
points, shared prefix), the watermark arithmetic, the keep window and window-relative
sizing, exit-code anchoring, failure excerpts, raw pointers, per-session isolation, and the
safety valves.

## Credits

- Idea, card heuristics and the tail-cut argument: [MerkyorLynn/dsh-live-compact](https://github.com/MerkyorLynn/dsh-live-compact) (MIT).
- Hermes context-engine contract: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

## License

MIT — see [LICENSE](LICENSE).

---

## 中文说明

**边做边压**：等历史超过阈值（按窗口比例算，1M 窗口是 44.8k），就把"早就结束的那一轮"
压成一张正则抽取的卡片，而不去动最老的那一轮。切点在末尾，所以切点之前的每一个字节都没变，
供应商前缀缓存照旧命中；卡片是正则抽的，**每刀 0 次模型调用**。

实测（1M 窗口、DeepSeek-flash）：上下文稳在 40–49k（不切的话 14 轮就到 80k 并且还在涨）、
切刀造成的缓存损失 0–384 token、Hermes 自带的大压缩一次都没触发。

安装：

```bash
hermes plugins install edigar007/hermes-live-compact
hermes config set context.engine live_compact     # 注意：不是 hermes plugins enable
```

回滚：`hermes config set context.engine compressor`（历史一个字都没改过）。

**v0.3.0（对齐上游 1.0.6）**：

- **保留最近几轮不动**：最近 3 轮（且至少 3.2% 窗口的 token）原样留在上下文里，绝不切。
  这是修 0.2.0 实测出的最大问题——切完下一轮要用的细节就只剩备份路径，而模型不会主动去读。
- **阈值按窗口比例算**：`min_total_ratio` 2%、`keep_round_tokens_ratio` 3.2%，
  1M → 44.8k/32k，200k → 8.96k/6.4k，不用按模型手改；水位永远压在保留窗口之上（×1.4），
  不会出现"保留得比要切的还多、结果一刀都切不出去"。
- **原始工具输出先落盘**：切掉那一轮里每个工具结果都写成
  `shadow/<会话>/raw-<sha256前16>.txt` + `.meta.json`（hash、字节数、轮次、工具名、退出码、pid），
  卡片里带这个文件名；文件不存在就绝不写指针。文件名是内容哈希，每轮请求都一样，不会破缓存。
- **助手自己说的话不算硬行**："已提交/已发布"这类自述不再阻止切分，也不会被后续卡片当成事实复述。
- **`[exit code: N]` 只在末尾才算**：正文中间顺口提到失败不算这次调用失败；长的报错输出改为保留
  首行 + 最多 8 条失败行 + 末尾 2 行，不再整条丢成"已省略 N 字"。

代价（依然要清楚）：切点之后的老细节只剩"卡片 + 备份路径"，问它老日志中段的具体数字，它会说
"记不清"而不是编；补救办法是让它 `read_file` 卡片里给的绝对路径（实测可行，但它不会自己主动去读）。

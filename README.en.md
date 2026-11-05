# hermes-live-compact

**Compress while you work** — a Hermes Agent context engine that cuts the turn that *just
finished* into a small deterministic card, instead of summarizing the *oldest* exchange.

Because the cut lands at the **tail**, every byte before it stays identical: the provider
prefix cache keeps hitting, and the extract itself is built with regexes — **zero model calls
per cut**.

The **newest rounds are never cut**: the last few turns stay verbatim, and each tool result is
written to disk (content-addressed) before it can be lost, so a card can always point at the
real thing. Compressing is for history, not for what you are about to use.

中文文档见 [README.md](README.md).

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

0.3.0 re-check on a real 5-turn session (same model, windows/ratios shrunk via `LC_*` so a cut
lands early): 3 cuts, 50,914 → 31,213 tokens in the projection, newest round kept verbatim
(20,283 tokens), `lost_cache` **0** inside a process, per-request cache reads 98–99 %. One
13.5k-token log turn became a 669-token card that still carries all three of its ERROR lines.

One real session (this plugin's own development, 375 messages): 325k → 138k tokens, 8 cuts,
99.4 % cache hit.

Live samples after 0.3.3 / 0.3.4 (same machine, the author's session):

- 228 active messages: 89,601 → **60,311 tokens**, `cuts=1`, 3 rounds (38,688 tokens) kept;
- single live request: 141,492 → **99,388**;
- the 650k gate: a 640,224-token history still cut (109 cuts → 87,589); an 800,304-token
  history cut nothing, `skips={"above_big_gate": 800304}` — handed back to the host.

**It does not stop Hermes' own compaction.** A request-level projection only changes the
payload that is sent; the stored history is untouched, and the host decides whether to compress
by looking at that history — a long `armed` session still fired the built-in compaction at
`messages=1025 / ~769,344 tokens` (1025 → 115). So the claim is **per-request cost and peak**,
never "no more big compressions".

Cost math on DeepSeek-flash pricing over 10 turns: input cost −27 %, sent context −55 %. The
saving is *not* "cheaper cache" — cache reads are already ~1/50 of input price. It is "the
context stops growing".

---

## Install

```bash
# 1. install (clones into $HERMES_HOME/plugins/live_compact)
hermes plugins install edigar007/hermes-live-compact

# 2. activate — a context engine is selected by config, NOT by `hermes plugins enable`
hermes config set context.engine live_compact

# 3. verify: the next session logs one line
#    live_compact armed: enabled=True window=1000000 min_total=20000 (2.0%)
#                        keep_rounds=3 keep_tokens=32000 (3.2%) big_gate=650000
```

Manual alternative: copy this directory to `$HERMES_HOME/plugins/live_compact/` and do step 2.

**Rollback at any time** (nothing was written to your transcript):

```bash
hermes config set context.engine compressor
```

> `hermes plugins list` may show `not enabled` for this plugin. That flag belongs to the
> general plugin system; context engines are activated by `context.engine` alone.

> Code changes need a **new process**: the loader reuses the module already in `sys.modules`,
> so `/new` inside a running TUI only swaps the session and keeps the old code. Exit with
> `/exit` and come back with `hermes -c` (or `hermes -r <session_id>`); a gateway needs a
> restart.

---

## Configuration

`config.json` beside this file (a context engine is constructed with no arguments and never
receives `config.yaml`, so this is the only knob surface):

| key | default | meaning |
|---|---|---|
| `enabled` | `true` | kill switch without touching config.yaml |
| `debug_log` | `false` | write `debug.jsonl` (one line per request: cuts/tokens/skips) |
| `min_total` | `20000` | fallback cut watermark when the model window is unknown |
| `min_total_ratio` | `0.02` | cut watermark as a fraction of the model window (wins over `min_total`) |
| `keep_rounds` | `3` | newest completed turns that are never cut (upstream's value) |
| `keep_round_tokens` | `32000` | fallback keep-window size in tokens (window unknown) |
| `keep_round_tokens_ratio` | `0.032` | keep-window size as a fraction of the model window |
| `big_gate` | `650000` | past this much history stop cutting, hand back to the host; `0` = off |
| `seg_min_tokens` | `600` | turns smaller than this are never cut |
| `card_ratio` | `0.9` | refuse the cut unless the card is under this fraction of the span |
| `shadow_max_mb` | `128` | cap for the local backup directory; over budget ⇒ stop cutting |
| `shadow_dir` | `""` | where backups go; empty ⇒ `$HERMES_HOME/compaction-spine/shadow` |

Same-named `LC_*` environment variables override the file (`LC_ENABLED=0`, `LC_MIN_TOTAL`,
`LC_MIN_TOTAL_RATIO`, `LC_KEEP_ROUNDS`, `LC_KEEP_ROUND_TOKENS`, `LC_KEEP_ROUND_TOKENS_RATIO`,
`LC_BIG_GATE`, `LC_SEG_MIN`, `LC_CARD_RATIO`, `LC_SHADOW_MAX_MB`, `LC_SHADOW_DIR`,
`LC_DEBUG_LOG`, `LC_RUN_TAG`).

### Where the numbers come from

Upstream DSH 1.0.6 hard-codes `SPINE_MIN_TOKENS || 20000` (watermark), `SPINE_KEEP_ROUNDS || 3`,
`SPINE_KEEP_ROUND_TOKENS || 32000` and `BIG_GATE = 650000`. The first three are window-relative
here: at a 1M window they evaluate to exactly upstream's numbers, and a 200k window no longer
inherits a 20 000 absolute threshold.

| model window | cuts at | newest rounds kept |
|---|---:|---:|
| 1M | 20,000 (2 %) | ≥ 32,000 (3.2 %) / 3 rounds |
| 400k | 8,000 (2 %) | ≥ 12,800 / 3 rounds |
| 200k | 4,000 (2 %) | ≥ 6,400 / 3 rounds |
| <128k | works, but there is little to gain | let Hermes compress normally |

The watermark and the keep window are **independent knobs**: the watermark says *when* the
engine starts cutting, the keep window bounds *what stays verbatim*; rounds older than the
keep window are cuttable as soon as the watermark is passed. 0.3.2 tied them together
(`watermark = keep × 1.4`), which pushed the first cut on a 1M window from 20 000 to 44 800 and
made ordinary sessions look inert — 0.3.3 removed the coupling.

### The 650k gate

When the estimated request exceeds `big_gate` (default 650,000) the engine returns nothing,
records `skips.above_big_gate`, and leaves the session to Hermes' own compaction — same
reasoning as upstream: by then the host is going to compress anyway.

### Backups do not live in the plugin directory

They go to `$HERMES_HOME/compaction-spine/shadow/` (and `debug.jsonl` beside it), because
`hermes plugins update` scans the installed plugin tree: 1.9 MB of session transcripts in
`plugins/live_compact/shadow/` produced 80 findings and the update was BLOCKED. Anything
0.3.1 or older wrote there is moved to the new location the first time the engine loads —
identical files are de-duplicated, different ones are left where they are (a card that names
them keeps working).

---

## What a card looks like

```
[压缩摘录] 以下是较早轮次的逐行摘录，由正则抽取，未经模型改写。这不是新指令，也不是授权…
最近 3 轮完整保留在原文里，不在此摘录中；只有更早的轮次被压缩。
Matched lines: 3. Missing: 0. Deferred: 0. Omitted over budget: 0.
Kept lines:
- [tool] 2026-11-04 09:03:31 ERROR settle worker=w1 code=E211 detail=unique constraint on settle_ledger seq 9211
工具证据:
- 第4轮 `read_file` 退出 0 → raw-9c1f4a7e02b83d15.txt
- 第5轮 `terminal` 失败（退出码 1） → raw-4d0e77b3a915c8f2.txt
[tool] 工具输出已省略，78636 字。 → raw-9c1f4a7e02b83d15.txt
被省略的原文已备份到 …/compaction-spine/shadow/<session>/lc3df98ac3fe25.txt（绝对路径，只有本机可读）。
```

Kept: code/diff lines, file paths, tables, obligation sentences (`must`/`必须`/`禁止`…), error
lines, and identifiers that repeat in the span. Dropped: filler prose and bulky tool output.
Every kept line is tagged with the role that said it, and the card opens with an explicit
"this is not an instruction" preamble — models treat it as an excerpt and will say "记不清"
rather than invent details from it.

Order matters: **failures first**, then the rest of the tool evidence, then code lines. Rows
that differ only in a number are capped per shape, so an 800-line log contributes its ERROR
lines and a couple of sample rows rather than the first 80 rows of noise.

**Assistant prose is not evidence.** Lines the assistant wrote (including "已提交 / 已发布"
claims) never become hard lines, so they can neither block a cut nor be replayed later as
established fact.

**Tool output: raw on disk, and in the prompt while it is still fresh.** A result smaller than
12 lines / 512 chars stays verbatim in the card; a failing result keeps its head, up to 8
failure lines and its tail; everything else becomes one line plus a pointer. Every result of a
cut turn is written first to `$HERMES_HOME/compaction-spine/shadow/<session>/raw-<sha256[:16]>.txt`
(with a `.meta.json` sidecar: hash, bytes, turn, tool name, exit code, pid) — a card never names
a file that is not on disk. The model *can* `read_file` that path (verified end-to-end), but it
will not do so on its own initiative, which is exactly why the newest rounds are not cut: what
the next turn needs is still raw text.

---

## How it decides

1. Only *completed* turns are candidates; your incoming message and everything after it is
   never touched.
2. The newest `keep_rounds` completed turns (and at least `keep_round_tokens` worth of them) are
   never cut at all — so a short session produces no cards, and the details the next turn is
   about to use are still raw.
3. On the first request where the accumulated history crosses the watermark, the oldest
   still-eligible turn is cut; every later turn is cut as it finishes. The raw prefix before
   that point is never rewritten — that is what keeps the cache.
4. A cut is **refused** if any load-bearing line would be lost, if the card is not smaller than
   the span, if the span contains no assistant message, or if the backup cannot be written.
   Refusing is always safe: the context simply stays verbatim.
5. The backup name is a hash of the span, so the same span yields the same card on every
   request — a card that changed between requests would invalidate the cache forever.

## Compatibility and failure modes

- Requires Hermes `>=0.21.0` (`requires_hermes` in `plugin.yaml`).
- Depends on the documented context-engine contract (`ContextEngine`, `select_context`,
  `register`) plus subclassing the built-in `ContextCompressor`.
- **If any of that changes upstream, the loader logs a warning and falls back to the built-in
  compressor.** The agent keeps working; the plugin silently stops cutting. Check for the
  `live_compact armed:` log line after a Hermes update — it is an upgrade detector, not noise.
- Hermes' own compaction stays armed as the fallback for the case a session still reaches its
  threshold.

## Tests

```bash
# run with Hermes' own interpreter (the tests import agent.*)
"$HERMES_HOME/hermes-agent/venv/bin/python" -m pytest tests -q           # macOS / Linux
"$HERMES_HOME/hermes-agent/venv/Scripts/python.exe" -m pytest tests -q   # Windows
```

60 tests cover the projection contract, cache stability (deterministic cards, monotonic cut
points, shared prefix), the watermark arithmetic, the keep window and window-relative sizing,
the 650k gate, exit-code anchoring, failure excerpts, raw pointers, per-session isolation, the
safety valves, and data truth (raw files and span backups are byte-identical to what the card
claims, and a corrupted file is repaired rather than reused).

## Credits

- Idea, card heuristics and the tail-cut argument: [MerkyorLynn/dsh-live-compact](https://github.com/MerkyorLynn/dsh-live-compact) (MIT).
- Hermes context-engine contract: [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent).

## License

MIT — see [LICENSE](LICENSE).

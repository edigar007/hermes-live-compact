# Changelog

## 0.3.0 — port of upstream 1.0.6's four fixes

Upstream (dsh-live-compact 1.0.6) fixed exactly the four things this port was weakest at.
Behaviour change: **the newest rounds are no longer cut**, so a session needs more history
before the first card appears — that is the point, not a regression.

- **Keep window.** The newest `keep_rounds` completed turns (default 3) stay verbatim, and
  if they are smaller than `keep_round_tokens` the window grows backwards until it is big
  enough. Fixes the measured 0.2.0 failure: after a cut, the details the very next turn
  needed were only in a backup, and the model would not go read it on its own.
- **Sizing is window-relative.** `min_total_ratio` (2%) and `keep_round_tokens_ratio`
  (3.2%) replace fixed counts whenever the model window is known: 1M → cut at 44.8k / keep
  32k, 200k → 8.96k / 6.4k. The watermark is always held above the keep window (×1.4), so
  the engine can never end up protecting everything it was asked to cut.
- **Raw tool output on disk, with a hash in the card.** Every tool result of a cut turn is
  written to `shadow/<session>/raw-<sha256[:16]>.txt` with a `.meta.json` sidecar (hash,
  bytes, turn, tool name, exit code, pid) before it can be lost, and the card names it.
  Content-addressed, so the name is identical on every request and cannot break the cache.
- **Assistant prose is not evidence.** The assistant's own "already committed / published"
  lines no longer count as hard lines: they cannot block a cut, and they are not replayed
  as fact in a later card.
- **`[exit code: N]` only counts at the END** of a tool result (a note *mentioning* a
  failure no longer marks the call as failed). Long failing results now keep their head,
  up to 8 failure-marker lines and their tail instead of collapsing to "omitted".
- **Per-session shadow directories** (`shadow/<session>/`), so rotating one session's
  backups can never touch another session that is still running.
- 32 tests (up from 16): keep-window arithmetic, window-relative sizing, exit-code
  anchoring, failure excerpts, evidence lines, raw pointers, per-session isolation.

## 0.2.0 — first public release

- Tail-first cut: the turn that just finished is replaced by a deterministic card, so the
  prefix cache survives (`lost_cache` 0–384 tokens over 151 measured requests).
- Cards keep code/paths/tables/obligations/error lines/repeated identifiers, tag every kept
  line with its source role, and open with a "not an instruction" preamble.
- Safety valves: refuse the cut when a load-bearing line would be lost, when the card is not
  smaller than the span, or when the local backup cannot be written.
- Backups are content-addressed (a stable name across requests) and carry their absolute
  path in the card so the model can read the original back.
- `config.json` for tuning; `debug_log` is off by default.
- 16 tests: projection contract, cache stability, watermark arithmetic, safety valves.
- Importable outside a Hermes process (tooling/test collectors); refuses to run there.

## 0.1.0 — internal proof of concept

- Request-level projection via `select_context()`, measured on 74 turns / 151 requests.

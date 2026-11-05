# Changelog

## 0.3.2 — the backups blocked their own upgrade

`hermes plugins update live_compact` came back **BLOCKED**: the security scan over the
installed plugin tree reported 80 findings, all of them session transcripts in
`plugins/live_compact/shadow/` (~1.9 MB). The engine's own data was blocking the engine's
own update — the fix is not a scan exception, it is putting user data where user data goes.

- **Backups (and `debug.jsonl`) move to `$HERMES_HOME/compaction-spine/`** instead of the
  plugin directory. Overridable with `config.json` → `shadow_dir` or `LC_SHADOW_DIR`.
- **One-time migration on first load**: files written by <=0.3.1 are moved to the new root;
  identical bytes are de-duplicated, different bytes are left in place so a card that names
  them still resolves. Only then is the legacy directory removed (empty `rmdir`), so a
  partial move never loses a backup whose card is still in a live history.
- **New test file `tests/test_shadow_home.py`** (9 tests): default root is outside the
  plugin dir, `HERMES_HOME` unset falls back to `plugins/../compaction-spine`, config wins
  over the default, env wins over config, migration of session dirs and loose files,
  dedupe/never-overwrite, no-op without a legacy dir, no-op when target *is* the legacy dir,
  and cards naming the configured root.
- Known cost: cards written before the move embed the old absolute path, which stops
  resolving once the files have moved. The information they name is still in the history
  card itself; only the "go read the raw backup" path breaks.

## 0.3.1 — a content-addressed name was trusted without checking the content

Found by a new test, not by review: both writers short-circuited on "a file with that name
exists and is non-empty", so a truncated or corrupted file was silently reused and the card
kept pointing at it. The name is a hash, but existence was never proof.

- **`_raw_write` verifies the bytes** before reusing a `raw-<sha16>.txt`; a mismatch is
  rewritten (and a missing `.meta.json` sidecar is re-created). Failure to verify falls
  through to the normal write path, so a damaged raw file costs a rewrite, never a lie.
- **`_shadow_write` verifies the bytes** against the span it is named after before reuse.
  A truncated span backup is rewritten instead of being handed to the model as "the original".
- **New test file `tests/test_raw_integrity.py`** (8 tests): raw file byte-identical to the
  tool output, name hashes to its own content, every `raw-*.txt` a card names exists on
  disk, truncated raw file repaired, backup holds the prompt not the card, no orphan
  sidecar, idempotent rewrite, truncated span backup repaired. The previous suite only
  asserted `meta.is_file()`, which is why this slipped through.

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
  as fact in a later card. Two tiers remain: *user* lines block the cut if they cannot be
  kept, *tool* lines are best effort (their raw file is named in the card).
- **Failure lines first, bulk lines capped by shape.** Tool evidence is ordered
  failures → everything else → code lines, and near-identical rows (an 800-line log whose
  rows differ only in a number) are capped per digit-collapsed "shape". A 13 kB log whose
  only signal is 3 ERROR lines now yields a 669-token card that contains all 3, instead of
  a card full of the first 80 INFO rows.
- **Timestamped log failures are claims.** `2026-11-04 09:12:57 ERROR …` is kept even
  though it does not start with `Error:`; prose that merely mentions an error is not.
- **`[exit code: N]` only counts at the END** of a tool result (a note *mentioning* a
  failure no longer marks the call as failed). Long failing results now keep their head,
  up to 8 failure-marker lines and their tail instead of collapsing to "omitted".
- **Per-session shadow directories** (`shadow/<session>/`), so rotating one session's
  backups can never touch another session that is still running.
- 37 tests (up from 16): keep-window arithmetic, window-relative sizing, exit-code
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

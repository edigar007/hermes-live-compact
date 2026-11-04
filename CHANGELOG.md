# Changelog

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

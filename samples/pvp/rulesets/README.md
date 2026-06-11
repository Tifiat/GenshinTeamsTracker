# PvP Ruleset Samples

These files are temporary offline fixtures for backend tests and smoke commands.
They are not raw Gentor/Abyss captures and are not production catalog data.

- `minimal_gtt_ruleset.json` uses synthetic ids aligned with
  `samples/pvp/free_draft_player_1_deck.json` so cost-preview tests can exercise
  stable id matching.
- `gentor_like_sanitized_ruleset.json` is a tiny hand-written payload shaped
  after the public Gentor fields documented in `docs/handoff/`. Its ids are
  intentionally source-local so tests can prove name fallback is reported as a
  mapping gap instead of treated as a stable match.

Replace these with a real importer fixture only after the PvP ruleset contract
and source-permission expectations are stable.

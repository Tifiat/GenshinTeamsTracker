# PvP Ruleset Source Discovery Matrix

Last checked: 2026-06-11.

Scope: backend/research handoff only. No UI, no importer product surface, no
script execution, no saved raw public payloads.

## Draft System vs Ruleset Data

- A draft system/pipeline is a GTT adapter/template that defines executable
  stages and action order: prebans, picks, middle bans, teams, weapons, timers,
  and result flow. Free Draft v0 is implemented this way; future French or
  Abyss-like modes need their own explicit adapter before execution.
- Seasonal ruleset/balance data is imported or entered from Gentor, Excel,
  Sheets, Discord docs, JSON, or similar sources. It can update costs, tiers,
  restrictions, weapon costs/overrides, ban counts, thresholds, and tier
  requirements, but those knobs are not automatically a complete executable
  schedule.
- Gentor/Abyss public data is useful for cost/config/balance research. It is
  not enough today to derive universal schedule execution automatically.
- Detailed organizer spreadsheets may later get a source-specific adapter after
  the source format and permissions are explicit.

## Matrix

| Source | Public location checked | Confirmed fields | Current parser support | PvP backend applicability | Schedule status | Risk / next step |
| --- | --- | --- | --- | --- | --- | --- |
| Gentor rulesheets | `https://gentor.vercel.app/planilhas`, `https://gentor.com.br/planilha`, `https://gentor.com.br/planilha/3` | `personagens`, `armas`, character C0-C6 costs, level 95/100 extras, weapon R1-R5 costs, character-specific weapon overrides, `tiers`, `configuracao`, optional script | `TournamentRulesetV1` parses normalized and Gentor-like shapes for costs/config/tiers. Live probe on 2026-06-11 returned HTTP 200 for `/planilha` and `/planilha/3`. | Cost-preview research is supported through `run_workspace/pvp/ruleset_costs.py`; id mismatch/name fallback is reported as a mapping gap. | Not executable. Gentor config gives knobs and may include script logic, but not a universal explicit pick/ban flow. | Add a source-specific adapter only after importer/source-permission expectations are decided. Do not execute source scripts in v0. |
| Abyss Draft | `https://abyss.darte.gg/`, `/drafts`, `/draft-systems` | Public UI and client chunks expose draft concepts/phases/roles; unauthenticated browser probe saw pages/assets/API calls. Plain `urllib` GET returned 403 on 2026-06-11. | No current ruleset payload parser. | Product concepts inform PvP vocabulary, but no real Abyss ruleset can be parsed from public data today. | Not executable. | Needs either an explicit public API/sample, user-provided export, or a manual normalized fixture before backend mapping. |
| Local normalized JSON/CSV | `samples/rulesets/minimal_ruleset.json`, `samples/pvp/rulesets/*.json` | Metadata, characters, weapons, tiers, draft config; synthetic PvP samples also cover id-aligned deck pricing and Gentor-like id gaps. | Supported by `TournamentRulesetV1`; PvP applicability/cost reports consume parsed rulesets. | Supported for offline tests and smoke only. | Not executable unless a future ruleset is paired with an explicit GTT `DraftSchedule`/draft-system adapter. | Keep samples small and clearly synthetic; replace only with sanitized real fixtures when the import contract exists. |
| Organizer spreadsheets / Discord docs | No durable public sample in repo | Unknown; likely tournament-specific columns and localized names | Not implemented | Not applicable | Not executable | Future manual XLSX/CSV importer should generate alias/mapping reports before any automatic use. |

## Current Backend Entry Points

- `run_workspace/pvp/draft_system.py`: executable draft-system registry. This
  is the GTT adapter boundary that keeps draft flow separate from imported
  ruleset/balance data.
- `run_workspace/pvp/ruleset_applicability.py`: report-only bridge from
  `TournamentRulesetV1` to PvP v0 capabilities and blockers.
- `run_workspace/pvp/ruleset_costs.py`: deck cost preview using ids first,
  display-name fallback with explicit warnings, level extras, and
  character-specific weapon overrides for assigned weapon previews.
- `python -m run_workspace.pvp.ruleset_applicability_smoke`: deterministic
  backend-only smoke over synthetic ruleset fixtures and a PvP sample deck.

## Current Conclusion

Real Gentor rulesheets can currently be parsed enough for character/weapon cost
research and config inspection, but not enough to execute a PvP draft schedule
without an explicit GTT draft-system adapter or source-specific adapter. Real
Abyss Draft rulesets cannot currently be parsed from confirmed public data in
this repo.

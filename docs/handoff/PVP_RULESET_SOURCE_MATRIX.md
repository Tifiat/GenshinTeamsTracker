# PvP Ruleset Source Discovery Matrix

Last checked: Abyss 2026-10-09; Gentor historical findings 2026-06-11.

Scope: source/applicability routing. [Deck rules](PVP_DECK_RULES.md) owns the
current Abyss editor/adapter. No source-script execution or saved raw payloads.

Current direction (2026-10-09): Free Draft and provider/build services exist.
Usable public Abyss machine rules and tournament-linked regulations are now
confirmed. [Live source mapping and conflicts](PVP_ABYSS_SOURCE_AUDIT.md) owns
current evidence. The user asked Worker4 to discover/retrieve/map sources; do
not wait for the user to locate an export. Product deck UI and known cost/limit
checks exist under `PVP_DECK_RULES.md`; exact rule matching/matches remain open.

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
- Gentor configuration alone does not define a universal schedule. Abyss now
  supplies an explicit phase/action list; unsupported actions still need a GTT
  adapter and validation before execution.
- Detailed organizer spreadsheets may later get a source-specific adapter after
  the source format and permissions are explicit.

## Matrix

| Source | Public location checked | Confirmed fields | Current parser support | PvP backend applicability | Schedule status | Risk / next step |
| --- | --- | --- | --- | --- | --- | --- |
| Gentor rulesheets | `https://gentor.vercel.app/planilhas`, `https://gentor.com.br/planilha`, `https://gentor.com.br/planilha/3` | `personagens`, `armas`, character C0-C6 costs, level 95/100 extras, weapon R1-R5 costs, character-specific weapon overrides, `tiers`, `configuracao`, optional script | `TournamentRulesetV1` parses normalized and Gentor-like shapes for costs/config/tiers. Live probe on 2026-06-11 returned HTTP 200 for `/planilha` and `/planilha/3`. | Cost-preview and report-only deck application research is supported through `run_workspace/pvp/ruleset_costs.py` and `run_workspace/pvp/ruleset_balance.py`; id mismatch/name fallback is reported as a mapping gap. | Not executable. Gentor config gives knobs and may include script logic, but not a universal explicit pick/ban flow. | Add a source-specific adapter only after importer/source-permission expectations are decided. Do not execute source scripts in v0. |
| Abyss Draft | `https://abyss.darte.gg/api/abyss/draft_systems`, `/draft_systems/{id}`, `/agents`, `/engines`, `/tournaments` | HTTP 200 without auth; prices, percentage level modifiers, weapon overrides, bundles, tiers, preset constraints and explicit phases. | Product pinned-deck adapter and UI; separate from generic `TournamentRulesetV1`. | Nine current DEFAULT families parse; French mode unsupported. Stable IDs/variants, price/limit/declaration display; [editor contract](PVP_DECK_RULES.md). | Explicit 26-action list available; immune actions and exact rule matching are not implemented/accepted in GTT. | Currentness and saved snapshots in editor; API/document conflicts remain in [source receipt](PVP_ABYSS_SOURCE_AUDIT.md). |
| Local normalized JSON/CSV | `samples/rulesets/minimal_ruleset.json`, `samples/pvp/rulesets/*.json` | Metadata, characters, weapons, tiers, draft config; synthetic PvP samples also cover id-aligned deck pricing and Gentor-like id gaps. | Supported by `TournamentRulesetV1`; PvP applicability, cost, and balance application reports consume parsed rulesets. | Supported for offline tests and smoke only. | Not executable unless a future ruleset is paired with an explicit GTT `DraftSchedule`/draft-system adapter. | Keep samples small and clearly synthetic; replace only with sanitized real fixtures when the import contract exists. |
| Organizer documents / spreadsheets | Abyss tournament API links public Google Docs and cost Sheets; current links in receipt | Regulated budget, weapon split, tier counts, restarts and phases; linked guide/Sheets differ from current API | Public text/CSV access confirmed; no product document importer | Requires an explicit tournament override/conflict layer | Do not infer full execution from prose | Keep versions separate; no user-provided file prerequisite for the confirmed Abyss source. |

## Current Backend Entry Points

- `run_workspace/pvp/draft_system.py`: executable draft-system registry. This
  is the GTT adapter boundary that keeps draft flow separate from imported
  ruleset/balance data.
- `run_workspace/pvp/ruleset_applicability.py`: report-only bridge from
  `TournamentRulesetV1` to PvP v0 capabilities and blockers.
- `run_workspace/pvp/ruleset_costs.py`: deck cost preview using ids first,
  display-name fallback with explicit warnings, level extras, and
  character-specific weapon overrides for assigned weapon previews.
- `run_workspace/pvp/ruleset_balance.py`: report-only application layer for a
  parsed ruleset against a deck or compact session bundle summary. It reports
  id/name/fallback matching, costs, unsupported features, and not-enforced
  restrictions without turning source rulesets into executable schedules.
- `python -m run_workspace.pvp.ruleset_applicability_smoke`: deterministic
  backend-only smoke over synthetic ruleset fixtures and a PvP sample deck.
- `python -m run_workspace.pvp.ruleset_balance_smoke`: deterministic
  backend-only smoke for the ruleset/balance application report.

## Current Conclusion

Real Gentor rulesheets can currently be parsed enough for character/weapon cost
research, config inspection, and report-only deck application summaries, but
not enough to execute a PvP draft schedule without an explicit GTT draft-system
adapter or source-specific adapter. Real Abyss rules now have a dedicated deck
adapter, pinned snapshots and editor. Full matching and match execution remain
separate from the implemented known-cost/bounds checks.

Keep displayed declarations distinct from enforced legality. The editor uses the
confirmed API; source documents guide remaining matching/override work. The user
need not find the sources. Source access does not establish native UI acceptance.

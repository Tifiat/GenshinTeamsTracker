# Task: Abyss Enemy Data Source Audit

Use this as a handoff prompt for a separate chat/agent.

## Goal

Research sources for Spiral Abyss enemy/room data that GenshinTeamsTracker can later use to show factual DPS from enemy HP/time and to inform future simulator/bot/team-building features.

This is research/audit only.

Do not edit app code. Do not run the app. Do not run HoYoLAB import. Do not read project generated/private/account folders. Reading existing project roadmap docs is not required. Focus on external/public data sources and create a source-oriented handoff file.

## Required Output File

Create a markdown research file:

- `docs/handoff/ABYSS_ENEMY_DATA.md`

The file must be practical and source-oriented. Include concrete URLs, repository paths, data keys, sample field names, update cadence if known, and uncertainty labels.

Use these labels:

- `Confirmed`
- `Unconfirmed`
- `Needs follow-up`
- `Risk`
- `MVP recommendation`

## What To Find

Find data sources for current and recent Spiral Abyss enemy lineups and enemy metadata.

Collect broadly first; filtering can happen later.

Need anything that may matter for factual DPS, Team Builder, simulator, draft bots, and UI explanations:

- Abyss season/period identifiers.
- Floor/chamber/side layout.
- Waves per chamber/side.
- Enemy internal ids/monster ids.
- Enemy display names and localized names if available.
- Enemy level.
- Enemy HP or HP multipliers.
- Total HP per side/chamber.
- Enemy resistances by element and physical.
- Enemy shields, armor, gauges, or special durability if source exposes them.
- Enemy immunities.
- Special states and mechanics.
- Invulnerability windows, phases, forced downtime, burrow/fly/hidden states, etc.
- Spawn positions, coordinates, distances, grouping/wave timings if available.
- Enemy icons/images and asset keys.
- Tags useful for human/bot summaries:
  - boss-heavy;
  - AoE needed;
  - single-target;
  - multi-wave;
  - grouping useful;
  - shield check;
  - elemental immunity/counter constraints;
  - high mobility;
  - phase/invulnerability warnings.

## Source Types To Investigate

Use primary/source-like data when possible. Do not rely on one source only.

Investigate at least:

- Official or source-like game data dumps if publicly available.
- GCSIM source/data for enemy HP/resist data and target modeling:
  - `pipeline/pkg/data/enemy/*`
  - `ui/packages/docs/docs/reference/enemies/*`
  - generated docs components such as HP/resist tables.
- Community data sources/sites/APIs for Abyss lineups:
  - HomDGCat / hakush.in style data if available.
  - ambr.top style data if available.
  - other public repos/datasets that expose Abyss schedules/lineups.
- Wiki/reference pages only as fallback or cross-check, not sole source.

For each source, record:

- Source URL/repo.
- Whether it has current Abyss lineups.
- Whether it has historical Abyss lineups.
- Whether it has enemy base stats/HP/resistances.
- Whether it has mechanics/phases/invulnerability info.
- Whether it has spawn/wave/position info.
- Data format: JSON, TS/JS, YAML, markdown, generated pages, API.
- Relevant keys/field names.
- Language/localization behavior.
- License/terms/usage concerns.
- Update cadence/freshness.
- Reliability and gaps.

## Suggested File Structure

Use this structure in `docs/handoff/ABYSS_ENEMY_DATA.md`:

1. Overview
2. Candidate Sources Summary
3. Spiral Abyss Lineup Data
4. Enemy HP / Level / Scaling Data
5. Enemy Resistances / Immunities
6. Waves / Spawn Positions / Room Geometry
7. Mechanics / Phases / Invulnerability
8. Icons / Localized Names / Asset Keys
9. Mapping Strategy
10. MVP Data Model Proposal
11. Fallback Behavior When Data Is Missing
12. License / Terms Risks
13. Open Questions
14. Useful Source Pointers

## MVP Product Needs

The near-term MVP is not full simulation.

Near-term app needs:

- Build an Abyss season/period page.
- Show chamber/side enemy list.
- Calculate factual DPS from total known enemy HP and clear time.
- Show `no data` / `нет данных` when HP or enemy data is missing.
- Keep factual DPS separate from future `sim DPS`.

MVP recommendation should answer:

- Which source is best for current Abyss lineups?
- Which source is best for enemy HP/resistances?
- Whether one source can cover both or whether a two-source join is needed.
- What stable key should join lineup enemies to enemy stat rows.
- What minimal local cache shape should be used first.

## Important Product Rules

- Do not claim factual HP/time DPS is exact damage dealt. Waves, immunity, shields, phase downtime, movement, and invulnerability can distort it.
- Preserve enough enemy structure to improve this later.
- If no network/source data is available, app should still create a date-based Abyss period and mark enemy HP/DPS as unavailable.
- Do not design the app around a single brittle source if alternatives exist.

## Final Response From Audit Chat

Report back:

- Created file path.
- Sources inspected.
- Most promising source(s).
- Key fields discovered.
- Biggest blockers.
- Recommended MVP source/model.
- Whether any source can provide current Abyss HP totals reliably.

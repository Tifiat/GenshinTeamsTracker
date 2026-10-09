"""On-demand rules loading for Decks; no account access or persistent cache."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from localization import tr, get_language
from run_workspace.pvp import abyss_client
from run_workspace.pvp.abyss_rules import AbyssRuleset, evaluate_deck
from run_workspace.pvp.deck import FREE_DRAFT_V0_RULESET_ID
from run_workspace.pvp.schedule import default_free_draft_v0_config
from run_workspace.pvp.tier_allocation import allocate_requirements
from run_workspace.pvp.weapon_roster_budget import (
    CUP_SOURCE as _MANUAL_REGULATION_SOURCE,
    REGULATION_URL as _MANUAL_REGULATION_URL,
    build_weapon_roster_report,
)


_MANUAL_REGULATION_CHECKED = "2026-10-09"


class _JobSignals(QObject):
    finished = Signal(object, object, object, str)


class _RulesJob(QRunnable):
    def __init__(self, kind, context, operation):
        super().__init__()
        self.kind, self.context, self.operation = kind, context, operation
        self.signals = _JobSignals()

    def run(self):
        try:
            result = self.operation()
            error = ""
        except Exception as exc:
            result = None
            error = getattr(exc, "code", "abyss_schema_error")
        self.signals.finished.emit(self.kind, self.context, result, error)


class _AllocationSignals(QObject):
    finished = Signal(int, object)


class _AllocationJob(QRunnable):
    def __init__(self, generation, characters, rules):
        super().__init__()
        self.generation, self.characters, self.rules = generation, characters, rules
        self.signals = _AllocationSignals()

    def run(self):
        try:
            result = allocate_requirements(self.characters, self.rules)
        except Exception:
            result = {"status": "unknown", "complete": False, "reason": "calculation error"}
        self.signals.finished.emit(self.generation, result)


class DeckRulesController(QObject):
    changed = Signal()
    rules_received = Signal(object, object)
    requirements_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.catalog = ()
        self.catalog_loaded = False
        self.catalog_current = False
        self.loading = False
        self.error_code = ""
        self._job = None
        self._allocation_rules = None
        self._allocation_characters = None
        self._allocation_result = None
        self._allocation_generation = 0
        self._allocation_job = None
        self._allocation_pending = None
        self._report_rules = None
        self._report_characters = None
        self._report_weapons = None
        self._report = None
        self._snapshot = None

    @property
    def requirements_loading(self):
        return self._allocation_job is not None or self._allocation_pending is not None

    def _queue_allocation(self, rules, deck, report):
        if self._allocation_rules is rules and self._allocation_characters == deck.characters:
            return
        self._allocation_rules, self._allocation_characters = rules, deck.characters
        self._allocation_generation += 1
        self._allocation_result = {"status": "unknown", "complete": False, "reason": "pending"}
        self._allocation_pending = (self._allocation_generation, report["character_rows"], self._snapshot["preset_rules"])
        if self._allocation_job is None:
            self._start_allocation()

    def _start_allocation(self):
        job = _AllocationJob(*self._allocation_pending)
        self._allocation_pending = None
        self._allocation_job = job
        job.signals.finished.connect(self._allocation_finished)
        QThreadPool.globalInstance().start(job)

    @Slot(int, object)
    def _allocation_finished(self, generation, result):
        self._allocation_job = None
        if generation == self._allocation_generation:
            self._allocation_result = result
            # Only the requirements panel changed; do not rebuild the card grids.
            self.requirements_changed.emit()
        if self._allocation_pending is not None:
            self._start_allocation()

    def _clear_allocation(self):
        if self._allocation_rules is not None:
            self._allocation_generation += 1
        self._allocation_rules = self._allocation_characters = self._allocation_result = None
        self._allocation_pending = None
        self._report_rules = self._report_characters = self._report_weapons = None
        self._report = self._snapshot = None

    def refresh(self):
        return self._start("catalog", None, abyss_client.list_latest_rulesets)

    def load(self, system_id, context):
        if not self.catalog_current or not any(row.system_id == system_id for row in self.catalog):
            return False

        def operation():
            source = abyss_client.fetch_ruleset_source(system_id)
            return AbyssRuleset.from_source(
                *source, fetched_at=datetime.now(timezone.utc).isoformat(),
            )

        return self._start("rules", context, operation)

    def _start(self, kind, context, operation):
        if self.loading:
            return False
        self.loading = True
        self.error_code = ""
        job = _RulesJob(kind, context, operation)
        self._job = job
        job.signals.finished.connect(self._finished)
        self.changed.emit()
        QThreadPool.globalInstance().start(job)
        return True

    @Slot(object, object, object, str)
    def _finished(self, kind, context, result, error):
        self.loading = False
        self._job = None
        self.error_code = error
        if kind == "catalog":
            self.catalog_current = not bool(error)
            if not error:
                self.catalog = result
                self.catalog_loaded = True
        elif not error:
            self.rules_received.emit(context, result)
        self.changed.emit()

    def ui_state(self, preset, *, editable, rules=None, deck=None):
        state = {
            "options": ({"id": FREE_DRAFT_V0_RULESET_ID, "label": tr("app_shell.pvp.decks.ruleset_free")},)
            + tuple({"id": "abyss:" + row.system_id, "label": row.title} for row in self.catalog if self.catalog_current),
            "selected_id": preset.ruleset_id if preset else FREE_DRAFT_V0_RULESET_ID,
            "editable": editable,
            "loading": self.loading,
            "catalog_loaded": self.catalog_loaded,
            "source_title": "", "version_text": "", "freshness": "free", "update_id": "",
            "summary_lines": (), "requirement_lines": (), "requirement_rows": (), "issue_lines": (),
            "error_text": _t(self.error_code) if self.error_code else "",
        }
        if rules is None:
            self._clear_allocation()
            if preset is not None and preset.ruleset_id == FREE_DRAFT_V0_RULESET_ID:
                minimum = default_free_draft_v0_config().minimum_characters_per_deck
                count = len(set(preset.character_ids) - {"10000005", "10000007"})
                state["requirement_rows"] = ({
                    "label": _t("free_minimum", minimum=minimum),
                    "current": f"{count} / {minimum}",
                    "status": "pass" if count >= minimum else "fail",
                }, {"label": _t("free_costs"), "current": "—", "status": "info"})
            return state
        if rules is not self._report_rules:
            self._report_rules = rules
            self._snapshot = rules.to_dict()
            self._report = self._report_characters = self._report_weapons = None
        source = self._snapshot["source"]
        try:
            version_text = datetime.fromisoformat(source["updated_at"].replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        except ValueError:
            version_text = source["updated_at"]
        state.update(source_title=source["title"], version_text=version_text, freshness="unknown")
        choice = next((row for row in self.catalog if row.family_id == source["root_id"]), None)
        if self.catalog_current and choice is not None:
            is_latest = choice.system_id == source["system_id"] and choice.updated_at == source["updated_at"]
            state["freshness"] = "current" if is_latest else "update"
            state["update_id"] = "" if is_latest else "abyss:" + choice.system_id
        if deck is not None:
            if self._report is None or self._report_characters != deck.characters or self._report_weapons != deck.weapons:
                self._report = evaluate_deck(deck, rules).to_dict()
                self._report_characters, self._report_weapons = deck.characters, deck.weapons
            report = self._report
            self._queue_allocation(rules, deck, report)
            state.update(format_report(self._snapshot, report, deck, allocation=self._allocation_result))
        return state


def _t(key, **values):
    return tr("app_shell.pvp.rules." + key).format(**values)


def _number(value):
    return "?" if value is None else f"{value:g}"


def _criterion_label(item):
    role = item.get("specification")
    suffix = " " + _t("role_dd" if role == 0 else "role_support") if role in (0, 1) else ""
    return f"T{item['tier']}{suffix}"


def _coverage_status(filled, required, allocation):
    if required == 0:
        return "info"
    if not allocation.get("complete"):
        return "unknown"
    if filled == required:
        return "pass"
    return "fail"


def _weapon_roster_current(check, roster):
    actual = check.get("actual")
    maximum = check.get("maximum", 0)
    if actual is not None:
        return f"{_number(actual)} / {_number(maximum)}" if maximum else _number(actual)
    if check.get("code") == "weapon_roster_expensive":
        partial = _t(
            "weapon_roster_expensive_partial",
            known=_number(check.get("known_actual", 0)),
            unknown_prices=roster.get("unknown_price_count", 0),
            unclassified=roster.get("unclassified_count", 0),
            threshold=_number((roster.get("policy") or {}).get("expensive_min") or 15),
        )
    else:
        partial = _t(
            "weapon_roster_partial",
            known=_number(check.get("known_actual", 0)),
            unknown=roster.get("unknown_price_count", 0),
        )
    return f"{partial} / {_number(maximum)}" if maximum else partial


def _weapon_roster_requirement_rows(snapshot, roster):
    policy = roster.get("policy")
    provenance = ""
    if policy:
        if policy.get("source_kind") == "regulation":
            provenance = _t(
                "weapon_roster_regulation_source",
                title=policy.get("source_title") or snapshot["source"].get("title", ""),
                date=policy.get("checked_at", ""),
                url=policy.get("url", ""),
            )
        else:
            api_parts = [_t(
                "weapon_roster_api_source",
                title=policy.get("source_title") or snapshot["source"].get("title", ""),
            )]
            if policy.get("source_kind") == "api" and (
                    policy.get("minimum", 0) or not policy.get("maximum", 0)):
                api_parts.append(_t(
                    "weapon_roster_api_bounds",
                    minimum=_number(policy.get("minimum", 0)),
                    maximum=_number(policy.get("maximum", 0)) if policy.get("maximum", 0)
                    else _t("unspecified"),
                ))
            provenance = " · ".join(api_parts)

    price_unknown = (_t("weapon_roster_unknown_prices", count=roster["unknown_price_count"])
                     if roster.get("unknown_price_count", 0) else "")
    classification_unknown = (
        _t("weapon_roster_classification_unknown", count=roster["unclassified_count"])
        if roster.get("unclassified_count", 0) else "")

    if not policy:
        total = (_t("weapon_roster_partial", known=_number(roster.get("known_total", 0)),
                    unknown=roster.get("unknown_price_count", 0))
                 if roster.get("unknown_price_count", 0)
                 else _number(roster.get("total") if roster.get("total") is not None
                              else roster.get("known_total", 0)))
        return [{"label": _t("weapon_roster_cost"), "current": total,
                 "status": "info", "detail": _t("weapon_roster_policy_unspecified")}]

    rows = []
    for check in roster.get("checks", ()):
        code = check.get("code")
        label_key = {
            "weapon_roster_cost": "weapon_roster_cost",
            "weapon_roster_expensive": "weapon_roster_expensive",
        }.get(code)
        if label_key is None:
            continue
        label_values = ({"threshold": _number(policy.get("expensive_min") or 15)}
                        if code == "weapon_roster_expensive" else {})
        if code == "weapon_roster_expensive" and policy.get("general_pool") is not None:
            detail_parts = [_t(
                "weapon_roster_pools_detail",
                general=_number(policy["general_pool"]),
                reserve=_number(policy["cheap_pool"]),
                cheap_max=_number(policy["cheap_max"]),
            )]
        else:
            detail_parts = [provenance]
        if price_unknown:
            detail_parts.append(price_unknown)
        if code == "weapon_roster_expensive" and classification_unknown:
            detail_parts.append(classification_unknown)
        rows.append({"label": _t(label_key, **label_values), "current": _weapon_roster_current(check, roster),
                     "status": check.get("status", "unknown"), "detail": " · ".join(detail_parts)})
    return rows


def format_report(snapshot, report, deck, *, allocation=None):
    language = get_language()
    names = {row["game_id"]: row.get("names", {}).get(language) or row.get("names", {}).get("en") or row["game_id"]
             for row in snapshot["characters"]}
    names.update({row.character_id: row.display_name for row in deck.characters if row.display_name})
    names.update({row.weapon_id: row.display_name for row in deck.weapons if row.display_name})
    if allocation is None:
        allocation = allocate_requirements(report["character_rows"], snapshot["preset_rules"])
    allocation_rules = {row["rule_index"]: row for row in allocation.get("rules", ())}
    allocation_equals = {row["rule_index"]: row for row in allocation.get("equals", ())}
    character_rows = {row["index"]: row for row in report["character_rows"]}
    weapon_roster = report.get("weapon_roster")
    if not isinstance(weapon_roster, dict):
        # Older synthetic reports may not include the derived roster section.
        weapon_roster = build_weapon_roster_report(snapshot, report["weapon_rows"])
    known_total = _number(weapon_roster.get("known_total", 0))
    unknown_price_count = weapon_roster.get("unknown_price_count", 0)
    if unknown_price_count:
        roster_total = _t("weapon_roster_partial", known=known_total,
                          unknown=unknown_price_count)
    else:
        roster_total = _number(weapon_roster.get("total")
                               if weapon_roster.get("total") is not None
                               else weapon_roster.get("known_total", 0))
    summary = [
        _t("character_cost", value=_number(report["character_total"])),
        _t("weapon_roster_summary", value=roster_total),
        _t("card_legend"),
    ]
    if report.get("bundle_adjustment_total"):
        summary.append(_t("bundle_adjustment", value=_number(report["bundle_adjustment_total"])))
    counts = report["tier_counts"]
    if counts:
        summary.append(_t("tier_counts", values=" · ".join(f"T{k}: {v}" for k, v in sorted(counts.items()))))
    requirements = []
    requirement_rows = []
    requirement_rows.append({"label": _t("weapon_price_explanation"), "current": "—", "status": "info"})
    traveler_required = False
    for group, metrics in (("agents", ("cost", "count")), ("engines", ("count",))):
        for metric in metrics:
            low, high = snapshot["bounds"][group][metric]
            if low or high:
                label = _t("limit", subject=_t(group + "_" + metric),
                           minimum=_number(low), maximum=_number(high) if high else _t("unspecified"))
                requirements.append(label)
                actual = report[("character" if group == "agents" else "weapon") + ("_total" if metric == "cost" else "_count")]
                uncertain = group == "agents" and metric == "cost" and bool(report["bundle_candidates"])
                failed = actual is not None and (actual < low or high > 0 and actual > high)
                status = ("unknown" if actual is None or uncertain else "fail" if failed
                          else "unknown" if high == 0 else "pass")
                if actual is None and group == "engines":
                    current = _t("weapon_count_incomplete")
                else:
                    current = _number(actual)
                requirement_rows.append({"label": label, "current": current, "status": status,
                                         "detail": _t("bundle_application_unverified") if uncertain else ""})
    requirement_rows.extend(_weapon_roster_requirement_rows(snapshot, weapon_roster))
    phase_teams = snapshot.get("phase_teams", {})
    team_weapon_max = phase_teams.get("max_engines_cost")
    if team_weapon_max is not None:
        requirement_rows.append({
            "label": _t("phase_teams_weapon_max"), "current": _number(team_weapon_max),
            "status": "info", "detail": _t("phase_teams_not_deck_cap"),
        })
    team_weapon_step = phase_teams.get("max_engines_cost_step")
    if team_weapon_step is not None:
        requirement_rows.append({"label": _t("phase_teams_weapon_step"),
                                 "current": _number(team_weapon_step), "status": "info"})
    source = snapshot["source"]
    if all(source.get(key) == value for key, value in _MANUAL_REGULATION_SOURCE.items()):
        source_detail = _t("manual_regulation_source", date=_MANUAL_REGULATION_CHECKED,
                           url=_MANUAL_REGULATION_URL)
        requirement_rows.extend((
            {"label": _t("manual_joker_regulation"), "current": _t("manual_info"),
             "status": "info", "detail": source_detail},
            {"label": _t("regulation_score_difference"), "current": _t("manual_info"),
             "status": "info"},
        ))
    for row in snapshot["tiers"]:
        requirements.append(f"T{row['tier']}: {_number(row['min_cost'])}–{_number(row['max_cost'])}")
        requirement_rows.append({
            "label": _t("tier_band", tier=row["tier"], minimum=_number(row["min_cost"]), maximum=_number(row["max_cost"])),
            "current": str(counts.get(str(row["tier"]), 0)), "status": "info",
        })
    outside_count = sum(row.get("tier_status") == "outside" for row in report["character_rows"])
    if snapshot["tiers"]:
        requirement_rows.append({"label": _t("outside_tiers"), "current": str(outside_count),
                                 "status": "info", "detail": _t("outside_tiers_detail")})
    for rule_index, rule in enumerate(snapshot["preset_rules"]):
        kind = rule["type"]
        if kind in ("requires", "equals"):
            parts = [_criterion_label(item) for item in rule["from"]]
            text = _t(kind, tier=rule["to"], parts=" + ".join(parts))
            if "from_cost" in rule:
                text += _t("threshold", value=_number(rule["from_cost"]))
            requirements.append(text)
            if kind == "requires":
                assigned = allocation_rules.get(rule_index, {})
                selected = assigned.get("selected", counts.get(str(rule["to"]), 0))
                if not assigned and any(row["tier"] is None and row.get("tier_status") != "outside"
                                        for row in report["character_rows"]):
                    selected = None  # An unresolved tier may add another target.
                covered = assigned.get("covered")
                requirement_rows.append({"label": text, "current": f"{covered if covered is not None else '—'} / {selected if selected is not None else '?'}",
                                         "status": _coverage_status(covered, selected, allocation),
                                         "detail": _t("coverage_legend")})
                slots = assigned.get("slots") or [dict(item, required=selected, filled=None) for item in rule["from"]]
                for slot in slots:
                    requirement_rows.append({"label": _criterion_label(slot),
                                             "current": f"{slot['filled'] if slot['filled'] is not None else '—'} / {slot['required'] if slot['required'] is not None else '?'}",
                                             "status": _coverage_status(slot["filled"], slot["required"], allocation),
                                             "depth": 1,
                                             **({"character_filter": (slot["tier"], slot["specification"])}
                                                if slot.get("specification") in (0, 1) else {})})
            else:
                assigned = allocation_equals.get(rule_index, {})
                used = assigned.get("used")
                settled = allocation.get("complete", False)
                current = ("—" if used is None else _t("groups_not_needed")
                           if used == 0 and allocation.get("status") == "pass"
                           else _t("groups_used", count=used))
                requirement_rows.append({"label": text, "current": current,
                                         "status": "unknown" if not settled else "pass" if used else "info"})
                for group in assigned.get("groups", ()):
                    members = [character_rows[index] for index in group]
                    label = " + ".join(names.get(row["character_id"], row["character_id"]) for row in members)
                    total = sum(row["cost"] for row in members)
                    requirement_rows.append({"label": label, "current": _number(total),
                                             "status": "pass", "depth": 1, "allocation_group": True})
        elif kind == "max_count":
            text = _t("max_count", value=rule["count"])
            requirements.append(text)
            actual = report["character_count"]
            requirement_rows.append({"label": text, "current": f"{actual} / {rule['count']}",
                                     "status": "pass" if actual <= rule["count"] else "fail"})
        elif kind == "required_agents":
            required_names = []
            for item in rule["characters"]:
                name = names.get(item["game_id"], item["game_id"])
                if item["game_id"] in ("10000005", "10000007"):
                    traveler_required = True
                    element = {11: "anemo", 12: "cryo", 13: "dendro", 14: "electro",
                               15: "geo", 16: "hydro", 17: "pyro"}.get(item["attribute"])
                    if element:
                        name += " (" + tr("filter.element." + element) + ")"
                required_names.append(name)
            requirements.append(_t("required", names=", ".join(required_names)))
            selected_sources = {row["source_id"] for row in report["character_rows"]}
            present = sum(item["source_id"] in selected_sources for item in rule["characters"])
            total = len(rule["characters"])
            requirement_rows.append({"label": _t("required_heading"), "current": f"{present} / {total}",
                                     "status": "pass" if present == total else "fail"})
            for item, name in zip(rule["characters"], required_names):
                present = item["source_id"] in selected_sources
                requirement_rows.append({"label": name, "current": _t("present" if present else "missing"),
                                         "status": "pass" if present else "fail", "depth": 1})
        else:
            requirements.append(_t("unsupported_rule"))
            requirement_rows.append({"label": _t("unsupported_rule"), "current": "?", "status": "unknown"})
    issues = [_t("traveler_unavailable")] if traveler_required else []
    if allocation.get("status") == "fail":
        issues.append(_t("allocation_shortfall"))
    elif allocation.get("status") == "unknown" and allocation.get("reason") != "pending":
        reason = allocation.get("reason")
        issues.append(_t("allocation_budget" if reason == "budget" else "allocation_unknown"))
    by_code = {}
    for issue in report["issues"]:
        if issue["code"] == "tier_combination_unverified":
            continue
        by_code.setdefault(issue["code"], []).append(issue["details"])
    for key, details in by_code.items():
        if key == "weapon_roster_classification_unknown":
            count = sum(detail.get("count", 0) for detail in details)
            text = _t(key, count=count)
        else:
            text = _t(key)
        if text == "app_shell.pvp.rules." + key:
            text = _t("unsupported_rule")
        identities = list(dict.fromkeys(value for detail in details
                                       if (value := detail.get("character_id") or detail.get("weapon_id"))))
        if identities:
            text += " — " + ", ".join(names.get(value, value) for value in identities[:3])
            if len(identities) > 3:
                text += f" (+{len(identities) - 3})"
        if text not in issues:
            issues.append(text)
    if not issues:
        summary.append(_t("checks_passed"))
    if any(row["type"] in ("requires", "equals") for row in snapshot["preset_rules"]):
        pending = allocation.get("status") == "unknown" and allocation.get("reason") == "pending"
        policy = {"label": _t("allocation_policy"), "current": "",
                  "status": "unknown" if pending else "info"}
        if pending:
            policy["status_detail"] = _t("allocation_pending")
        requirement_rows.append(policy)
    return {"summary_lines": tuple(summary), "requirement_lines": tuple(requirements),
            "requirements_pending": allocation.get("reason") == "pending",
            "requirement_rows": tuple(requirement_rows), "issue_lines": tuple(issues)}

"""On-demand rules loading for Decks; no account access or persistent cache."""
from __future__ import annotations

from datetime import datetime, timezone

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from localization import tr, get_language
from run_workspace.pvp import abyss_client
from run_workspace.pvp.abyss_rules import AbyssRuleset, evaluate_deck
from run_workspace.pvp.deck import FREE_DRAFT_V0_RULESET_ID


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


class DeckRulesController(QObject):
    changed = Signal()
    rules_received = Signal(object, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.catalog = ()
        self.catalog_loaded = False
        self.catalog_current = False
        self.loading = False
        self.error_code = ""
        self._job = None

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
            "summary_lines": (), "requirement_lines": (), "issue_lines": (),
            "error_text": _t(self.error_code) if self.error_code else "",
        }
        if rules is None:
            return state
        try:
            version_text = datetime.fromisoformat(rules.updated_at.replace("Z", "+00:00")).astimezone(timezone.utc).strftime("%d.%m.%Y %H:%M UTC")
        except ValueError:
            version_text = rules.updated_at
        state.update(source_title=rules.title, version_text=version_text, freshness="unknown")
        choice = next((row for row in self.catalog if row.family_id == rules.root_id), None)
        if self.catalog_current and choice is not None:
            is_latest = choice.system_id == rules.system_id and choice.updated_at == rules.updated_at
            state["freshness"] = "current" if is_latest else "update"
            state["update_id"] = "" if is_latest else "abyss:" + choice.system_id
        if deck is not None:
            report = evaluate_deck(deck, rules).to_dict()
            state.update(format_report(rules.to_dict(), report, deck))
        return state


def _t(key, **values):
    return tr("app_shell.pvp.rules." + key).format(**values)


def _number(value):
    return "?" if value is None else f"{value:g}"


def format_report(snapshot, report, deck):
    language = get_language()
    names = {row["game_id"]: row.get("names", {}).get(language) or row.get("names", {}).get("en") or row["game_id"]
             for row in snapshot["characters"]}
    names.update({row.character_id: row.display_name for row in deck.characters if row.display_name})
    names.update({row.weapon_id: row.display_name for row in deck.weapons if row.display_name})
    base_costs = [row["base_unit_cost"] * row["count"] if row["base_unit_cost"] is not None and row["count"] else None
                  for row in report["weapon_rows"]]
    summary = [
        _t("character_cost", value=_number(report["character_total"])),
        _t("weapon_base_cost", value=_number(sum(base_costs) if None not in base_costs else None)),
        _t("weapon_cost", value=_number(report["weapon_total"])),
        _t("card_legend"),
    ]
    if report.get("bundle_adjustment_total"):
        summary.append(_t("bundle_adjustment", value=_number(report["bundle_adjustment_total"])))
    counts = report["tier_counts"]
    if counts:
        summary.append(_t("tier_counts", values=" · ".join(f"T{k}: {v}" for k, v in sorted(counts.items()))))
    requirements = []
    traveler_required = False
    for group in ("agents", "engines"):
        for metric in ("cost", "count"):
            low, high = snapshot["bounds"][group][metric]
            if low or high:
                requirements.append(_t("limit", subject=_t(group + "_" + metric),
                                       minimum=_number(low), maximum=_number(high) if high else _t("unspecified")))
    for row in snapshot["tiers"]:
        requirements.append(f"T{row['tier']}: {_number(row['min_cost'])}–{_number(row['max_cost'])}")
    for rule in snapshot["preset_rules"]:
        kind = rule["type"]
        if kind in ("requires", "equals"):
            parts = []
            for item in rule["from"]:
                role = item.get("specification")
                suffix = " " + _t("role_dd" if role == 0 else "role_support") if role in (0, 1) else ""
                parts.append(f"T{item['tier']}{suffix}")
            text = _t(kind, tier=rule["to"], parts=" + ".join(parts))
            if "from_cost" in rule:
                text += _t("threshold", value=_number(rule["from_cost"]))
            requirements.append(text)
        elif kind == "max_count":
            requirements.append(_t("max_count", value=rule["count"]))
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
        else:
            requirements.append(_t("unsupported_rule"))
    issues = [_t("traveler_unavailable")] if traveler_required else []
    by_code = {}
    for issue in report["issues"]:
        by_code.setdefault(issue["code"], []).append(issue["details"])
    for key, details in by_code.items():
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
    return {"summary_lines": tuple(summary), "requirement_lines": tuple(requirements), "issue_lines": tuple(issues)}

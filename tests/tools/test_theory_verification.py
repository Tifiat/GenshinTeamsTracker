"""Offline checks for the saved relaxed Theory candidate renderer."""

from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
import json
from pathlib import Path
import re
import unittest

from tools.experiments.gcsim.theory_verification.render import render_candidate_config


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "tests/fixtures/gcsim_optimizer_go_v1/theory_lunar_audit_20261003_v1.json"
BASE = ROOT / "tests/fixtures/gcsim_optimizer_go_v1/inventory_bound_poc_lineage5_v1.json"
KNOWN_SETS = {"nightoftheskysunveiling", "silkenmoonsserenade"}


def _fixture() -> tuple[str, dict]:
    base = json.loads(BASE.read_text(encoding="utf-8"))["inputs"][0]["config"]
    candidate = json.loads(AUDIT.read_text(encoding="utf-8"))["product"]["candidates"][0]
    return base, candidate


def _stat_rows(config: str) -> dict[str, dict[str, Decimal]]:
    rows = {}
    for actor, body in re.findall(r"(?m)^([a-z][a-z0-9_]*) add stats ([^;\n]+);$", config):
        assert actor not in rows
        rows[actor] = {key: Decimal(value) for key, value in (part.split("=") for part in body.split(" "))}
    return rows


class TheoryVerificationRendererTest(unittest.TestCase):
    def setUp(self):
        self.config, self.candidate = _fixture()

    def render(self, *, config=None, candidate=None, known_sets=KNOWN_SETS, roll_budget=45):
        return render_candidate_config(
            self.config if config is None else config,
            self.candidate if candidate is None else candidate,
            roll_budget=roll_budget,
            known_sets=known_sets,
        )

    def test_saved_audit_candidate_has_exact_aggregate_artifact_stats_once(self):
        rendered = self.render()
        self.assertEqual(
            _stat_rows(rendered),
            {
                "columbina": {
                    "hp": Decimal("4780"), "atk": Decimal("311"),
                    "hp%": Decimal("1.3259249999999999"),
                    "em": Decimal("5.8275"), "cr": Decimal("0.311"),
                    "cd": Decimal("2.331"), "hydro%": Decimal("0.466"),
                },
                "flins": {
                    "hp": Decimal("4780"), "atk": Decimal("311"),
                    "atk%": Decimal("1.6316"), "cr": Decimal("0.4277"),
                    "cd": Decimal("2.331"),
                },
                "ineffa": {
                    "hp": Decimal("4780"), "atk": Decimal("311"),
                    "atk%": Decimal("1.208925"), "em": Decimal("81.585"),
                    "cr": Decimal("0.75834999999999997"),
                    "cd": Decimal("1.9619250000000001"),
                },
                "jahoda": {
                    "hp": Decimal("4780"), "atk": Decimal("311"),
                    "atk%": Decimal("0.917825"),
                    "cr": Decimal("0.72917499999999996"),
                    "cd": Decimal("2.05905"), "hydro%": Decimal("0.466"),
                },
            },
        )
        self.assertEqual(rendered.count("relaxed theoretical artifact vector"), 1)
        self.assertIn("five-piece physical feasibility unverified", rendered)

    def test_declarations_and_every_nonartifact_line_keep_original_order(self):
        rendered = self.render()
        untouched = lambda text: [
            line for line in text.splitlines(keepends=True)
            if " add stats " not in line
            and " add set=" not in line
            and not line.startswith("# GTT Theory relaxed")
        ]
        self.assertEqual(untouched(rendered), untouched(self.config))
        self.assertEqual(
            re.findall(r"(?m)^([a-z][a-z0-9_]*) char ", rendered),
            ["flins", "ineffa", "columbina", "jahoda"],
        )
        self.assertEqual(rendered[rendered.index("options swap_delay="):],
                         self.config[self.config.index("options swap_delay="):])

    def test_package_swap_removes_all_previous_set_effects(self):
        candidate = deepcopy(self.candidate)
        candidate["packages"][1]["sets"] = [
            {"set_uid": "newset", "count": 2},
            {"set_uid": "otherset", "count": 2},
        ]
        rendered = self.render(candidate=candidate, known_sets=KNOWN_SETS | {"newset", "otherset"})
        self.assertEqual(
            re.findall(r'(?m)^([a-z]+) add set="([a-z0-9_]+)" count=([0-9]+);$', rendered),
            [
                ("flins", "newset", "2"),
                ("flins", "otherset", "2"),
                ("ineffa", "silkenmoonsserenade", "4"),
                ("jahoda", "silkenmoonsserenade", "4"),
            ],
        )
        self.assertNotIn("nightoftheskysunveiling", rendered)
        self.assertNotIn("tenacityofthemillelith", rendered)
        self.assertNotIn("viridescentvenerer", rendered)

    def test_single_two_piece_package_is_rendered(self):
        candidate = deepcopy(self.candidate)
        candidate["packages"][0]["sets"] = [{"set_uid": "singleset", "count": 2}]
        rendered = self.render(candidate=candidate, known_sets=KNOWN_SETS | {"singleset"})
        self.assertIn('columbina add set="singleset" count=2;\ncolumbina add stats ', rendered)

    def test_missing_duplicate_or_foreign_wearer_is_rejected(self):
        for field in ("allocations", "packages"):
            for mode in ("missing", "duplicate", "foreign"):
                with self.subTest(field=field, mode=mode):
                    candidate = deepcopy(self.candidate)
                    if mode == "missing":
                        candidate[field].pop()
                    elif mode == "duplicate":
                        candidate[field][1]["wearer_key"] = candidate[field][0]["wearer_key"]
                    else:
                        candidate[field][0]["wearer_key"] = "stranger"
                    with self.assertRaises(ValueError):
                        self.render(candidate=candidate)

    def test_roll_scale_budget_and_eligible_piece_cap_are_checked(self):
        edits = (
            (lambda c: c["allocations"][0]["substats"][0].update(stat_value=0.123), "scale"),
            (lambda c: c["allocations"][0].update(spent_roll_units=44), "spent"),
            (lambda c: c["allocations"][0].update(unspent_roll_units=1), "unspent"),
            (lambda c: c["allocations"][0]["substats"][0].update(stat_value=float("nan")), "nan value"),
            (lambda c: c["allocations"][0]["substats"][0].update(roll_units=float("nan")), "nan units"),
            (lambda c: c["allocations"][0]["substats"][0].update(roll_units=-1), "negative units"),
        )
        for edit, label in edits:
            with self.subTest(label=label):
                candidate = deepcopy(self.candidate)
                edit(candidate)
                with self.assertRaises(ValueError):
                    self.render(candidate=candidate)
        with self.assertRaises(ValueError):
            self.render(roll_budget=46)
        with self.assertRaises(ValueError):
            self.render(roll_budget=44)
        candidate = deepcopy(self.candidate)
        flins = candidate["allocations"][1]
        flins["substats"] = [{"stat_key": "atk_percent", "roll_units": 18.25,
                              "stat_value": 18.25 * 0.0583}]
        flins["spent_roll_units"], flins["unspent_roll_units"] = 18.25, 26.75
        with self.assertRaisesRegex(ValueError, "eligible-piece"):
            self.render(candidate=candidate)

    def test_illegal_main_unknown_axis_and_bad_packages_are_rejected(self):
        edits = (
            lambda c: c["allocations"][0]["main_stats"].update(sands="crit_rate"),
            lambda c: c["allocations"][0]["substats"][0].update(stat_key="injected;"),
            lambda c: c["packages"][1].update(sets=[{"set_uid": "bad\"; active flins", "count": 4}]),
            lambda c: c["packages"][1].update(sets=[{"set_uid": "nightoftheskysunveiling", "count": 3}]),
            lambda c: c["packages"][1].pop("sets"),
            lambda c: c["packages"][1].update(sets=[
                {"set_uid": "nightoftheskysunveiling", "count": 2},
                {"set_uid": "nightoftheskysunveiling", "count": 2},
            ]),
        )
        for edit in edits:
            candidate = deepcopy(self.candidate)
            edit(candidate)
            with self.assertRaises(ValueError):
                self.render(candidate=candidate)
        with self.assertRaisesRegex(ValueError, "bound registry"):
            self.render(known_sets={"silkenmoonsserenade"})

    def test_orphan_duplicate_and_noncanonical_source_rows_are_rejected(self):
        bad_rows = (
            "stranger add stats hp=1;\n",
            "flins add stats hp=1;\n",
            "flins add stats hp=1; active jahoda;\n",
            "flins add stats hp=NaN;\n",
            'flins add set="oldset" count=4; active jahoda;\n',
            'stranger add set="oldset" count=4;\n',
            'flins add set="bad;set" count=4;\n',
        )
        for row in bad_rows:
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.render(config=self.config + row)
        with self.assertRaises(ValueError):
            self.render(config=self.config.replace("flins add stats", "flins add\tstats", 1))

    def test_crlf_input_keeps_crlf_and_fractional_values(self):
        config = self.config.replace("\r\n", "\n").replace("\n", "\r\n")
        rendered = self.render(config=config)
        self.assertEqual(rendered.replace("\r\n", "").count("\n"), 0)
        self.assertIn("em=5.8275", rendered)


if __name__ == "__main__":
    unittest.main()

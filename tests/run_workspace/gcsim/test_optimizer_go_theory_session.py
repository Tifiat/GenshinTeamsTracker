"""Live Theory transport checks using synthetic snapshots and owned temp files."""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from localization import tr
from run_workspace.gcsim.optimizer_go_requests import GcsimOptimizerGoError
from run_workspace.gcsim.optimizer_go_theory import GcsimOptimizerGoTheoryRequest
from run_workspace.gcsim.optimizer_go_theory_session import (
    GCSIM_OPTIMIZER_GO_THEORY_SESSION_RESULT_KIND,
    GcsimOptimizerGoTheorySession,
    THEORY_SESSION_COMMAND_KIND,
    copy_theory_snapshot,
    format_gcsim_optimizer_go_theory_session_result,
    theory_continuation_actions,
)
from run_workspace.gcsim.optimizer_theory_presentation import TheoryResultIndex
from tests.run_workspace.gcsim.theory_output_fixture import (
    EXPECTED_COUNTS, EXPECTED_GROUP_TUPLES, EXPECTED_PENDING_TUPLES,
    EXPECTED_UNAVAILABLE_TUPLES, GROUP_ROWS, REQUEST_SHA, SESSION_ID, WEARERS,
    family_row, no_verified_snapshot, output_snapshot, refresh_measurement_identity,
    snapshot_with_rows,
)


def _snapshot(
    version: int = 1, *, phase: str = "first_light", families: int = 7,
    publication_version: int | None = None,
) -> dict:
    return snapshot_with_rows(
        [family_row(str(index), 1000 - index, index / 10) for index in range(families)],
        version=version, phase=phase, publication_version=publication_version,
    )


def _session(*, callback=None) -> GcsimOptimizerGoTheorySession:
    session = GcsimOptimizerGoTheorySession(
        GcsimOptimizerGoTheoryRequest("unused", {}, 0, "rotation"),
        progress_callback=callback,
    )
    session._expected_request_sha256 = REQUEST_SHA
    return session


class TheorySessionTransportTests(unittest.TestCase):
    def test_native_wire_accepts_measured_leader_and_below_band_receipt(self) -> None:
        fixture = (
            Path(__file__).resolve().parents[2]
            / "fixtures/gcsim_optimizer_go_v1/theory_verified_wire_v3.json"
        )
        native = json.loads(fixture.read_text(encoding="utf-8"))
        snapshot = copy_theory_snapshot(
            native,
            expected_request_sha256=native["request_sha256"],
            expected_session_id=native["session_id"],
        )
        self.assertEqual(snapshot["verification"]["completed_count"], 2)
        self.assertEqual((len(snapshot["co_leaders"]), len(snapshot["pending"])), (1, 1))
        self.assertEqual(snapshot["reference_score"], 900)
        self.assertEqual(tuple(entry.score for entry in TheoryResultIndex(snapshot)), (900, 800))
        self.assertEqual(snapshot["pending"][0]["reason"], "below_verified_practical_band")

    def test_v3_command_uses_owned_finish_and_control_files(self) -> None:
        session = _session()
        root = Path("synthetic-run")
        command = session._optimizer_command(Path("optimizer.exe"), root)
        self.assertEqual(command[1], "optimize-theory")
        self.assertEqual(command[-4:], (
            "--finish-file", str(root / "finish-requested"),
            "--theory-control-file", str(root / "theory-control.json"),
        ))
        self.assertEqual(session.result_schema_kind, GCSIM_OPTIMIZER_GO_THEORY_SESSION_RESULT_KIND)
        self.assertEqual(session.request.product_timeout_ms, 0)

    def test_snapshot_copies_protect_previous_result_and_callback_ownership(self) -> None:
        events = []
        session = _session(callback=events.append)
        source = _snapshot()
        event = {"request_sha256": REQUEST_SHA, "stage": "first_light", "theory_snapshot": source}
        session._consume_progress(event)
        expected = deepcopy(source)
        source["co_leaders"][0]["aliases"].clear()
        events[0]["theory_snapshot"]["co_leaders"].clear()
        exposed = session.last_snapshot
        exposed["co_leaders"][0]["allocations"].clear()
        self.assertEqual(session.last_snapshot, expected)
        session._consume_progress({"request_sha256": REQUEST_SHA, "stage": "breadth_light", "theory_snapshot": _snapshot(2, phase="breadth_light")})
        self.assertEqual(expected["snapshot_version"], 1)
        self.assertEqual(len(expected["co_leaders"]), 7)
        self.assertEqual(session.last_snapshot["snapshot_version"], 2)

    def test_stale_identity_phase_and_version_never_replace_snapshot(self) -> None:
        events = []
        session = _session(callback=events.append)
        session._consume_progress({"request_sha256": REQUEST_SHA, "theory_snapshot": _snapshot()})
        for field, value in (
            ("request_sha256", "another-request"),
            ("session_id", "another-session"),
            ("snapshot_version", 0),
            ("snapshot_version", True),
            ("phase", "unknown-phase"),
            ("schema_version", 1),
        ):
            snapshot = _snapshot(2)
            snapshot[field] = value
            session._consume_progress({"request_sha256": REQUEST_SHA, "theory_snapshot": snapshot})
        session._consume_progress({"request_sha256": "wrong-envelope", "theory_snapshot": _snapshot(2)})
        self.assertEqual(len(events), 1)
        self.assertEqual(session.last_snapshot, _snapshot())

    def test_search_phase_cannot_regress_on_a_newer_publication(self) -> None:
        events = []
        session = _session(callback=events.append)
        session._consume_progress({"request_sha256": REQUEST_SHA, "theory_snapshot": _snapshot()})
        session._consume_progress({
            "request_sha256": REQUEST_SHA,
            "theory_snapshot": _snapshot(2, phase="breadth_light", publication_version=2),
        })
        self.assertEqual(len(events), 2)

        session._consume_progress({
            "request_sha256": REQUEST_SHA,
            "theory_snapshot": _snapshot(3, phase="first_light", publication_version=3),
        })

        self.assertEqual(len(events), 2)
        self.assertEqual(session.last_snapshot["phase"], "breadth_light")

    def test_command_is_atomic_single_shot_and_bound_to_checkpoint(self) -> None:
        session = _session()
        session._store_snapshot(_snapshot())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session._run_dir = root
            self.assertFalse(session.request_continuation("breadth", snapshot_version=0))
            self.assertTrue(session.request_continuation("breadth", snapshot_version=1))
            self.assertFalse(session.request_continuation("deep", snapshot_version=1))
            first = json.loads((root / "theory-control.json").read_text(encoding="utf-8"))
            self.assertEqual(first, {
                "schema_kind": THEORY_SESSION_COMMAND_KIND,
                "session_id": SESSION_ID,
                "request_sha256": REQUEST_SHA,
                "snapshot_version": 1,
                "sequence": 1,
                "action": "breadth",
            })
            self.assertEqual([path.name for path in root.iterdir()], ["theory-control.json"])
            session._store_snapshot(_snapshot(2, phase="breadth_light"))
            self.assertFalse(session.request_continuation("breadth", snapshot_version=2))
            self.assertTrue(session.request_continuation("deep", snapshot_version=2))
            second = json.loads((root / "theory-control.json").read_text(encoding="utf-8"))
            self.assertEqual((second["snapshot_version"], second["sequence"], second["action"]), (2, 2, "deep"))
            session._store_snapshot(_snapshot(3, phase="deep_baseline"))
            self.assertFalse(session.request_continuation("deep", snapshot_version=3))

    def test_failed_command_cleans_its_temp_and_does_not_consume_sequence(self) -> None:
        session = _session()
        session._store_snapshot(_snapshot())
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            session._run_dir = root
            with patch("run_workspace.gcsim.optimizer_go_theory_session.os.replace", side_effect=OSError("synthetic failure")):
                self.assertFalse(session.request_continuation("breadth", snapshot_version=1))
            self.assertEqual(list(root.iterdir()), [])
            self.assertEqual(session._command_sequence, 0)
            self.assertTrue(session.request_continuation("deep", snapshot_version=1))

    def test_finish_before_candidate_is_explicit_and_after_candidate_is_cooperative(self) -> None:
        session = _session()
        session.request_finish()
        with self.assertRaises(GcsimOptimizerGoError) as raised:
            session._require_search_not_finished_before_result()
        self.assertEqual(raised.exception.code, "finish_no_result")
        session = _session()
        session._store_snapshot(_snapshot())
        with tempfile.TemporaryDirectory() as temporary:
            session._run_dir = Path(temporary)
            session.request_finish()
            session._require_search_not_finished_before_result()
            self.assertTrue((Path(temporary) / "finish-requested").is_file())
            self.assertFalse(session.request_continuation("breadth", snapshot_version=1))
            self.assertFalse(session._cancelled.is_set())

    def test_cancel_retains_snapshot_without_promoting_terminal_success(self) -> None:
        session = _session()
        session._store_snapshot(_snapshot())
        session.cancel()
        self.assertFalse(session.request_continuation("deep", snapshot_version=1))
        with patch("run_workspace.gcsim.optimizer_go_theory.GcsimOptimizerGoTheorySession.run", return_value={"success": False, "status": "cancelled", "error_code": "cancelled"}):
            payload = session.run()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["status"], "cancelled")
        self.assertEqual(payload["retained_snapshot"], _snapshot())
        text = format_gcsim_optimizer_go_theory_session_result(payload)
        self.assertIn(tr("gcsim.optimizer.theory_cancelled"), text)
        self.assertIn(tr("gcsim.optimizer.theory_session.retained"), text)
        self.assertIn(_snapshot()["co_leaders"][-1]["aliases"][0]["tuple_key"], text)

    def test_cancel_during_terminal_handoff_retains_result_without_success(self) -> None:
        session = _session()
        terminal = _snapshot(2, phase="deep_baseline")
        parent_payload = {
            "success": True, "status": "success", "result": terminal,
            "adapter_timings": {"terminal_status": "success"},
        }

        def completed_before_cancel():
            session._store_snapshot(terminal)
            session.cancel()
            return parent_payload

        with patch("run_workspace.gcsim.optimizer_go_theory.GcsimOptimizerGoTheorySession.run", side_effect=completed_before_cancel):
            payload = session.run()
        self.assertFalse(payload["success"])
        self.assertEqual((payload["status"], payload["error_code"]), ("cancelled", "cancelled"))
        self.assertNotIn("result", payload)
        self.assertEqual(payload["retained_snapshot"], terminal)
        self.assertEqual(payload["adapter_timings"]["terminal_status"], "cancelled")
        self.assertTrue(parent_payload["success"])
        self.assertEqual(parent_payload["adapter_timings"]["terminal_status"], "success")
        self.assertFalse(session.request_continuation("deep", snapshot_version=2))

    def test_terminal_result_requires_a_new_snapshot_version(self) -> None:
        session = _session()
        session._store_snapshot(_snapshot())
        with patch("run_workspace.gcsim.optimizer_go_session.GcsimOptimizerGoSession._run_go_optimizer", return_value=_snapshot(2)):
            result = session._run_go_optimizer(prepared={"request_sha256": REQUEST_SHA}, compact={}, run_dir=Path("unused"), started=0)
        self.assertEqual(result["snapshot_version"], 2)
        with patch("run_workspace.gcsim.optimizer_go_session.GcsimOptimizerGoSession._run_go_optimizer", return_value=_snapshot(2)):
            with self.assertRaises(GcsimOptimizerGoError) as raised:
                session._run_go_optimizer(prepared={"request_sha256": REQUEST_SHA}, compact={}, run_dir=Path("unused"), started=0)
        self.assertEqual(raised.exception.code, "theory_snapshot_stale")

    def test_publication_updates_do_not_ack_or_replay_a_search_command(self) -> None:
        session = _session()
        session._store_snapshot(_snapshot(1))
        session._pending_command_version = 1
        streamed = _snapshot(1, publication_version=2)
        streamed["verification"]["in_progress"] = True
        session._store_snapshot(streamed)
        self.assertEqual(session._snapshot_version, 1)
        self.assertEqual(session._publication_version, 2)
        self.assertEqual(session._pending_command_version, 1)
        self.assertFalse(session.request_continuation("breadth", snapshot_version=1))
        self.assertEqual((), theory_continuation_actions("first_light", verification_in_progress=True))

    def test_distinct_verified_main_variants_may_share_one_searched_tuple(self) -> None:
        first = family_row("same-choice-a", 1000, 0)
        second = family_row("same-choice-b", 990, 1)
        second["aliases"][0]["tuple_key"] = first["aliases"][0]["tuple_key"]
        second["aliases"][0]["packages"] = deepcopy(first["aliases"][0]["packages"])
        second["witness45"]["Mains"][0][3] = "pyro_damage_bonus"
        second["allocations"][0]["main_stats"]["goblet"] = "pyro_damage_bonus"
        refresh_measurement_identity(second)
        snapshot = snapshot_with_rows([first, second])

        copied = copy_theory_snapshot(snapshot)

        self.assertEqual(len(copied["co_leaders"]), 2)
        self.assertEqual(
            copied["co_leaders"][0]["aliases"][0]["tuple_key"],
            copied["co_leaders"][1]["aliases"][0]["tuple_key"],
        )
        self.assertNotEqual(
            copied["co_leaders"][0]["measurement"]["candidate_sha256"],
            copied["co_leaders"][1]["measurement"]["candidate_sha256"],
        )

    def test_pending_only_verified_publication_is_still_ordinary_verified(self) -> None:
        row = family_row("pending-only", 1000, 0)
        row["reason"] = "below_practical_band"
        snapshot = snapshot_with_rows([row])
        snapshot["co_leaders"] = []
        snapshot["pending"] = [row]
        snapshot.update(
            found_group_families=0,
            found_group_tuples=0,
            sensitivity_group_families=0,
            sensitivity_group_tuples=0,
        )

        copied = copy_theory_snapshot(snapshot)

        self.assertEqual(copied["status"], "success")
        self.assertEqual(copied["response_status"], "ordinary_verified")
        self.assertEqual(len(copied["pending"]), 1)

    def test_no_verified_progress_is_valid_but_not_a_success_result(self) -> None:
        snapshot = no_verified_snapshot(in_progress=True)
        self.assertEqual(copy_theory_snapshot(snapshot), snapshot)
        self.assertEqual(format_gcsim_optimizer_go_theory_session_result(
            {"success": True, "result": snapshot}, include_rows=False
        ).splitlines()[0], tr("gcsim.optimizer.theory_session.checking"))
        session = _session()
        with patch("run_workspace.gcsim.optimizer_go_theory.GcsimOptimizerGoTheorySession.run", return_value={
            "success": True, "status": "success", "result": no_verified_snapshot(),
        }):
            payload = session.run()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["status"], "no_verified_result")
        self.assertNotIn("result", payload)
        self.assertEqual(payload["retained_snapshot"]["status"], "no_verified_result")
        self.assertEqual(TheoryResultIndex(payload["retained_snapshot"]).entries, ())
        text = format_gcsim_optimizer_go_theory_session_result(payload)
        self.assertEqual(text.count(tr("gcsim.optimizer.theory_session.no_verified_result_detail")), 1)
        self.assertIn(tr("gcsim.optimizer.theory_display.reference_unavailable"), text)
        self.assertNotIn(tr("gcsim.optimizer.theory_session.reference").format(
            dps="0", band="3", sensitivity="2",
        ), text)

    def test_schema_v2_formula_only_publications_fail_closed(self) -> None:
        legacy = output_snapshot()
        legacy.update(schema_version=2, schema_kind="gtt_gcsim_optimizer_theory_result_v2", response_status="formula_only")
        with self.assertRaises(GcsimOptimizerGoError):
            copy_theory_snapshot(legacy)

    def test_finite_energy_still_fails_before_formula_preparation(self) -> None:
        session = GcsimOptimizerGoTheorySession(GcsimOptimizerGoTheoryRequest("unused", {}, 0, "rotation", infinite_energy_enabled=False))
        with patch("run_workspace.gcsim.optimizer_go_all.GcsimOptimizerGoAllSetsSession._prepare_formula_inputs") as prepare:
            with self.assertRaises(GcsimOptimizerGoError) as raised:
                session._prepare_formula_inputs(prepared={}, run_dir=Path("unused"), started=0)
        self.assertEqual(raised.exception.code, "theory_finite_energy_unsupported")
        prepare.assert_not_called()

    def test_verified_rows_pending_and_unavailable_are_accessible(self) -> None:
        snapshot = _snapshot(families=7)
        pending = family_row("pending", 948.75, 5.125)
        pending["reason"] = "below_practical_band_not_deeply_refined"
        pending["aliases"][0]["tuple_key"] = "pending-choice"
        snapshot["pending"] = [pending]
        snapshot["unavailable"] = [{
            "tuple_key": "unavailable-choice", "packages": [{"wearer_key": wearer, "sets": []} for wearer in WEARERS],
            "reasons": ["synthetic-unavailable"],
        }]
        snapshot.update(total_found_families=8, total_found_tuples=24, domain_tuples="28")
        snapshot["verification"].update(
            limit=8, attempted_count=8, completed_count=8, candidate_count=8,
            remaining_budget=0, response_lane_reserve=2,
        )
        original = deepcopy(snapshot)
        self.assertEqual(copy_theory_snapshot(snapshot), snapshot)
        text = format_gcsim_optimizer_go_theory_session_result({"success": True, "result": snapshot})
        for index in range(7):
            self.assertNotIn(f"family-{index}", text)
            self.assertIn(f"choice-{index}-0", text)
            self.assertIn(f"set-{index}-0", text)
        for value in ("pending-choice", "5.125", "unavailable-choice", "synthetic-unavailable"):
            self.assertIn(value, text)
        self.assertEqual(snapshot, original)
        self.assertNotIn("Top-", text)

    def test_family_labels_use_display_ordinals_and_pending_reasons_are_localized(self) -> None:
        snapshot = _snapshot()
        pending = family_row("pending", 960, 4)
        pending["measurement"]["origins"][0]["family"] = "internal-frame-hash"
        for reason, key in (
            ("below_practical_band", "gcsim.optimizer.theory_session.below_band"),
            ("below_practical_band_not_deeply_refined", "gcsim.optimizer.theory_session.below_band_unrefined"),
        ):
            pending["reason"] = reason
            pending["refinement_level"] = 2 if reason == "below_practical_band" else 0
            snapshot["pending"] = [pending]
            snapshot.update(total_found_families=8, total_found_tuples=24, domain_tuples="27")
            snapshot["verification"].update(
                limit=8, attempted_count=8, completed_count=8, candidate_count=8,
                remaining_budget=0, response_lane_reserve=2,
            )
            self.assertEqual(copy_theory_snapshot(snapshot), snapshot)
            text = format_gcsim_optimizer_go_theory_session_result({"success": True, "result": snapshot})
            self.assertIn(tr("gcsim.optimizer.theory_session.family").format(family=7, dps="994", deficit="0.6"), text)
            self.assertIn(tr(key), text)
            self.assertNotIn(reason, text)
            self.assertNotIn("internal-frame-hash", text)

    def test_schema_copy_rejects_nonfinite_scores(self) -> None:
        snapshot = _snapshot()
        snapshot["reference_score"] = float("nan")
        with self.assertRaises(GcsimOptimizerGoError):
            copy_theory_snapshot(snapshot)


class TheoryOutputConsumerTests(unittest.TestCase):
    def test_frozen_output_is_copied_without_losing_rows_aliases_or_nested_fields(self) -> None:
        source = output_snapshot()
        copied = copy_theory_snapshot(source, expected_request_sha256=REQUEST_SHA, expected_session_id=SESSION_ID)
        self.assertEqual(copied, source)
        self.assertEqual(json.loads(json.dumps(copied, allow_nan=False)), source)
        for field, count in EXPECTED_COUNTS.items():
            self.assertEqual(copied[field], count)
        self.assertEqual(tuple(row["family"] for row in copied["co_leaders"]), tuple(row["measurement"]["candidate_sha256"] for row in copied["co_leaders"]))
        self.assertEqual(tuple(alias["tuple_key"] for row in copied["co_leaders"] for alias in row["aliases"]), EXPECTED_GROUP_TUPLES)
        self.assertEqual(tuple(alias["tuple_key"] for row in copied["pending"] for alias in row["aliases"]), EXPECTED_PENDING_TUPLES)
        self.assertEqual(tuple(row["tuple_key"] for row in copied["unavailable"]), EXPECTED_UNAVAILABLE_TUPLES)
        for row in copied["co_leaders"] + copied["pending"]:
            self.assertEqual(tuple(allocation["wearer_key"] for allocation in row["allocations"]), WEARERS)
            for actor, allocation in enumerate(row["allocations"]):
                self.assertEqual(allocation["spent_roll_units"], 45)
                self.assertEqual(allocation["unspent_roll_units"], 0)
                self.assertEqual(sum(stat["roll_units"] for stat in allocation["substats"]), 45)
                self.assertEqual(sum(sum(slot) for slot in row["witness45"]["Upgrades"][actor]), 25)
        copied["provenance"]["model"]["seeds"].clear()
        copied["co_leaders"][0]["aliases"][0]["provenance"]["bound_frame"]["coordinates"].clear()
        copied["co_leaders"][0]["witness45"]["Upgrades"][0][0][0] = 999
        self.assertEqual(source, output_snapshot())

    def test_formatter_keeps_every_unordered_boundary_row_and_exact_choice_once(self) -> None:
        source = output_snapshot()
        frozen = deepcopy(source)
        text = format_gcsim_optimizer_go_theory_session_result({"success": True, "result": source})
        position = -1
        for ordinal, (_, score, deficit) in enumerate(GROUP_ROWS, start=1):
            label = tr("gcsim.optimizer.theory_session.family").format(family=ordinal, dps=f"{score:,.6g}", deficit=f"{deficit:,.6g}")
            self.assertGreater(text.index(label), position)
            position = text.index(label)
        for key in EXPECTED_GROUP_TUPLES + EXPECTED_PENDING_TUPLES + EXPECTED_UNAVAILABLE_TUPLES:
            self.assertEqual(text.count(tr("gcsim.optimizer.theory_session.choice").format(key=key)), 1)
        for row in source["co_leaders"] + source["pending"]:
            for allocation in row["allocations"]:
                self.assertIn(allocation["wearer_key"], text)
            for alias in row["aliases"]:
                for package in alias["packages"]:
                    for item in package["sets"]:
                        self.assertIn(item["set_uid"], text)
                for reason in alias["uncertainty"]:
                    self.assertIn(reason, text)
        self.assertIn(tr("gcsim.optimizer.theory_session.pending"), text)
        self.assertIn(tr("gcsim.optimizer.theory_session.below_band_unrefined"), text)
        self.assertIn(tr("gcsim.optimizer.theory_session.below_band"), text)
        self.assertIn(tr("gcsim.optimizer.theory_session.unavailable"), text)
        self.assertIn(tr("gcsim.optimizer.theory_session.domain_coverage").format(domain="32", unseen="3"), text)
        self.assertIn(tr("gcsim.optimizer.theory_session.coverage_partial"), text)
        self.assertIn(tr("gcsim.optimizer.theory_session.unbounded"), text)
        self.assertNotIn(tr("gcsim.optimizer.theory_session.coverage_complete"), text)
        self.assertNotIn("Top-", text)
        self.assertEqual(source, frozen)

    def test_full_cartesian_coverage_does_not_claim_a_global_optimum(self) -> None:
        source = output_snapshot()
        source.update(domain_tuples="29", unseen_tuples="0", full_cartesian_covered=True)
        self.assertEqual(copy_theory_snapshot(source), source)
        text = format_gcsim_optimizer_go_theory_session_result({"success": True, "result": source})
        self.assertIn(tr("gcsim.optimizer.theory_session.coverage_complete"), text)
        self.assertIn(tr("gcsim.optimizer.theory_session.guidance"), text)
        self.assertIn(tr("gcsim.optimizer.theory_session.unbounded"), text)
        self.assertFalse(source["rules"]["full_search_optimality_proved"])
        self.assertEqual((source["search_status"], source["response_status"]), ("partial", "ordinary_verified"))

    def test_arbitrary_precision_domain_strings_are_retained_without_truncation(self) -> None:
        source = output_snapshot()
        self.assertEqual(source["total_found_tuples"], 27)
        self.assertEqual(len(source["unavailable"]), 2)
        # Independent decimal identity: 10**4400 - 29 ends in 71, with
        # 4398 leading nines. Do not reuse the consumer's bigint parser.
        source.update(domain_tuples="1" + "0" * 4400, unseen_tuples="9" * 4398 + "71")
        self.assertEqual(copy_theory_snapshot(source), source)

    def test_early_snapshot_remains_owned_across_progress_finish_cancel_and_failure(self) -> None:
        for outcome in ("finish", "cancel", "failure"):
            with self.subTest(outcome=outcome):
                events = []
                session = _session(callback=events.append)
                source = output_snapshot()
                session._consume_progress({"request_sha256": REQUEST_SHA, "theory_snapshot": source})
                early = session.last_snapshot
                early_event = events[0]["theory_snapshot"]
                source["provenance"]["domain"]["wearers"].clear()
                breadth = output_snapshot(2, phase="breadth_light")
                breadth["active_branch_work"]["completed_catalog_passes"] = 2
                session._consume_progress({"request_sha256": REQUEST_SHA, "theory_snapshot": breadth})
                terminal = output_snapshot(3, phase="deep_baseline", finished_early=outcome == "finish")

                def terminal_handoff():
                    result = session._store_snapshot(terminal)
                    if outcome == "finish":
                        session.request_finish()
                        return {"success": True, "status": "success", "result": result}
                    if outcome == "cancel":
                        session.cancel()
                        return {"success": True, "status": "success", "result": result}
                    return {"success": False, "status": "failed", "error_code": "synthetic_failure", "error": "fixture failure"}

                with patch("run_workspace.gcsim.optimizer_go_theory.GcsimOptimizerGoTheorySession.run", side_effect=terminal_handoff):
                    payload = session.run()
                self.assertEqual(early, output_snapshot())
                self.assertEqual(early_event, output_snapshot())
                retained = payload["result" if outcome == "finish" else "retained_snapshot"]
                self.assertEqual(retained, terminal)
                retained["pending"][0]["witness45"]["Lines"][0][0].clear()
                events[1]["theory_snapshot"]["co_leaders"][0]["aliases"].clear()
                self.assertEqual(session.last_snapshot, terminal)
                self.assertEqual(early, output_snapshot())
                self.assertEqual(payload["success"], outcome == "finish")
                if outcome != "finish":
                    self.assertNotIn("result", payload)

    def test_failure_discards_success_result_and_does_not_mutate_parent_payload(self) -> None:
        session = _session()
        session._store_snapshot(output_snapshot())
        parent_payload = {
            "success": False, "status": "success", "error_code": "fixture_error",
            "error": "fixture failure", "result": output_snapshot(2),
            "adapter_timings": {"terminal_status": "success"},
        }
        frozen = deepcopy(parent_payload)
        with patch("run_workspace.gcsim.optimizer_go_theory.GcsimOptimizerGoTheorySession.run", return_value=parent_payload):
            payload = session.run()
        self.assertEqual(parent_payload, frozen)
        self.assertEqual((payload["success"], payload["status"]), (False, "failed"))
        self.assertEqual(payload["adapter_timings"]["terminal_status"], "failed")
        self.assertNotIn("result", payload)
        self.assertEqual(payload["retained_snapshot"], output_snapshot())
        text = format_gcsim_optimizer_go_theory_session_result(payload)
        self.assertTrue(text.startswith(tr("gcsim.optimizer.theory_failed")))
        self.assertIn(tr("gcsim.optimizer.theory_session.retained"), text)
        self.assertNotIn(tr("gcsim.optimizer.theory_session.title"), text)

    def test_error_code_cannot_promote_a_retained_snapshot_to_success(self) -> None:
        session = _session()
        session._store_snapshot(output_snapshot())
        contradictory = {
            "success": True, "status": "success", "error_code": "fixture_error",
            "error": "fixture failure", "result": output_snapshot(2),
            "retained_snapshot": output_snapshot(),
        }
        with patch("run_workspace.gcsim.optimizer_go_theory.GcsimOptimizerGoTheorySession.run", return_value=contradictory):
            payload = session.run()
        self.assertEqual((payload["success"], payload["status"]), (False, "failed"))
        self.assertNotIn("result", payload)
        self.assertEqual(payload["retained_snapshot"], output_snapshot())
        text = format_gcsim_optimizer_go_theory_session_result(contradictory)
        self.assertTrue(text.startswith(tr("gcsim.optimizer.theory_failed")))
        self.assertIn(tr("gcsim.optimizer.theory_session.retained"), text)

    def test_malformed_or_duplicate_output_cannot_replace_a_legal_snapshot(self) -> None:
        invalid = []
        for field, value in (("formula_dps", "1000"), ("deficit_percent", True), ("refinement_level", -1)):
            snapshot = output_snapshot(2)
            snapshot["co_leaders"][0][field] = value
            invalid.append((field, snapshot))
        for field, value in (("found_group_tuples", 20), ("total_found_families", -1), ("sensitivity_group_tuples", 22), ("unseen_tuples", "-1"), ("full_cartesian_covered", True)):
            snapshot = output_snapshot(2)
            snapshot[field] = value
            invalid.append((field, snapshot))
        for name, change in (
            ("duplicate family", lambda s: s["pending"][0].update(family=s["co_leaders"][0]["family"])),
            ("duplicate candidate", lambda s: (s["pending"][0].update(family=s["co_leaders"][0]["family"]), s["pending"][0]["measurement"].update(candidate_sha256=s["co_leaders"][0]["measurement"]["candidate_sha256"]))),
            ("missing context", lambda s: s["co_leaders"][0]["aliases"][0].pop("context_sha256")),
            ("missing initial lines", lambda s: s["co_leaders"][0]["witness45"]["Lines"][0][0].clear()),
            ("missing allocation wearer", lambda s: s["co_leaders"][0]["allocations"].pop()),
            ("missing package wearer", lambda s: s["co_leaders"][0]["aliases"][0]["packages"].pop()),
            ("missing pending reason", lambda s: s["pending"][0].pop("reason")),
            ("uncertainty string", lambda s: s["co_leaders"][0]["aliases"][0].update(uncertainty="source limitation")),
            ("mismatched witness units", lambda s: s["co_leaders"][0]["allocations"][0]["substats"][3].update(roll_units=44)),
            ("nonquarter upgrade", lambda s: s["co_leaders"][0]["witness45"]["Upgrades"][0][0].__setitem__(0, 1.1)),
        ):
            snapshot = output_snapshot(2)
            change(snapshot)
            invalid.append((name, snapshot))
        mixed_cohort = output_snapshot(2)
        mixed_cohort["pending"][0]["measurement"]["frame_sha256"] = "f" * 64
        refresh_measurement_identity(mixed_cohort["pending"][0])
        invalid.append(("mixed measurement cohort", mixed_cohort))
        wrong_fidelity = output_snapshot(2)
        wrong_fidelity["pending"][0]["measurement"]["iterations"] = 499
        invalid.append(("mixed measurement iterations", wrong_fidelity))
        events = []
        session = _session(callback=events.append)
        session._consume_progress({"request_sha256": REQUEST_SHA, "theory_snapshot": output_snapshot()})
        for name, snapshot in invalid:
            with self.subTest(defect=name):
                with self.assertRaises(GcsimOptimizerGoError) as raised:
                    copy_theory_snapshot(snapshot)
                self.assertEqual(raised.exception.code, "theory_snapshot_invalid")
                session._consume_progress({"request_sha256": REQUEST_SHA, "theory_snapshot": snapshot})
                self.assertEqual(session.last_snapshot, output_snapshot())
        self.assertEqual(len(events), 1)

    @unittest.skipUnless(os.environ.get("GTT_THEORY_OUTPUT_EXPORT"), "Native public output export not supplied.")
    def test_managed_native_public_output_survives_the_python_consumer(self) -> None:
        # A serial native gate supplies this public synthetic snapshot. No engine
        # capture, account input, or native grouping import is needed here.
        source = json.loads(Path(os.environ["GTT_THEORY_OUTPUT_EXPORT"]).read_text(encoding="utf-8"))
        copied = copy_theory_snapshot(source)
        self.assertEqual(copied, source)
        self.assertGreater(len(copied["co_leaders"]), 5)
        text = format_gcsim_optimizer_go_theory_session_result({"success": True, "result": copied})
        for row in source["co_leaders"] + source["pending"]:
            for alias in row["aliases"]:
                self.assertEqual(text.count(tr("gcsim.optimizer.theory_session.choice").format(key=alias["tuple_key"])), 1)
        copied["co_leaders"][0]["witness45"]["Upgrades"][0][0][0] = 999
        self.assertNotEqual(copied, source)


if __name__ == "__main__":
    unittest.main()

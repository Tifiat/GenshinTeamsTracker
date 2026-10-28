"""Backend-only smoke for the Free Draft v0 local controller API."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from typing import Any, Mapping

from .account_deck_export import (
    AccountDeckExportOptions,
    LocalAccountSQLiteDeckDataProvider,
)
from .free_draft_controller import FreeDraftController
from .full_loop_smoke import DEFAULT_PLAYER_1_DECK_PATH, DEFAULT_PLAYER_2_DECK_PATH
from .schedule import PVP_SEATS, SEAT_PLAYER_1, SEAT_PLAYER_2


class FreeDraftControllerSmokeError(RuntimeError):
    """Raised when the deterministic controller smoke cannot complete."""


@dataclass(frozen=True, slots=True)
class FreeDraftControllerSmokeReport:
    source_mode: str
    initial_projection: Mapping[str, Any]
    final_projection: Mapping[str, Any]
    initial_board: Mapping[str, Any]
    after_actions_board: Mapping[str, Any]
    final_board: Mapping[str, Any]
    bundle_verification: Mapping[str, Any]
    bundle_session_id: str
    step_demo: tuple[Mapping[str, Any], ...] = ()
    issue_codes: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return (
            self.final_projection["status"]["draft_finished"]
            and self.final_projection["status"]["assignments_ready"]
            and self.final_projection["status"]["result_ready"]
            and bool(self.bundle_verification.get("ready"))
            and not self.issue_codes
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "source_mode": self.source_mode,
            "initial_projection": _compact_projection_report(self.initial_projection),
            "final_projection": _compact_projection_report(self.final_projection),
            "initial_board": _compact_board_report(self.initial_board),
            "after_actions_board": _compact_board_report(self.after_actions_board),
            "final_board": _compact_board_report(self.final_board),
            "bundle": {
                "session_id": self.bundle_session_id,
                "verification": dict(self.bundle_verification),
            },
            "step_demo": [dict(item) for item in self.step_demo],
            "issue_codes": list(self.issue_codes),
        }


def run_free_draft_controller_smoke(
    *,
    use_account: bool = False,
    include_step_demo: bool = False,
) -> FreeDraftControllerSmokeReport:
    controller = (
        FreeDraftController.from_account_export(
            provider=LocalAccountSQLiteDeckDataProvider(),
            options=AccountDeckExportOptions(),
        )
        if use_account
        else FreeDraftController.from_deck_files(
            DEFAULT_PLAYER_1_DECK_PATH,
            DEFAULT_PLAYER_2_DECK_PATH,
        )
    )
    if not controller.state.setup_ready:
        raise FreeDraftControllerSmokeError(
            f"Controller setup is not ready: {list(controller.issue_codes())}"
        )

    initial_projection = controller.to_projection().to_dict()
    initial_board = controller.to_board_dict()
    after_actions_board = _board_after_demo_actions(controller, max_actions=2)
    step_demo = (
        _run_step_demo(controller, max_steps=4) if include_step_demo else ()
    )
    controller.complete_draft_with_first_legal_targets()
    controller.assign_deterministic_teams_and_weapons()
    controller.set_deterministic_timers()
    bundle = controller.build_session_bundle()
    verification = controller.verify_session_bundle().to_dict()
    return FreeDraftControllerSmokeReport(
        source_mode="account" if use_account else "synthetic",
        initial_projection=initial_projection,
        final_projection=controller.to_projection().to_dict(),
        initial_board=initial_board,
        after_actions_board=after_actions_board,
        final_board=controller.to_board_dict(),
        bundle_verification=verification,
        bundle_session_id=bundle.session_id,
        step_demo=step_demo,
        issue_codes=controller.issue_codes(),
    )


def format_free_draft_controller_smoke_report(
    report: FreeDraftControllerSmokeReport,
) -> str:
    initial = report.initial_board
    after_actions = report.after_actions_board
    final = report.final_board
    system = final["draft_system"]
    initial_requirement = initial["current_requirement"] or {}
    progress = final["progress"]
    pools = final["global_pools"]
    result = final["summary"]["result"] or {}
    issue_codes = ", ".join(report.issue_codes) or "none"
    step_lines = [
        (
            "Step demo: "
            f"{item['before']['active_seat']} {item['before']['expected_action_type']} "
            f"{item['target_id']} -> "
            f"{item['after']['active_seat'] if item['after'] else 'complete'} "
            f"{item['after']['expected_action_type'] if item['after'] else ''}"
        ).rstrip()
        for item in report.step_demo
    ]
    p1_picks = len(pools["player_1_picked_ids"])
    p2_picks = len(pools["player_2_picked_ids"])
    return "\n".join(
        (
            "PvP Free Draft board/controller smoke",
            (
                "Draft system: "
                f"{system['system_id']} v{system['version']} "
                f"({system['display_name']})"
            ),
            f"Deck source mode: {report.source_mode}",
            (
                "Initial requirement: "
                f"{initial_requirement.get('phase', '')} "
                f"{initial_requirement.get('active_seat', '')} "
                f"{initial_requirement.get('expected_action_type', '')}"
            ),
            f"Initial legal targets: {initial['progress']['legal_target_count']}",
            f"Initial card statuses: {_first_card_statuses(initial)}",
            (
                "After 2 actions: "
                f"legal_targets={after_actions['progress']['legal_target_count']}; "
                f"{_first_card_statuses(after_actions)}"
            ),
            (
                "Actions: "
                f"{progress['actions_accepted']}/"
                f"{progress['actions_total_expected']}, "
                f"draft_finished={str(final['status']['draft_finished']).lower()}"
            ),
            _seat_line(final, SEAT_PLAYER_1),
            _seat_line(final, SEAT_PLAYER_2),
            (
                "Pools: "
                f"bans={len(pools['banned'])}, "
                f"picks={SEAT_PLAYER_1}:{p1_picks}, {SEAT_PLAYER_2}:{p2_picks}"
            ),
            (
                "Assignments: "
                f"teams={_total_team_count(final)}, "
                f"weapons={_total_weapon_count(final)}"
            ),
            (
                "Result: "
                f"status={result.get('status', 'not_run')}, "
                f"winner={result.get('winner_seat')}, "
                f"diff={result.get('seconds_difference', 0)}s"
            ),
            f"Action log rows: {len(final['action_log'])}",
            (
                "Bundle verification: "
                f"{str(report.bundle_verification.get('ready')).lower()}"
            ),
            f"Issue codes: {issue_codes}",
            *step_lines,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run backend-only Free Draft controller smoke.",
    )
    parser.add_argument("--json", action="store_true", help="Print compact JSON.")
    parser.add_argument(
        "--account",
        action="store_true",
        help="Use local account export and an independent player_2 copy.",
    )
    parser.add_argument(
        "--step-demo",
        action="store_true",
        help="Print the first few manual controller transitions.",
    )
    args = parser.parse_args(argv)

    try:
        report = run_free_draft_controller_smoke(
            use_account=args.account,
            include_step_demo=args.step_demo,
        )
    except Exception as exc:
        print(f"PvP Free Draft controller smoke failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_free_draft_controller_smoke_report(report))
    return 0 if report.ready else 1


def _board_after_demo_actions(
    controller: FreeDraftController,
    *,
    max_actions: int,
) -> Mapping[str, Any]:
    demo = FreeDraftController.from_decks(
        controller.state.player_1_deck,
        controller.state.player_2_deck,
        draft_system=controller.state.draft_system,
        source_mode=controller.state.source_mode,
    )
    for _ in range(max_actions):
        legal = demo.get_legal_targets()
        if not legal:
            break
        demo.apply_current_action(legal[0].character_id)
    return demo.to_board_dict()


def _run_step_demo(
    controller: FreeDraftController,
    *,
    max_steps: int,
) -> tuple[Mapping[str, Any], ...]:
    rows: list[Mapping[str, Any]] = []
    for _ in range(max_steps):
        before = controller.to_projection().to_dict()["current_requirement"]
        legal = controller.get_legal_targets()
        if before is None or not legal:
            break
        target_id = legal[0].character_id
        action = controller.apply_current_action(target_id)
        after = controller.to_projection().to_dict()["current_requirement"]
        rows.append(
            {
                "action_id": action.action_id,
                "sequence": action.sequence,
                "before": before,
                "target_id": target_id,
                "after": after,
            }
        )
    return tuple(rows)


def _seat_line(projection: Mapping[str, Any], seat: str) -> str:
    progress = projection["progress"]["per_seat"][seat]
    return (
        f"{seat}: "
        f"bans={progress['actual_bans']}/{progress['expected_bans']}, "
        f"picks={progress['actual_picks']}/{progress['expected_picks']}"
    )


def _first_card_statuses(projection: Mapping[str, Any], *, per_seat: int = 2) -> str:
    parts: list[str] = []
    for seat in PVP_SEATS:
        cards = projection["seats"][seat]["cards"]
        for card in cards[:per_seat]:
            parts.append(f"{seat}:{card['character_id']}={card['status']}")
    return ", ".join(parts) or "none"


def _total_team_count(projection: Mapping[str, Any]) -> int:
    return sum(
        projection["summary"]["assignments"][seat]["team_count"]
        for seat in PVP_SEATS
    )


def _total_weapon_count(projection: Mapping[str, Any]) -> int:
    return sum(
        projection["summary"]["assignments"][seat]["weapon_assignment_count"]
        for seat in PVP_SEATS
    )


def _compact_projection_report(projection: Mapping[str, Any]) -> dict[str, Any]:
    assignments = projection.get("assignments", {})
    teams = assignments.get("teams", {}) if isinstance(assignments, Mapping) else {}
    weapons = assignments.get("weapons", {}) if isinstance(assignments, Mapping) else {}
    result = projection.get("result")
    return {
        "draft_system": dict(projection["draft_system"]),
        "status": dict(projection["status"]),
        "current_requirement": (
            dict(projection["current_requirement"])
            if projection.get("current_requirement") is not None
            else None
        ),
        "progress": dict(projection["progress"]),
        "seats": dict(projection["seats"]),
        "draft_state": dict(projection["draft_state"]),
        "legal_target_count": len(projection.get("legal_targets", ())),
        "assignments": {
            "team_counts": {
                seat: teams.get(seat, {}).get("team_count", 0)
                for seat in PVP_SEATS
            },
            "weapon_assignment_counts": {
                seat: weapons.get(seat, {}).get("assignment_count", 0)
                for seat in PVP_SEATS
            },
        },
        "result": _compact_result_report(result),
        "issue_codes": list(projection.get("issue_codes", ())),
    }


def _compact_board_report(projection: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "variant": projection["variant"],
        "draft_system": dict(projection["draft_system"]),
        "status": dict(projection["status"]),
        "current_requirement": (
            dict(projection["current_requirement"])
            if projection.get("current_requirement") is not None
            else None
        ),
        "progress": dict(projection["progress"]),
        "card_status_samples": {
            seat: [
                {
                    "character_id": card["character_id"],
                    "status": card["status"],
                    "is_current_legal_target": card["is_current_legal_target"],
                }
                for card in projection["seats"][seat]["cards"][:4]
            ]
            for seat in PVP_SEATS
        },
        "global_pools": dict(projection["global_pools"]),
        "action_log_count": len(projection["action_log"]),
        "timeline": [
            {
                "step_index": step["step_index"],
                "status": step["status"],
                "actions_done": step["actions_done"],
                "actions_total": step["actions_total"],
            }
            for step in projection["timeline"]
        ],
        "summary": dict(projection["summary"]),
        "issue_codes": list(projection.get("issue_codes", ())),
    }


def _compact_result_report(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return {
        "status": value.get("status"),
        "winner_seat": value.get("winner_seat"),
        "seconds_difference": value.get("seconds_difference"),
        "totals": dict(value.get("totals", {})),
    }


if __name__ == "__main__":
    raise SystemExit(main())

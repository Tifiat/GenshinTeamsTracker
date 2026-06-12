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
            "initial_projection": dict(self.initial_projection),
            "final_projection": dict(self.final_projection),
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
        bundle_verification=verification,
        bundle_session_id=bundle.session_id,
        step_demo=step_demo,
        issue_codes=controller.issue_codes(),
    )


def format_free_draft_controller_smoke_report(
    report: FreeDraftControllerSmokeReport,
) -> str:
    initial = report.initial_projection
    final = report.final_projection
    system = final["draft_system"]
    initial_requirement = initial["current_requirement"] or {}
    progress = final["progress"]
    draft_state = final["draft_state"]
    result = final["result"] or {}
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
    return "\n".join(
        (
            "PvP Free Draft controller smoke",
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
            (
                "Actions: "
                f"{progress['actions_accepted']}/"
                f"{progress['actions_total_expected']}, "
                f"draft_finished={str(final['status']['draft_finished']).lower()}"
            ),
            _seat_line(final, SEAT_PLAYER_1),
            _seat_line(final, SEAT_PLAYER_2),
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
            f"State hash: {draft_state['state_hash']}",
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


def _total_team_count(projection: Mapping[str, Any]) -> int:
    return sum(
        projection["assignments"]["teams"][seat]["team_count"]
        for seat in PVP_SEATS
    )


def _total_weapon_count(projection: Mapping[str, Any]) -> int:
    return sum(
        projection["assignments"]["weapons"][seat]["assignment_count"]
        for seat in PVP_SEATS
    )


if __name__ == "__main__":
    raise SystemExit(main())

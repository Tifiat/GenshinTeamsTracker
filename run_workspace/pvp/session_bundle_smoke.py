"""Backend-only smoke for PvP session bundle roundtrip and replay verification."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .account_full_loop_smoke import run_account_full_loop_smoke
from .full_loop_smoke import run_default_full_loop_smoke
from .session_bundle import (
    PvpSessionBundle,
    PvpSessionBundleVerificationReport,
    build_session_bundle_from_account_full_loop_report,
    build_session_bundle_from_full_loop_report,
    calculate_bundle_hash,
    default_session_bundle_output_path,
    load_session_bundle_from_json_text,
    session_bundle_to_json_text,
    verify_session_bundle,
    write_session_bundle,
)


class SessionBundleSmokeError(RuntimeError):
    """Raised when the deterministic session bundle smoke cannot complete."""


@dataclass(frozen=True, slots=True)
class SessionBundleSmokeReport:
    source_mode: str
    bundle: PvpSessionBundle
    roundtrip_bundle_hash: str
    verification_report: PvpSessionBundleVerificationReport
    wrote_file: bool = False
    output_path: str = ""

    @property
    def ready(self) -> bool:
        return self.verification_report.ready and (
            calculate_bundle_hash(self.bundle) == self.roundtrip_bundle_hash
        )

    def to_dict(self) -> dict[str, Any]:
        result = self.bundle.match_result
        return {
            "ready": self.ready,
            "source_mode": self.source_mode,
            "draft_system": self.bundle.draft_system.to_dict(),
            "session_id": self.bundle.session_id,
            "schedule_steps_count": len(self.bundle.schedule.steps),
            "action_count": len(self.bundle.accepted_actions),
            "state_hash": self.bundle.final_state_hash,
            "replay_verified": self.verification_report.ready,
            "roundtrip_hash_matches": (
                calculate_bundle_hash(self.bundle) == self.roundtrip_bundle_hash
            ),
            "teams_assigned": {
                seat: sum(len(team.character_ids) for team in assignment.teams)
                for seat, assignment in self.bundle.team_assignments.items()
            },
            "weapons_assigned": {
                seat: len(assignment.assignments)
                for seat, assignment in self.bundle.weapon_assignments.items()
            },
            "result": {
                "status": result.status,
                "winner_seat": result.winner_seat,
                "seconds_difference": result.seconds_difference,
            },
            "bundle_validation": self.verification_report.to_dict(),
            "wrote_file": self.wrote_file,
            "output_path": self.output_path,
        }


def run_session_bundle_smoke(
    *,
    use_account: bool = False,
    write: bool = False,
    output_path: str | Path | None = None,
) -> SessionBundleSmokeReport:
    source_mode = "account" if use_account else "synthetic"
    if use_account:
        source_report = run_account_full_loop_smoke()
        if not source_report.ready:
            raise SessionBundleSmokeError("Account full-loop smoke is not ready.")
        bundle = build_session_bundle_from_account_full_loop_report(source_report)
    else:
        source_report = run_default_full_loop_smoke()
        bundle = build_session_bundle_from_full_loop_report(source_report)

    roundtripped = load_session_bundle_from_json_text(session_bundle_to_json_text(bundle))
    verification = verify_session_bundle(roundtripped)
    roundtrip_hash = calculate_bundle_hash(roundtripped)

    wrote_file = False
    final_output_path = ""
    if write:
        if not verification.ready:
            raise SessionBundleSmokeError("Refusing to write an invalid session bundle.")
        target = (
            Path(output_path)
            if output_path is not None
            else default_session_bundle_output_path(
                created_at_utc=bundle.created_at_utc,
                session_id=bundle.session_id,
            )
        )
        final_output_path = str(write_session_bundle(roundtripped, target))
        wrote_file = True

    return SessionBundleSmokeReport(
        source_mode=source_mode,
        bundle=roundtripped,
        roundtrip_bundle_hash=roundtrip_hash,
        verification_report=verification,
        wrote_file=wrote_file,
        output_path=final_output_path,
    )


def format_session_bundle_smoke_report(report: SessionBundleSmokeReport) -> str:
    bundle = report.bundle
    result = bundle.match_result
    validation_codes = ", ".join(report.verification_report.issue_codes()) or "none"
    output_line = (
        f"Output: {report.output_path}"
        if report.wrote_file
        else "Output: dry-run, no files written"
    )
    return "\n".join(
        (
            "PvP session bundle smoke",
            (
                "Draft system: "
                f"{bundle.draft_system.system_id} v{bundle.draft_system.version}"
            ),
            f"Deck source mode: {report.source_mode}",
            (
                "Schedule/actions: "
                f"{len(bundle.schedule.steps)} steps, {len(bundle.accepted_actions)} actions"
            ),
            f"State hash: {bundle.final_state_hash}",
            f"Replay verified: {str(report.verification_report.ready).lower()}",
            (
                "Assignments: "
                f"teams={_assigned_team_slots(bundle)}, "
                f"weapons={_assigned_weapon_slots(bundle)}"
            ),
            (
                "Result: "
                f"status={result.status}, winner={result.winner_seat}, "
                f"diff={result.seconds_difference}s"
            ),
            (
                "Bundle validation: "
                f"status={report.verification_report.status}, "
                f"issues={validation_codes}"
            ),
            output_line,
        )
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run backend-only PvP session bundle roundtrip/replay smoke.",
    )
    parser.add_argument("--json", action="store_true", help="Print compact JSON.")
    parser.add_argument(
        "--account",
        action="store_true",
        help="Use local account full-loop smoke instead of synthetic fixtures.",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write the bundle JSON under generated/private data/pvp/sessions/.",
    )
    parser.add_argument("--output", default="", help="Optional output JSON path.")
    args = parser.parse_args(argv)

    try:
        report = run_session_bundle_smoke(
            use_account=args.account,
            write=bool(args.write or args.output),
            output_path=args.output or None,
        )
    except Exception as exc:
        print(f"PvP session bundle smoke failed: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(format_session_bundle_smoke_report(report))
    return 0 if report.ready else 1


def _assigned_team_slots(bundle: PvpSessionBundle) -> int:
    return sum(
        len(team.character_ids)
        for assignment in bundle.team_assignments.values()
        for team in assignment.teams
    )


def _assigned_weapon_slots(bundle: PvpSessionBundle) -> int:
    return sum(
        len(assignment.assignments)
        for assignment in bundle.weapon_assignments.values()
    )


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from run_workspace.gcsim.trace_equation.same_context_acceptance import (
    build_current_same_context_acceptance_input,
    run_same_context_acceptance,
)


ROOT = Path(__file__).resolve().parents[2]
ENGINE_STORE = ROOT / ".codex_tmp" / "forwarded_attack_v1_store"
DATABASE_PATH = ROOT / "data" / "artifacts.db"


def main() -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = ROOT / ".codex_tmp" / f"same_context_acceptance_{stamp}"
    acceptance_input = build_current_same_context_acceptance_input(
        engine_store_dir=ENGINE_STORE,
        database_path=DATABASE_PATH,
    )
    result = run_same_context_acceptance(
        acceptance_input,
        run_dir=run_dir,
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

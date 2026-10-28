from __future__ import annotations

import json
from pathlib import Path
import unittest

from run_workspace.gcsim.optimizer_go_contracts import (
    GCSIM_OPTIMIZER_GO_COMPACT_IR_KIND,
    GCSIM_OPTIMIZER_GO_PROGRESS_KIND,
    GCSIM_OPTIMIZER_GO_REQUEST_KIND,
    GCSIM_OPTIMIZER_GO_RESULT_KIND,
    canonical_json_bytes,
    canonical_sha256,
    load_contract,
)


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "tests" / "fixtures" / "gcsim_optimizer_go_v1"


class GoOptimizerContractTests(unittest.TestCase):
    def test_shared_fixture_hashes_match_python_canonical_json(self) -> None:
        expected = json.loads(
            (FIXTURES / "canonical_sha256_v1.json").read_text(encoding="utf-8")
        )
        for filename, expected_sha256 in expected["files"].items():
            payload = json.loads((FIXTURES / filename).read_text(encoding="utf-8"))
            self.assertEqual(canonical_sha256(payload), expected_sha256, filename)
            self.assertEqual(
                json.loads(canonical_json_bytes(payload)),
                payload,
                filename,
            )

    def test_shared_fixture_headers_are_the_accepted_v1_contracts(self) -> None:
        expected_kinds = {
            "request_v1.json": GCSIM_OPTIMIZER_GO_REQUEST_KIND,
            "progress_v1.json": GCSIM_OPTIMIZER_GO_PROGRESS_KIND,
            "compact_ir_v1.json": GCSIM_OPTIMIZER_GO_COMPACT_IR_KIND,
            "result_v1.json": GCSIM_OPTIMIZER_GO_RESULT_KIND,
        }
        for filename, kind in expected_kinds.items():
            payload = load_contract(FIXTURES / filename, expected_kind=kind)
            self.assertEqual(payload["schema_kind"], kind)

    def test_fixture_arrays_are_already_canonical(self) -> None:
        request = json.loads((FIXTURES / "request_v1.json").read_text("utf-8"))
        self.assertEqual(
            [artifact["artifact_id"] for artifact in request["artifacts"]],
            sorted(artifact["artifact_id"] for artifact in request["artifacts"]),
        )
        self.assertEqual(
            [wearer["wearer_key"] for wearer in request["wearers"]],
            sorted(wearer["wearer_key"] for wearer in request["wearers"]),
        )
        compact = json.loads((FIXTURES / "compact_ir_v1.json").read_text("utf-8"))
        self.assertEqual(
            [member["seed"] for member in compact["members"]],
            sorted(member["seed"] for member in compact["members"]),
        )

    def test_go_sources_do_not_import_gcsim_internals(self) -> None:
        module = ROOT / "native" / "gcsim_optimizer"
        offenders = []
        for path in module.rglob("*.go"):
            if "gcsim/internal" in path.read_text(encoding="utf-8"):
                offenders.append(str(path.relative_to(ROOT)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()

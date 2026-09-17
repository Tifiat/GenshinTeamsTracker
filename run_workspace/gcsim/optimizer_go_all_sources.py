"""Read-only engine-bound source envelope for native All Sets discovery.

No gameplay formulas, search, account writes or simulation in this adapter.
The full original source tree is verified once before handing source texts to
Go; matching a catalog label or binary path alone is not sufficient provenance.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping

from .artifact_set_catalog import load_gcsim_artifact_set_catalog
from .source_manifest_build import canonical_json, compute_patched_source_tree_sha256


def prepare_all_set_effect_sources(engine_root: str | Path, binding: Mapping[str, object]) -> dict:
    root = Path(engine_root).resolve()
    binary = Path(str(binding["binary_path"])).resolve()
    if binary.parent.parent != root:
        raise ValueError("effect sources are not from the bound engine root")
    if "gtt_effect_inputs_v1" not in binding.get("capabilities", ()):
        raise ValueError("All Sets effect-input capability is absent")
    binary_sha = hashlib.sha256(binary.read_bytes()).hexdigest()
    if binary_sha != binding["artifact_sha256"]:
        raise ValueError("bound engine binary changed")
    manifest = json.loads((root / "build/gtt-source-manifest-body.json").read_bytes())
    manifest_sha = hashlib.sha256(canonical_json(manifest).encode()).hexdigest()
    if manifest_sha != binding["source_manifest_sha256"]:
        raise ValueError("bound source manifest changed")
    if compute_patched_source_tree_sha256(root) != manifest["patched_source_tree_sha256"]:
        raise ValueError("engine sources differ from the built manifest")
    catalog = load_gcsim_artifact_set_catalog(root)

    def text(relative: str) -> dict[str, str]:
        path = (root / relative).resolve()
        path.relative_to(root)
        data = path.read_bytes()
        return {"text": data.decode("utf-8"), "sha256": hashlib.sha256(data).hexdigest()}

    items = []
    for entry in catalog.sets:
        if entry.max_rarity != 5 or not entry.two_piece_modeled:
            continue
        items.append({"key": entry.key, "four_piece_modeled": entry.four_piece_modeled,
                      "sources": {name: text(name) for name in entry.source_files if name.endswith(".go")}})
    return {"schema_version": 1, "engine_sha256": binary_sha,
            "source_manifest_sha256": manifest_sha, "catalog_sha256": catalog.source_fingerprint,
            "stat_source": text("pkg/core/attributes/stats.go"),
            "attack_source": text("pkg/core/attacks/attack.go"),
            "element_source": text("pkg/core/attributes/element.go"),
            "context_source": text("pkg/enemy/damage.go"), "items": items}

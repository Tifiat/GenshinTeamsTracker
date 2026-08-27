from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from run_workspace.gcsim.engine_store import (
    GcsimEngineInstallation,
    GcsimEngineManifest,
)
from run_workspace.gcsim.optimizer_engine_context import (
    build_gcsim_optimizer_engine_context,
)
from run_workspace.gcsim.optimizer_oracle import GcsimOptimizerOracleScore
from run_workspace.gcsim.optimizer_theoretical_oracle import (
    GcsimOptimizerTheoreticalFourPieceOracleWearerDomain,
    run_gcsim_optimizer_theoretical_four_piece_oracle,
)
from run_workspace.gcsim.optimizer_two_piece_signatures import (
    GcsimOptimizerTwoPieceSignatureError,
    GcsimOptimizerTwoPieceProofKind,
    build_gcsim_optimizer_theoretical_pair_domain,
    build_gcsim_optimizer_two_piece_effect_descriptors,
)


class GcsimOptimizerTwoPieceSignaturesTests(unittest.TestCase):
    def test_typed_domain_rejects_version_digest_binding_and_coverage_tampering(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            domain = build_gcsim_optimizer_theoretical_pair_domain(
                _context(Path(tmp))
            )

        with self.assertRaisesRegex(
            GcsimOptimizerTwoPieceSignatureError,
            "pair-domain schema",
        ):
            replace(domain, schema_version=999)
        with self.assertRaisesRegex(
            GcsimOptimizerTwoPieceSignatureError,
            "engine/catalog binding",
        ):
            replace(domain, engine_binding_sha256="f" * 64)
        with self.assertRaisesRegex(
            GcsimOptimizerTwoPieceSignatureError,
            "effect signature",
        ):
            replace(
                domain.descriptors[0],
                effect_signature_sha256="f" * 64,
            )
        with self.assertRaisesRegex(
            GcsimOptimizerTwoPieceSignatureError,
            "pair signature",
        ):
            replace(
                domain.groups[0],
                pair_signature_sha256="f" * 64,
            )
        alias_index = next(
            index
            for index, group in enumerate(domain.groups)
            if len(group.concrete_aliases) > 1
        )
        original = domain.groups[alias_index]
        narrowed = replace(
            original,
            concrete_aliases=(original.representative,),
        )
        groups = list(domain.groups)
        groups[alias_index] = narrowed
        with self.assertRaisesRegex(
            GcsimOptimizerTwoPieceSignatureError,
            "descriptor domain",
        ):
            replace(
                domain,
                groups=tuple(groups),
                concrete_pair_count=domain.concrete_pair_count - 1,
            )

    def test_wrong_receiver_and_reachable_outside_mutation_fail_closed(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            wrong_receiver = {
                item.set_key: item
                for item in build_gcsim_optimizer_two_piece_effect_descriptors(
                    _context(Path(tmp), beta_receiver="other")
                )
            }
        self.assertEqual(
            wrong_receiver["beta"].proof_kind,
            GcsimOptimizerTwoPieceProofKind.UNIQUE_SOURCE,
        )

        with tempfile.TemporaryDirectory() as tmp:
            outside_mutation = {
                item.set_key: item
                for item in build_gcsim_optimizer_two_piece_effect_descriptors(
                    _context(Path(tmp), beta_outside_side_effect=True)
                )
            }
        self.assertEqual(
            outside_mutation["beta"].proof_kind,
            GcsimOptimizerTwoPieceProofKind.UNIQUE_SOURCE,
        )

    def test_modifier_key_collision_is_part_of_pair_proof(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            domain = build_gcsim_optimizer_theoretical_pair_domain(
                _context(
                    Path(tmp),
                    alpha_modifier_key="shared-2pc",
                    beta_modifier_key="shared-2pc",
                    gamma_stat="ATKP",
                    gamma_value="0.18",
                )
            )

        group_by_pair = {
            frozenset(
                (alias.set_a.gcsim_set_key, alias.set_b.gcsim_set_key)
            ): group
            for group in domain.groups
            for alias in group.concrete_aliases
        }
        same_key = group_by_pair[frozenset(("alpha", "beta"))]
        alpha_gamma = group_by_pair[frozenset(("alpha", "gamma"))]
        beta_gamma = group_by_pair[frozenset(("beta", "gamma"))]
        self.assertEqual(same_key.modifier_key_relation, "same_static_key")
        self.assertEqual(len(same_key.concrete_aliases), 1)
        self.assertEqual(
            alpha_gamma.modifier_key_relation,
            "distinct_static_keys",
        )
        self.assertIs(alpha_gamma, beta_gamma)
        self.assertNotEqual(
            same_key.pair_signature_sha256,
            alpha_gamma.pair_signature_sha256,
        )

    def test_same_modifier_key_pairs_never_alias_across_application_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            domain = build_gcsim_optimizer_theoretical_pair_domain(
                _context(
                    Path(tmp),
                    alpha_modifier_key="shared-2pc",
                    beta_modifier_key="shared-2pc",
                    gamma_modifier_key="shared-2pc",
                    gamma_stat="HPP",
                    gamma_value="0.20",
                )
            )

        colliding = tuple(
            group
            for group in domain.groups
            if group.modifier_key_relation == "same_static_key"
        )
        self.assertEqual(len(colliding), 3)
        self.assertTrue(all(len(group.concrete_aliases) == 1 for group in colliding))

    def test_full_pair_proof_serialization_keeps_descriptors_and_interaction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            domain = build_gcsim_optimizer_theoretical_pair_domain(
                _context(Path(tmp))
            )

        payload = domain.to_dict()
        self.assertEqual(len(payload["descriptors"]), len(domain.descriptors))
        self.assertIn("modifier_key", payload["descriptors"][0])
        self.assertIn("receiver_binding", payload["descriptors"][0])
        self.assertIn("effect_signature_pair", payload["groups"][0])
        self.assertIn("modifier_key_relation", payload["groups"][0])

    def test_reduced_pair_oracle_exhausts_coordinated_four_wearer_changes(self) -> None:
        from tests.run_workspace.gcsim.test_gcsim_optimizer_theoretical_oracle import (
            _domains,
        )

        with tempfile.TemporaryDirectory() as tmp:
            pair_domain = build_gcsim_optimizer_theoretical_pair_domain(
                _context(Path(tmp))
            )
            packages = tuple(
                group.representative for group in pair_domain.groups[:2]
            )
            domains = tuple(
                GcsimOptimizerTheoreticalFourPieceOracleWearerDomain(
                    wearer=source.wearer,
                    packages=packages,
                    stat_states=(source.stat_states[0],),
                )
                for source in _domains()
            )

            result = run_gcsim_optimizer_theoretical_four_piece_oracle(
                domains,
                evaluator=lambda state: GcsimOptimizerOracleScore(
                    objective_name="pair_fixture_dps",
                    objective_value=sum(
                        1.0
                        for choice in state.choices
                        if choice.variant.package == packages[1]
                    ),
                    evidence_sha256=state.identity_sha256,
                ),
            )

        self.assertEqual(result.coverage.exhaustive_state_count, 16)
        self.assertEqual(result.winner.change_count_from_baseline, 4)

    def test_static_equal_effects_group_without_collapsing_concrete_aliases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = _context(Path(tmp))
            descriptors = build_gcsim_optimizer_two_piece_effect_descriptors(
                context
            )
            by_key = {item.set_key: item for item in descriptors}

            self.assertEqual(
                by_key["alpha"].proof_kind,
                GcsimOptimizerTwoPieceProofKind.STATIC_STAT,
            )
            self.assertEqual(
                by_key["alpha"].effect_signature_sha256,
                by_key["beta"].effect_signature_sha256,
            )
            self.assertNotEqual(
                by_key["alpha"].effect_signature_sha256,
                by_key["gamma"].effect_signature_sha256,
            )
            self.assertEqual(
                by_key["conditional"].proof_kind,
                GcsimOptimizerTwoPieceProofKind.UNIQUE_SOURCE,
            )

            domain = build_gcsim_optimizer_theoretical_pair_domain(context)

            self.assertEqual(domain.concrete_pair_count, 6)
            alias_group = next(
                group
                for group in domain.groups
                if {
                    frozenset(
                        (
                        item.set_a.gcsim_set_key,
                        item.set_b.gcsim_set_key,
                        )
                    )
                    for item in group.concrete_aliases
                }
                == {
                    frozenset(("alpha", "gamma")),
                    frozenset(("beta", "gamma")),
                }
            )
            self.assertEqual(len(alias_group.concrete_aliases), 2)
            self.assertEqual(alias_group.representative, alias_group.concrete_aliases[0])
            opaque_groups = tuple(
                group
                for group in domain.groups
                if any(
                    "conditional"
                    in {
                        alias.set_a.gcsim_set_key,
                        alias.set_b.gcsim_set_key,
                    }
                    for alias in group.concrete_aliases
                )
            )
            self.assertTrue(opaque_groups)
            self.assertTrue(
                all(
                    group.modifier_key_relation == "opaque_unique_source"
                    and len(group.concrete_aliases) == 1
                    for group in opaque_groups
                )
            )
            self.assertEqual(
                len(
                    {
                        item.identity_sha256
                        for group in domain.groups
                        for item in group.concrete_aliases
                    }
                ),
                6,
            )

    def test_parameterized_two_piece_effect_is_never_grouped_by_static_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            context = _context(Path(tmp), parameterized_beta=True)
            by_key = {
                item.set_key: item
                for item in build_gcsim_optimizer_two_piece_effect_descriptors(
                    context
                )
            }

            self.assertEqual(by_key["beta"].parameter_keys, ("stacks",))
            self.assertEqual(
                by_key["beta"].proof_kind,
                GcsimOptimizerTwoPieceProofKind.UNIQUE_SOURCE,
            )
            self.assertNotEqual(
                by_key["alpha"].effect_signature_sha256,
                by_key["beta"].effect_signature_sha256,
            )


def _context(
    root: Path,
    *,
    parameterized_beta: bool = False,
    beta_receiver: str = "char",
    beta_outside_side_effect: bool = False,
    alpha_modifier_key: str = "alpha-2pc",
    beta_modifier_key: str = "beta-2pc",
    gamma_modifier_key: str = "gamma-2pc",
    gamma_stat: str = "HPP",
    gamma_value: str = "0.20",
):
    artifact = root / "build" / "gtt-gcsim.exe"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"engine")
    for key, stat, value, modifier_key in (
        ("alpha", "ATKP", "0.18", alpha_modifier_key),
        ("beta", "ATKP", "0.18", beta_modifier_key),
        ("gamma", gamma_stat, gamma_value, gamma_modifier_key),
    ):
        parameter = (
            '\n    _ = param["stacks"]'
            if key == "beta" and parameterized_beta
            else ""
        )
        _write_set(
            root,
            key,
            _static_source(
                key,
                stat,
                value,
                parameter=parameter,
                modifier_key=modifier_key,
                receiver=(beta_receiver if key == "beta" else "char"),
                outside_side_effect=(
                    beta_outside_side_effect if key == "beta" else False
                ),
            ),
        )
    _write_set(
        root,
        "conditional",
        """
package conditional
func init() { core.RegisterSetFunc(keys.Conditional, NewSet) }
func NewSet(char *character.CharWrapper, count int) {
    if count >= 2 {
        char.AddAttackMod(character.AttackMod{})
    }
    if count >= 4 {}
}
""",
    )
    issues = (
        root
        / "ui"
        / "packages"
        / "docs"
        / "src"
        / "components"
        / "Issues"
        / "artifact_data.json"
    )
    issues.parent.mkdir(parents=True)
    issues.write_text(json.dumps({}), encoding="utf-8")
    optimizer = root / "pkg" / "optimization" / "substats.go"
    optimizer.parent.mkdir(parents=True)
    optimizer.write_text(
        "func load() { s.artifactSets4Star = []keys.Set{} }\n",
        encoding="utf-8",
    )
    manifest = GcsimEngineManifest(
        engine_id="engine",
        source_label="gcsim-v2.42.2",
        source_path=str(root),
        source_tree_hash="source",
        engine_tree_hash="",
        prepared_at_utc="2026-07-19T00:00:00+00:00",
        patch_backend="fixture",
        patch_count=0,
        metadata={
            "artifact_relative_path": "build/gtt-gcsim.exe",
            "artifact_version_stdout": "fixture-version",
        },
    )
    diagnostic = build_gcsim_optimizer_engine_context(
        GcsimEngineInstallation("engine", root, manifest),
        require_resealed=False,
    )
    sealed = replace(
        manifest,
        engine_tree_hash=diagnostic.engine_tree_sha256,
        metadata={
            **dict(manifest.metadata),
            "artifact_sha256": diagnostic.artifact_sha256,
        },
    )
    return build_gcsim_optimizer_engine_context(
        GcsimEngineInstallation("engine", root, sealed)
    )


def _write_set(root: Path, key: str, source: str) -> None:
    package = root / "internal" / "artifacts" / key
    package.mkdir(parents=True)
    (package / "config.yml").write_text(f"key: {key}\n", encoding="utf-8")
    (package / f"{key}.go").write_text(source, encoding="utf-8")


def _static_source(
    key: str,
    stat: str,
    value: str,
    *,
    parameter: str = "",
    modifier_key: str,
    receiver: str,
    outside_side_effect: bool,
) -> str:
    outside = (
        "\n    char.AddStatMod(character.StatMod{})"
        if outside_side_effect
        else ""
    )
    return f"""
package {key}
func init() {{ core.RegisterSetFunc(keys.{key.title()}, NewSet) }}
func NewSet(char *character.CharWrapper, count int, param map[string]int) {{
    if count >= 2 {{
        m := make([]float64, attributes.EndStatType)
        m[attributes.{stat}] = {value}
        {receiver}.AddStatMod(character.StatMod{{
            Base: modifier.NewBase("{modifier_key}", -1),
            AffectedStat: attributes.{stat},
            Amount: func() []float64 {{
                return m
            }},
        }})
    }}{outside}{parameter}
    if count >= 4 {{}}
}}
"""


if __name__ == "__main__":
    unittest.main()

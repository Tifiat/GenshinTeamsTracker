from __future__ import annotations

from dataclasses import replace
import unittest

from run_workspace.gcsim.artifact_set_catalog import (
    GcsimArtifactSetCapability,
)
from run_workspace.gcsim.optimizer_artifact_database import (
    GcsimOptimizerArtifactRecord,
)
from run_workspace.gcsim.optimizer_physical_package import (
    GcsimOptimizerPhysicalPackageRejectionReason,
    derive_gcsim_optimizer_target_from_physical_artifacts,
)
from run_workspace.gcsim.optimizer_product_contracts import (
    GCSIM_OPTIMIZER_ARTIFACT_SLOTS,
    GcsimFourPieceTargetPackage,
    GcsimOptimizerFourStarEligibilityOverride,
    GcsimOptimizerSetReference,
    GcsimOptimizerWearerIdentity,
    GcsimTwoPlusTwoTargetPackage,
)


class GcsimOptimizerPhysicalPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.wearer = GcsimOptimizerWearerIdentity(
            team_slot=1,
            account_character_id=1001,
            gcsim_character_key="alpha",
        )

    def test_four_plus_one_derives_strict_four_piece_target(self) -> None:
        result = self._derive(("A", "A", "A", "A", "B"))

        self.assertTrue(result.ready)
        self.assertIsInstance(result.package, GcsimFourPieceTargetPackage)
        assert isinstance(result.package, GcsimFourPieceTargetPackage)
        self.assertEqual(result.package.set_ref.set_uid, "A")
        self.assertEqual(dict(result.set_counts), {"A": 4, "B": 1})

    def test_five_same_set_derives_strict_four_piece_target(self) -> None:
        result = self._derive(("A",) * 5)

        self.assertTrue(result.ready)
        self.assertIsInstance(result.package, GcsimFourPieceTargetPackage)
        self.assertEqual(dict(result.set_counts), {"A": 5})

    def test_two_plus_two_plus_one_derives_pair(self) -> None:
        result = self._derive(("A", "A", "B", "B", "C"))

        self.assertTrue(result.ready)
        self.assertIsInstance(result.package, GcsimTwoPlusTwoTargetPackage)
        assert isinstance(result.package, GcsimTwoPlusTwoTargetPackage)
        self.assertEqual(
            {result.package.set_a.set_uid, result.package.set_b.set_uid},
            {"A", "B"},
        )

    def test_three_plus_two_derives_pair_under_existing_contract(self) -> None:
        result = self._derive(("A", "A", "A", "B", "B"))

        self.assertTrue(result.ready)
        self.assertIsInstance(result.package, GcsimTwoPlusTwoTargetPackage)
        self.assertEqual(dict(result.set_counts), {"A": 3, "B": 2})

    def test_unsupported_physical_shapes_fail_closed(self) -> None:
        for shape in (
            ("A", "A", "A", "B", "C"),
            ("A", "A", "B", "C", "D"),
            ("A", "B", "C", "D", "E"),
        ):
            with self.subTest(shape=shape):
                result = self._derive(shape)

                self.assertFalse(result.ready)
                self.assertEqual(
                    result.rejection.reason,
                    (
                        GcsimOptimizerPhysicalPackageRejectionReason
                        .SET_COUNT_SHAPE_UNSUPPORTED
                    ),
                )

    def test_pair_requires_include_two_plus_two(self) -> None:
        result = self._derive(
            ("A", "A", "A", "B", "B"),
            include_2p2p=False,
        )

        self.assertFalse(result.ready)
        self.assertEqual(
            result.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.TWO_PLUS_TWO_NOT_ENABLED,
        )

    def test_concrete_uids_with_same_gcsim_key_do_not_form_pair(self) -> None:
        refs = (
            _set_ref("A", key="samekey"),
            _set_ref("B", key="samekey"),
        )
        capabilities = (_capability("samekey"),)
        result = self._derive(
            ("A", "A", "A", "B", "B"),
            set_refs=refs,
            capabilities=capabilities,
            key_by_uid={"A": "samekey", "B": "samekey"},
        )

        self.assertFalse(result.ready)
        self.assertEqual(
            result.rejection.reason,
            (
                GcsimOptimizerPhysicalPackageRejectionReason
                .TWO_PLUS_TWO_GCSIM_KEY_COLLISION
            ),
        )

    def test_capability_gates_match_materializer_contract(self) -> None:
        four_piece_unmodeled = self._derive(
            ("A",) * 5,
            capabilities=(
                _capability("seta", four_piece_modeled=False),
            ),
        )
        two_piece_unmodeled = self._derive(
            ("A", "A", "A", "B", "B"),
            capabilities=(
                _capability("seta"),
                _capability("setb", two_piece_modeled=False),
            ),
        )

        self.assertEqual(
            four_piece_unmodeled.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.FOUR_PIECE_UNMODELED,
        )
        self.assertEqual(
            two_piece_unmodeled.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.TWO_PIECE_UNMODELED,
        )

    def test_parameter_policy_is_shared_with_materializer(self) -> None:
        valid = self._derive(
            ("A",) * 5,
            set_refs=(_set_ref("A", parameters={"stacks": 3}),),
            capabilities=(_capability("seta", parameter_keys=("stacks",)),),
        )
        unknown_key = self._derive(
            ("A",) * 5,
            set_refs=(_set_ref("A", parameters={"unknown": 3}),),
            capabilities=(_capability("seta", parameter_keys=("stacks",)),),
        )
        invalid_value = self._derive(
            ("A",) * 5,
            set_refs=(_set_ref("A", parameters={"stacks": "3"}),),
            capabilities=(_capability("seta", parameter_keys=("stacks",)),),
        )

        self.assertTrue(valid.ready)
        self.assertEqual(
            unknown_key.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.SET_PARAMETER_KEY_INVALID,
        )
        self.assertEqual(
            invalid_value.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.SET_PARAMETER_VALUE_INVALID,
        )

    def test_four_star_active_set_requires_and_accepts_existing_override(self) -> None:
        artifacts = _artifacts(("A",) * 5, rarity=4)
        rejected = self._derive(("A",) * 5, artifacts=artifacts)
        accepted = self._derive(
            ("A",) * 5,
            artifacts=artifacts,
            override=GcsimOptimizerFourStarEligibilityOverride(
                wearer=self.wearer,
                allowed_set_uids=("A",),
            ),
        )

        self.assertEqual(
            rejected.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.ARTIFACT_INELIGIBLE,
        )
        self.assertEqual(
            rejected.rejection.eligibility.reason,
            "four_star_requires_explicit_authorization",
        )
        self.assertTrue(accepted.ready)

    def test_four_star_offpiece_needs_explicit_id(self) -> None:
        artifacts = list(_artifacts(("A", "A", "A", "A", "B")))
        artifacts[-1] = replace(
            artifacts[-1],
            rarity=4,
            level=16,
            default_eligible=False,
        )
        set_only = GcsimOptimizerFourStarEligibilityOverride(
            wearer=self.wearer,
            allowed_set_uids=("B",),
        )
        explicit_id = GcsimOptimizerFourStarEligibilityOverride(
            wearer=self.wearer,
            allowed_artifact_ids=(artifacts[-1].artifact_id,),
        )

        rejected = self._derive(
            ("A", "A", "A", "A", "B"),
            artifacts=tuple(artifacts),
            override=set_only,
        )
        accepted = self._derive(
            ("A", "A", "A", "A", "B"),
            artifacts=tuple(artifacts),
            override=explicit_id,
        )

        self.assertEqual(
            rejected.rejection.eligibility.reason,
            "four_star_not_authorized_for_package",
        )
        self.assertTrue(accepted.ready)

    def test_physical_shape_failures_are_typed(self) -> None:
        artifacts = _artifacts(("A",) * 5)
        too_few = self._derive(("A",) * 5, artifacts=artifacts[:-1])
        duplicated = self._derive(
            ("A",) * 5,
            artifacts=(artifacts[0], replace(artifacts[1], artifact_id=1), *artifacts[2:]),
        )
        wrong_slots = self._derive(
            ("A",) * 5,
            artifacts=(*artifacts[:-1], replace(artifacts[-1], position_key="flower")),
        )

        self.assertEqual(
            too_few.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.ARTIFACT_COUNT_INVALID,
        )
        self.assertEqual(
            duplicated.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.ARTIFACT_ID_DUPLICATED,
        )
        self.assertEqual(
            wrong_slots.rejection.reason,
            (
                GcsimOptimizerPhysicalPackageRejectionReason
                .ARTIFACT_SLOT_COVERAGE_INVALID
            ),
        )

    def test_reference_and_capability_failures_are_typed(self) -> None:
        missing_ref = self._derive(("A",) * 5, set_refs=())
        ambiguous_ref = self._derive(
            ("A",) * 5,
            set_refs=(_set_ref("A"), _set_ref("A")),
        )
        missing_capability = self._derive(("A",) * 5, capabilities=())
        ambiguous_capability = self._derive(
            ("A",) * 5,
            capabilities=(_capability("seta"), _capability("seta")),
        )

        self.assertEqual(
            missing_ref.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.SET_REFERENCE_MISSING,
        )
        self.assertEqual(
            ambiguous_ref.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.SET_REFERENCE_AMBIGUOUS,
        )
        self.assertEqual(
            missing_capability.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.SET_CAPABILITY_UNAVAILABLE,
        )
        self.assertEqual(
            ambiguous_capability.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.SET_CAPABILITY_AMBIGUOUS,
        )

    def test_active_mapping_failures_and_input_order_are_deterministic(self) -> None:
        artifacts = _artifacts(("A",) * 5)
        invalid_mapping = self._derive(
            ("A",) * 5,
            artifacts=(
                replace(
                    artifacts[0],
                    set_mapping_status="unmapped",
                    gcsim_set_key="",
                ),
                *artifacts[1:],
            ),
        )
        mismatched_mapping = self._derive(
            ("A",) * 5,
            artifacts=tuple(
                replace(artifact, gcsim_set_key="different")
                for artifact in artifacts
            ),
        )
        refs = (_set_ref("A"), _set_ref("B"))
        capabilities = (_capability("seta"), _capability("setb"))
        physical = _artifacts(("A", "A", "A", "A", "B"))
        ordered = self._derive(
            ("A", "A", "A", "A", "B"),
            artifacts=physical,
            set_refs=refs,
            capabilities=capabilities,
        )
        reversed_inputs = self._derive(
            ("A", "A", "A", "A", "B"),
            artifacts=tuple(reversed(physical)),
            set_refs=tuple(reversed(refs)),
            capabilities=tuple(reversed(capabilities)),
        )

        self.assertEqual(
            invalid_mapping.rejection.reason,
            GcsimOptimizerPhysicalPackageRejectionReason.ACTIVE_SET_MAPPING_INVALID,
        )
        self.assertEqual(
            mismatched_mapping.rejection.reason,
            (
                GcsimOptimizerPhysicalPackageRejectionReason
                .ACTIVE_SET_REFERENCE_MISMATCH
            ),
        )
        self.assertTrue(ordered.ready)
        self.assertEqual(ordered.to_dict(), reversed_inputs.to_dict())

    def _derive(
        self,
        shape: tuple[str, ...],
        *,
        include_2p2p: bool = True,
        set_refs: tuple[GcsimOptimizerSetReference, ...] | None = None,
        capabilities: tuple[GcsimArtifactSetCapability, ...] | None = None,
        key_by_uid: dict[str, str] | None = None,
        artifacts: tuple[GcsimOptimizerArtifactRecord, ...] | None = None,
        override: GcsimOptimizerFourStarEligibilityOverride | None = None,
    ):
        unique_uids = tuple(sorted(set(shape)))
        keys = (
            {uid: f"set{uid.casefold()}" for uid in unique_uids}
            if key_by_uid is None
            else key_by_uid
        )
        refs = (
            tuple(_set_ref(uid, key=keys[uid]) for uid in unique_uids)
            if set_refs is None
            else set_refs
        )
        modeled = (
            tuple(_capability(key) for key in sorted(set(keys.values())))
            if capabilities is None
            else capabilities
        )
        physical = (
            _artifacts(shape, key_by_uid=keys)
            if artifacts is None
            else artifacts
        )
        return derive_gcsim_optimizer_target_from_physical_artifacts(
            wearer=self.wearer,
            artifacts=physical,
            set_refs=refs,
            set_capabilities=modeled,
            include_2p2p=include_2p2p,
            four_star_override=override,
        )


def _set_ref(
    set_uid: str,
    *,
    key: str | None = None,
    parameters: dict[str, object] | None = None,
) -> GcsimOptimizerSetReference:
    return GcsimOptimizerSetReference(
        set_uid=set_uid,
        gcsim_set_key=f"set{set_uid.casefold()}" if key is None else key,
        engine_binding_sha256="3" * 64,
        catalog_fingerprint="4" * 64,
        set_parameters={} if parameters is None else parameters,
    )


def _capability(
    key: str,
    *,
    two_piece_modeled: bool = True,
    four_piece_modeled: bool = True,
    parameter_keys: tuple[str, ...] = (),
) -> GcsimArtifactSetCapability:
    return GcsimArtifactSetCapability(
        key=key,
        package_name=key,
        key_constant=key.title(),
        max_rarity=5,
        registered=True,
        has_two_piece_code=two_piece_modeled,
        has_four_piece_code=four_piece_modeled,
        two_piece_modeled=two_piece_modeled,
        four_piece_modeled=four_piece_modeled,
        parameter_keys=parameter_keys,
    )


def _artifacts(
    shape: tuple[str, ...],
    *,
    key_by_uid: dict[str, str] | None = None,
    rarity: int = 5,
) -> tuple[GcsimOptimizerArtifactRecord, ...]:
    keys = (
        {uid: f"set{uid.casefold()}" for uid in set(shape)}
        if key_by_uid is None
        else key_by_uid
    )
    return tuple(
        GcsimOptimizerArtifactRecord(
            artifact_id=index,
            set_uid=set_uid,
            gcsim_set_key=keys[set_uid],
            set_mapping_status="ready",
            position=index,
            position_key=slot,
            rarity=rarity,
            level=16 if rarity == 4 else 20,
            main_property_type=None,
            main_property_name=None,
            main_property_value=None,
            main_numeric_value=None,
            substats=(),
            calculation_valid=True,
            default_eligible=rarity == 5,
            issues=(),
            raw_columns=(),
        )
        for index, (slot, set_uid) in enumerate(
            zip(GCSIM_OPTIMIZER_ARTIFACT_SLOTS, shape, strict=True),
            start=1,
        )
    )


if __name__ == "__main__":
    unittest.main()

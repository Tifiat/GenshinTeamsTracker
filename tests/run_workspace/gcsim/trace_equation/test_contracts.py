from __future__ import annotations

from dataclasses import replace
import json
import unittest

from run_workspace.gcsim.trace_equation import (
    CallbackPhase,
    CandidateStatDelta,
    DamageFormulaInputs,
    FormulaProvenance,
    FormulaValue,
    GuardKind,
    GuardObservation,
    GuardOperator,
    GuardPredicate,
    GuardTopologyReport,
    OpaqueEngineTraceEnvelope,
    ProvenanceSourceKind,
    ReactionOperator,
    ReplayStatus,
    ScalingKind,
    SnapshotStat,
    TopologyChannel,
    TopologyChannelDigest,
    TopologyEvidenceEvent,
    TOPOLOGY_COVERAGE_SENTINEL_KIND,
    TraceContractError,
    TraceDamageMode,
    TraceDocument,
    TraceExtractionRequest,
    TraceHitCompleteness,
    TraceHitEvent,
    TraceLineage,
    TraceObjective,
    ValueReadMode,
    canonical_json,
    canonical_sha256,
    decode_trace_document,
    decode_engine_trace_v1,
    encode_trace_document,
    replay_candidate_stat_deltas,
    replay_terminal_hit_slice,
)


class TraceEquationContractTests(unittest.TestCase):
    def test_document_round_trip_preserves_identity_and_is_immutable(self) -> None:
        document = _document()
        payload = encode_trace_document(document)
        decoded = decode_trace_document(payload)

        self.assertEqual(decoded, document)
        self.assertEqual(
            decoded.receipt.receipt_sha256,
            document.receipt.receipt_sha256,
        )
        with self.assertRaises((AttributeError, TypeError)):
            decoded.request.seed = 7  # type: ignore[misc]

    def test_codec_rejects_unknown_missing_duplicate_and_nonfinite_json(self) -> None:
        payload = encode_trace_document(_document())
        parsed = json.loads(payload)
        parsed["unknown"] = True
        with self.assertRaisesRegex(TraceContractError, "unknown"):
            decode_trace_document(json.dumps(parsed))

        parsed = json.loads(payload)
        del parsed["kind"]
        with self.assertRaisesRegex(TraceContractError, "missing"):
            decode_trace_document(json.dumps(parsed))

        duplicate = payload.replace(
            '"kind":"gtt.trace_equation.trace"',
            '"kind":"gtt.trace_equation.trace","kind":"gtt.trace_equation.trace"',
            1,
        )
        with self.assertRaisesRegex(TraceContractError, "duplicate"):
            decode_trace_document(duplicate)

        with self.assertRaisesRegex(TraceContractError, "non-finite"):
            decode_trace_document('{"schema_version":NaN}')

    def test_receipt_tamper_is_rejected(self) -> None:
        parsed = json.loads(encode_trace_document(_document()))
        parsed["receipt"]["trace_body_sha256"] = "0" * 64
        with self.assertRaisesRegex(TraceContractError, "trace_body_sha256"):
            decode_trace_document(json.dumps(parsed))

    def test_raw_crit_rate_is_separate_and_exactly_clamped(self) -> None:
        for raw, clamped in ((0.95, 0.95), (1.0, 1.0), (1.05, 1.0)):
            with self.subTest(raw=raw):
                inputs = _formula_inputs(raw_cr=raw, crit_rate=clamped)
                self.assertEqual(inputs.raw_crit_rate.value, raw)
                self.assertEqual(inputs.crit_rate.value, clamped)

        with self.assertRaisesRegex(TraceContractError, "exact clamp"):
            _formula_inputs(raw_cr=1.05, crit_rate=0.99)

    def test_unknown_formula_and_operator_are_preserved_as_unsupported(self) -> None:
        base = _document()
        hit = base.hits[0]
        unknown_inputs = replace(
            hit.formula_inputs,
            formula_kind="future_formula/v2",
        )
        opaque_json = canonical_json(
            {"operator_id": "future/reaction", "raw": {"coefficient": 3.0}}
        )
        unknown_lineage = replace(
            hit.lineage,
            reaction_operator_id="future/reaction",
            reaction_operator_sha256="8" * 64,
            opaque_reaction_payload_json=opaque_json,
            opaque_reaction_payload_sha256=canonical_sha256(
                json.loads(opaque_json)
            ),
        )
        unknown_hit = replace(
            hit,
            formula_inputs=unknown_inputs,
            lineage=unknown_lineage,
            formula_replay_status=ReplayStatus.UNSUPPORTED,
            formula_replay_reason_codes=("unknown_formula_or_operator",),
        )
        document = TraceDocument.build(
            request=base.request,
            hits=(unknown_hit,),
            topology=base.topology,
        )

        decoded = decode_trace_document(encode_trace_document(document))
        self.assertEqual(decoded.hits[0].formula_inputs.formula_kind, "future_formula/v2")
        self.assertEqual(
            decoded.hits[0].lineage.reaction_operator_id,
            "future/reaction",
        )
        self.assertEqual(
            decoded.hits[0].formula_replay_status,
            ReplayStatus.UNSUPPORTED,
        )
        diagnostic = replay_terminal_hit_slice(decoded, ())
        self.assertFalse(diagnostic.formula_supported)
        self.assertIsNone(diagnostic.team_uncapped_damage)

    def test_diagnostic_atk_percent_replays_terminal_formula(self) -> None:
        result = replay_terminal_hit_slice(
            _document(),
            (CandidateStatDelta("hero", "atk%", 0.05),),
        )

        self.assertFalse(result.authoritative)
        self.assertTrue(result.formula_supported)
        self.assertAlmostEqual(result.team_uncapped_damage or 0.0, 891.0)
        self.assertAlmostEqual(result.team_reported_damage or 0.0, 891.0)

    def test_crit_roll_side_change_requires_exact_engine_run(self) -> None:
        result = replay_candidate_stat_deltas(
            _document(),
            (CandidateStatDelta("hero", "cr", 0.4),),
        )

        self.assertEqual(result.assessment.status, ReplayStatus.NEEDS_EXACT)
        self.assertIsNone(result.team_uncapped_damage)
        self.assertIn("crit_roll_side_changed", result.assessment.reason_codes[0])

    def test_incomplete_topology_blocks_authoritative_but_not_diagnostic_math(self) -> None:
        base = _document()
        incomplete_topology = _topology(complete=False)
        incomplete_hit = replace(
            base.hits[0],
            completeness=TraceHitCompleteness(
                formula_complete=True,
                flat_dmg_provenance_complete=True,
                attack_mod_provenance_complete=True,
                reaction_topology_complete=False,
                provider_identity_complete=False,
            ),
            formula_replay_status=ReplayStatus.NEEDS_EXACT,
            formula_replay_reason_codes=("provider_identity_incomplete",),
        )
        document = TraceDocument.build(
            request=base.request,
            hits=(incomplete_hit,),
            topology=incomplete_topology,
        )

        authoritative = replay_candidate_stat_deltas(document, ())
        diagnostic = replay_terminal_hit_slice(document, ())

        self.assertEqual(authoritative.assessment.status, ReplayStatus.NEEDS_EXACT)
        self.assertIsNone(authoritative.team_uncapped_damage)
        self.assertFalse(diagnostic.authoritative)
        self.assertTrue(diagnostic.formula_supported)
        self.assertAlmostEqual(diagnostic.team_uncapped_damage or 0.0, 864.0)

    def test_duration_mode_separates_hp_subtraction_from_reported_damage(self) -> None:
        document = _document(
            damage_mode=TraceDamageMode.DURATION,
            target_hp=500.0,
        )
        hit = document.hits[0]

        self.assertEqual(hit.hp_damage_applied, 500.0)
        self.assertEqual(hit.reported_damage, 864.0)
        self.assertEqual(hit.target_hp_after, 0.0)
        self.assertFalse(hit.target_killed)

    def test_generic_guard_crossing_blocks_authoritative_replay(self) -> None:
        base = _document()
        guard = GuardObservation(
            guard_id="guard:atk-window",
            guard_kind=GuardKind.THRESHOLD,
            frame=118,
            subject_key="hero",
            phase=CallbackPhase.SNAPSHOT,
            baseline_value=0.5,
            predicate=GuardPredicate(
                operator=GuardOperator.CLOSED_INTERVAL,
                expected_value=None,
                lower_bound=0.0,
                upper_bound=0.52,
                lower_inclusive=True,
                upper_inclusive=True,
            ),
            dependency_keys=("stat:hero:atk%",),
            evidence_event_ids=("attack:1",),
        )
        guarded = TraceDocument.build(
            request=base.request,
            hits=base.hits,
            topology=_topology(guards=(guard,)),
        )

        result = replay_candidate_stat_deltas(
            guarded,
            (CandidateStatDelta("hero", "atk%", 0.05),),
        )

        self.assertEqual(result.assessment.status, ReplayStatus.NEEDS_EXACT)
        self.assertEqual(result.assessment.triggered_guard_ids, ("guard:atk-window",))
        self.assertEqual(
            result.assessment.reason_codes,
            ("guard_crossed:guard:atk-window",),
        )

    def test_complete_topology_cannot_use_empty_self_asserted_digests(self) -> None:
        with self.assertRaisesRegex(TraceContractError, "coverage sentinel"):
            GuardTopologyReport(
                channels=tuple(
                    TopologyChannelDigest(
                        channel=channel,
                        sha256=canonical_sha256([]),
                        item_count=0,
                        complete=True,
                    )
                    for channel in TopologyChannel
                ),
                evidence_events=(),
                guards=(),
                unsupported_feature_codes=(),
                complete=True,
            )

    def test_complete_document_rejects_dangling_lineage_reference(self) -> None:
        base = _document()
        dangling = replace(
            base.hits[0],
            lineage=replace(base.hits[0].lineage, source_event_id="attack:missing"),
        )
        with self.assertRaisesRegex(TraceContractError, "references unknown event"):
            TraceDocument.build(
                request=base.request,
                hits=(dangling,),
                topology=base.topology,
            )

    def test_raw_engine_v1_adapter_is_strict_and_diagnostic_only(self) -> None:
        request = _document().request
        raw = _raw_engine_trace(request)
        raw["hits"][0]["unsupported"] = [
            "multiplier_source_expression_not_instrumented",
            "provider_identity_not_instrumented",
        ]
        raw["unsupported"] = [
            "gadget_wave_state_lineage_not_instrumented",
            "multiplier_source_expression_not_instrumented",
            "provider_identity_not_instrumented",
        ]
        raw["guard_summary"]["unsupported_hit_count"] = 1
        raw["guard_summary"]["unsupported_count"] = 3

        decoded = decode_engine_trace_v1(canonical_json(raw), request=request)

        self.assertIsInstance(decoded, TraceDocument)
        assert isinstance(decoded, TraceDocument)
        self.assertFalse(decoded.topology.complete)
        self.assertEqual(
            decoded.hits[0].formula_replay_status,
            ReplayStatus.NEEDS_EXACT,
        )
        authoritative = replay_candidate_stat_deltas(decoded, ())
        diagnostic = replay_terminal_hit_slice(decoded, ())
        self.assertEqual(authoritative.assessment.status, ReplayStatus.NEEDS_EXACT)
        self.assertFalse(diagnostic.authoritative)
        self.assertAlmostEqual(diagnostic.team_uncapped_damage or 0.0, 864.0)

        changed = json.loads(canonical_json(raw))
        changed["unknown"] = True
        with self.assertRaisesRegex(TraceContractError, "unknown"):
            decode_engine_trace_v1(canonical_json(changed), request=request)

        future = decode_engine_trace_v1(
            canonical_json(
                {"schema_version": 2, "capability": "future", "new": True}
            ),
            request=request,
        )
        self.assertIsInstance(future, OpaqueEngineTraceEnvelope)


def _document(
    *,
    damage_mode: TraceDamageMode = TraceDamageMode.DAMAGE,
    target_hp: float = 10_000.0,
) -> TraceDocument:
    request = TraceExtractionRequest(
        context_sha256="1" * 64,
        source_config_sha256="2" * 64,
        compiled_action_sha256="3" * 64,
        target_sha256="4" * 64,
        engine_artifact_sha256="5" * 64,
        engine_binding_sha256="6" * 64,
        formula_version="trace-v1",
        formula_sha256="7" * 64,
        seed=42,
        objective=TraceObjective.TEAM_DPS,
        character_keys=("hero",),
        required_capabilities=("gtt_trace_equation_v1",),
    )
    formula_inputs = _formula_inputs()
    hp_damage = min(864.0, target_hp)
    killed = damage_mode is TraceDamageMode.DAMAGE and hp_damage == target_hp
    reported = hp_damage if killed else 864.0
    provenance = (
        FormulaProvenance(
            provenance_id="artifact-snapshot",
            source_kind=ProvenanceSourceKind.ARTIFACT,
            source_key="equipped-build",
            owner_key="hero",
            provider_event_id=None,
            modifier_key=None,
            modifier_channel=None,
            read_phase=CallbackPhase.SNAPSHOT,
            read_mode=ValueReadMode.SNAPSHOT,
        ),
        FormulaProvenance(
            provenance_id="engine-formula",
            source_kind=ProvenanceSourceKind.ENGINE_FORMULA,
            source_key="enemy.calc.standard",
            owner_key=None,
            provider_event_id=None,
            modifier_key=None,
            modifier_channel=None,
            read_phase=CallbackPhase.DAMAGE_RESOLUTION,
            read_mode=ValueReadMode.CONSTANT,
        ),
    )
    hit = TraceHitEvent(
        event_id="hit:1",
        frame=120,
        source_frame=118,
        snapshot_frame=118,
        actor_index=0,
        actor_key="hero",
        ability="skill",
        attack_tag=1,
        element="anemo",
        target_key="enemy:0",
        target_index=0,
        damage_mode=damage_mode,
        hp_cap_active=damage_mode is TraceDamageMode.DAMAGE,
        lineage=TraceLineage(
            parent_event_id=None,
            source_event_id="attack:1",
            damage_source_key="hero:skill",
            gadget_id=None,
            reaction_type=None,
            reaction_operator_id=ReactionOperator.NONE.value,
            reaction_operator_sha256=canonical_sha256({"operator": "none"}),
            opaque_reaction_payload_json=None,
            opaque_reaction_payload_sha256=None,
            reaction_owner_key=None,
            aura_source_keys=(),
        ),
        provenance=provenance,
        formula_inputs=formula_inputs,
        uncapped_rolled_damage=864.0,
        hp_damage_applied=hp_damage,
        reported_damage=reported,
        target_hp_before=target_hp,
        target_hp_after=max(0.0, target_hp - hp_damage),
        target_killed=killed,
        crit=False,
        completeness=TraceHitCompleteness(
            formula_complete=True,
            flat_dmg_provenance_complete=True,
            attack_mod_provenance_complete=True,
            reaction_topology_complete=True,
            provider_identity_complete=True,
        ),
        unsupported_feature_codes=(),
        formula_replay_status=ReplayStatus.EXACT_IN_CELL,
        formula_replay_reason_codes=(),
    )
    return TraceDocument.build(request=request, hits=(hit,), topology=_topology())


def _formula_inputs(
    *,
    raw_cr: float = 0.5,
    crit_rate: float = 0.5,
) -> DamageFormulaInputs:
    engine = ("engine-formula",)
    artifact = ("artifact-snapshot",)

    def value(number: float, provenance: tuple[str, ...] = engine) -> FormulaValue:
        return FormulaValue(number, provenance)

    stats = {
        "atk": 100.0,
        "atk%": 0.5,
        "base_atk": 1000.0,
        "base_def": 500.0,
        "base_hp": 10000.0,
        "anemo%": 0.2,
        "cd": 0.5,
        "cr": raw_cr,
        "def": 100.0,
        "def%": 0.0,
        "em": 0.0,
        "dmg%": 0.0,
        "hp": 1000.0,
        "hp%": 0.0,
    }
    return DamageFormulaInputs(
        formula_kind="standard",
        formula_sha256="7" * 64,
        character_level=90,
        target_level=100,
        scaling_kind=ScalingKind.ATTACK,
        scaling_value=value(1600.0, artifact),
        snapshot_stats=tuple(
            SnapshotStat(key, number, artifact)
            for key, number in sorted(stats.items())
        ),
        mult=value(1.0),
        base_dmg_bonus=value(0.0),
        flat_dmg=value(0.0),
        base_damage=value(1600.0),
        dmg_bonus=value(0.2),
        raw_crit_rate=value(raw_cr, artifact),
        crit_rate=value(crit_rate, artifact),
        crit_damage=value(0.5, artifact),
        crit_roll=value(0.8),
        hit_weak_point=False,
        defense_multiplier=value(0.5),
        defense_adjustment=value(0.0),
        ignore_defense_percent=value(0.0),
        resistance_multiplier=value(0.9),
        resistance=value(0.1),
        amplifying=False,
        amp_multiplier=value(1.0),
        elemental_mastery=value(0.0, artifact),
        em_bonus=value(0.0),
        reaction_bonus=value(0.0),
        amp_reaction_bonus=value(0.0),
        group_multiplier=value(1.0),
        elevation=value(0.0),
        elevation_multiplier=value(1.0),
    )


def _topology(
    *,
    complete: bool = True,
    guards: tuple[GuardObservation, ...] = (),
) -> GuardTopologyReport:
    unsupported = () if complete else ("engine_v1_topology_incomplete",)
    evidence = (
        tuple(
            TopologyEvidenceEvent(
                event_id=(
                    "attack:1"
                    if channel is TopologyChannel.ACTIONS
                    else f"coverage:{channel.value}"
                ),
                channel=channel,
                frame=0 if channel is not TopologyChannel.ACTIONS else 118,
                phase=(
                    CallbackPhase.SNAPSHOT
                    if channel is TopologyChannel.ACTIONS
                    else CallbackPhase.END_OF_FRAME
                ),
                kind_id=(
                    "captured_attack"
                    if channel is TopologyChannel.ACTIONS
                    else TOPOLOGY_COVERAGE_SENTINEL_KIND
                ),
                subject_key="hero" if channel is TopologyChannel.ACTIONS else "trace",
                state_sha256=canonical_sha256(
                    {"channel": channel.value, "complete": complete}
                ),
            )
            for channel in TopologyChannel
        )
        if complete
        else ()
    )
    if complete:
        action_sentinel = TopologyEvidenceEvent(
            event_id="coverage:actions",
            channel=TopologyChannel.ACTIONS,
            frame=118,
            phase=CallbackPhase.END_OF_FRAME,
            kind_id=TOPOLOGY_COVERAGE_SENTINEL_KIND,
            subject_key="trace",
            state_sha256=canonical_sha256(
                {"channel": TopologyChannel.ACTIONS.value, "complete": True}
            ),
        )
        evidence = tuple(
            sorted((*evidence, action_sentinel), key=lambda row: row.frame)
        )
    return GuardTopologyReport(
        channels=tuple(
            TopologyChannelDigest(
                channel=channel,
                sha256=canonical_sha256(
                    [
                        row.to_dict()
                        for row in evidence
                        if row.channel is channel
                    ]
                ),
                item_count=sum(row.channel is channel for row in evidence),
                complete=complete,
            )
            for channel in TopologyChannel
        ),
        evidence_events=evidence,
        guards=guards,
        unsupported_feature_codes=unsupported,
        complete=complete,
    )


def _raw_engine_trace(request: TraceExtractionRequest) -> dict[str, object]:
    stats = {
        "atk": 100.0,
        "atk%": 0.5,
        "base_atk": 1000.0,
        "base_def": 500.0,
        "base_hp": 10000.0,
        "cd": 0.5,
        "cr": 0.5,
        "def": 100.0,
        "def%": 0.0,
        "em": 0.0,
        "hp": 1000.0,
        "hp%": 0.0,
    }
    completeness = {
        "formula_complete": True,
        "flat_dmg_provenance_complete": True,
        "attack_mod_provenance_complete": True,
        "reaction_topology_complete": False,
        "provider_identity_complete": False,
    }
    hit = {
        "attack_id": 1,
        "hit_id": 1,
        "parent_attack_id": None,
        "parent_hit_id": None,
        "frame": 120,
        "source_frame": 118,
        "snapshot_frame": 118,
        "actor_index": 0,
        "damage_src": 1,
        "ability": "skill",
        "attack_tag": 1,
        "element": "pyro",
        "target_key": 0,
        "target_type": 0,
        "formula_kind": "standard",
        "formula_sha256": request.formula_sha256,
        "reaction_operator_id": "none",
        "mult": 1.0,
        "flat_dmg": 0.0,
        "use_def": False,
        "use_hp": False,
        "use_em": False,
        "base_dmg_bonus": 0.0,
        "elevation": 0.0,
        "ignore_def_percent": 0.0,
        "amped": False,
        "amp_mult": 1.0,
        "amp_type": "",
        "catalyzed": False,
        "icd_tag": 0,
        "icd_group": 0,
        "durability_initial": 0.0,
        "durability_post_icd": 0.0,
        "damage_group_multiplier": 1.0,
        "snapshot_stats": stats,
        "char_level": 90,
        "target_level": 100,
        "scaling_stat_kind": "atk",
        "scaling_stat_value": 1600.0,
        "base_damage": 1600.0,
        "damage_bonus": 0.2,
        "raw_crit_rate": 0.5,
        "crit_rate_clamped": 0.5,
        "crit_damage": 0.5,
        "crit_roll": 0.8,
        "hit_weak_point": False,
        "is_crit": False,
        "resistance": 0.1,
        "res_mod": 0.9,
        "def_adj": 0.0,
        "def_mod": 0.5,
        "em": 0.0,
        "em_bonus": 0.0,
        "reaction_bonus": 0.0,
        "amp_total": 1.0,
        "pre_amp_damage": 864.0,
        "elevation_multiplier": 1.0,
        "uncapped_damage": 864.0,
        "hp_before": 10000.0,
        "actual_damage": 864.0,
        "reported_damage": 864.0,
        "hp_after": 9136.0,
        "killed": False,
        "damage_mode": True,
        "hp_cap_active": True,
        "attack_mods": [],
        "aura_before": [],
        "aura_after_reaction": [],
        "aura_after_attachment": [],
        "completeness": completeness,
        "unsupported": [],
    }
    return {
        "schema_version": 1,
        "capability": "gtt_trace_equation_v1",
        "engine_version": "gcsim-test",
        "patch_version": "test-patch",
        "formula_version": request.formula_version,
        "formula_sha256": request.formula_sha256,
        "context_sha256": request.context_sha256,
        "request_sha256": "9" * 64,
        "source_config_sha256": request.source_config_sha256,
        "compiled_action_sha256": request.compiled_action_sha256,
        "target_sha256": request.target_sha256,
        "seed": str(request.seed),
        "duration_frames": 600,
        "character_keys": list(request.character_keys),
        "hits": [hit],
        "topology_events": [],
        "unsupported": [],
        "guard_summary": {
            "hit_count": 1,
            "topology_event_count": 0,
            "unsupported_hit_count": 0,
            "unsupported_count": 0,
            "formula_kind_counts": {"standard": 1},
            "reaction_operator_counts": {"none": 1},
            **completeness,
            "exact_replay_eligible": False,
        },
    }


if __name__ == "__main__":
    unittest.main()

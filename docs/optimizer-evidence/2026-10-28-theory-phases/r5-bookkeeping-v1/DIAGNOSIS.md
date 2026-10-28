# Retained-source replay diagnosis

Source identity: source.json base_map (timed R5, 449 files). This is a source
explanation of the r5-v1 counters, not new numerical evidence.

`setcontext/neutral.go` resolves the tuple through CompilePackagesSparse and
accounts inclusive RuleSeconds. Requests22020 / DispatchHits11010 show that
the second resolution reuses the model dispatch result for 11010 actual tuples.
Program hits10557/misses453 also exclude a blanket claim that all reuse is off.

`seteffects/neutral_composition.go` caches a component even when unusable;
the hit counter therefore does not prove composable reuse. componentOf requires
complete output, !out.r1Frozen and a tracked footprint. Unusable components or
groups cause full-package fallback. conflictGroup also refuses to cache
unusable/symbolic/oversized groups. Thus R1 can produce a complete frozen guide
that is still deliberately excluded from component composition. The small
causal fixture isolates this predicate, without relaxing it in production.
The counts do not establish that every one of 3102 full fallbacks has only
this cause; other rejection guards remain possible.

`seteffects/neutral_expressions.go:compilePackagesJoint` alone increments
Preparation.Replays and ReplaySeconds; JointReplays increments for >1 choice.
Its deferred timer covers symbolic replay plus r1Freeze and any concrete
EvaluatePackages nested there. EvaluatePackages itself does not increment this
joint timer. R1FallbackReplays counts r1FreezeConcrete calls after its initial
boundary/dimension validation; it is not equivalent to FullFallbacks or Replays.

`seteffects/r1_frozen_neutral.go:r1Freeze` tries concrete EvaluatePackages for
remaining symbolic boundaries. r1FreezeConcrete visits missing effect ports,
validates source ownership, freezes known finite anchors or preserves unresolved
source slots with a zero additive intervention, then marks output r1Frozen.
AnchorPorts/ReferencePorts count these repeated port events. OmittedRecords
counts events beyond the 128-record cap. They do not count independent tuples.
The original record literal computes ruleChoicesKey for every event before
checking retention. r1RememberReasons separately keeps up to64 package guides;
that key computation is intentionally unchanged by this variant.

ForkTheory copies the binding and component/group maps, preserving entries and
counter values. Model ForkTheory clones binding/specialization/program state
and resets its reverse-index pointer. The measured checkpoint fork was0.069976s;
neither the source nor measurement supports attributing 372s to cache erasure
or copy time. The response fork's later replay0.155932s is separate from the
main model's372.929676s and must not be added as a second copy of that total.

The present variant isolates discarded diagnostic record construction/key work.
It does not resolve the broader frozen/composition policy or establish its
quality implications. Timing improvement and numerical/work-count parity
remain unmeasured until the separately dispatched single Luna run.

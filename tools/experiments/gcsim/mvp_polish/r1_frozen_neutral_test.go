package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"math"
	"testing"
)

func r1TestBinding() *NeutralBinding {
	return &NeutralBinding{r1Frozen: true, keys: []string{"known", "missing"}, ports: []formula.EffectPort{{Member: 0, NodeID: 1, Key: "known", Observed: 5}, {Member: 0, NodeID: 2, Key: "missing", Observed: 17}}, members: []neutralBoundMember{{seed: "123", ports: []neutralBoundPort{{dimension: 0, query: RuleQuery{Owner: 1}}, {dimension: 1, query: RuleQuery{Owner: 2}}}}}}
}
func r1TestPartial() NeutralExpressions {
	return NeutralExpressions{Effects: map[string]*formula.InputExpression{"known": {Operation: "read", Key: "kept.stat"}}, Boundaries: []string{"unbound heal expression"}}
}
func TestR1FrozenAnchorsKeepKnownArithmeticAndProvenance(t *testing.T) {
	b := r1TestBinding()
	out := b.r1FreezeConcrete([]RuleChoice{{Owner: 2, Key: "generic", Pieces: 4}}, r1TestPartial(), NeutralEffectVector{Values: []float64{99, 7}, Known: []bool{true, true}})
	if !out.Complete() || out.SparseEffects[0].Key != "kept.stat" || out.Constants[1] != 7 || len(out.Uncertainty) == 0 {
		t.Fatal("known arithmetic lost", out)
	}
	r := b.r1Stats.Records[0]
	if r.State != "observed_package_anchor_frozen" || r.Owner != 2 || r.Seed != "123" || r.SourceNode != 2 || r.SourceValue != 17 || r.PackageAnchorValue == nil || *r.PackageAnchorValue != 7 {
		t.Fatal("anchor provenance lost", r)
	}
}
func TestR1UnknownReferencePreservesSourceAndRejectsNonfinite(t *testing.T) {
	b := r1TestBinding()
	out := b.r1FreezeConcrete(nil, r1TestPartial(), NeutralEffectVector{Values: []float64{0, 0}, Known: []bool{false, false}})
	if !out.Complete() || out.SparseEffects[0].Key != "kept.stat" || len(out.Uncertainty) == 0 {
		t.Fatal(out)
	}
	r := b.r1Stats.Records[0]
	if r.State != "no_package_anchor_reference_guide" || r.PackageAnchorValue != nil || !r.SourceSlotPreserved || r.SourceValue != 17 {
		t.Fatal("unknown became observed zero", r)
	}
	b = r1TestBinding()
	bad := b.r1FreezeConcrete(nil, r1TestPartial(), NeutralEffectVector{Values: []float64{0, math.NaN()}, Known: []bool{false, true}})
	if bad.Complete() {
		t.Fatal("nonfinite anchor hidden")
	}
	b = r1TestBinding()
	b.ports[1].Member = 3
	bad = b.r1FreezeConcrete(nil, r1TestPartial(), NeutralEffectVector{Values: []float64{0, 7}, Known: []bool{false, true}})
	if bad.Complete() {
		t.Fatal("foreign source-slot accepted")
	}
}
func TestR1InvalidMechanicNeverFrozenAndUnmappedStaysExplicit(t *testing.T) {
	b := r1TestBinding()
	out := r1TestPartial()
	out.MechanicBoundaries = []contracts.MechanicBoundary{{Kind: contracts.MechanicInvalidOperation, Reason: "invalid identity"}}
	if b.r1Freeze(nil, out).Complete() {
		t.Fatal("invalid operation hidden")
	}
	b = &NeutralBinding{r1Frozen: true}
	out = b.r1Freeze(nil, NeutralExpressions{Boundaries: []string{"unsupported operation with no slots"}})
	if !out.Complete() || len(out.Uncertainty) == 0 || len(b.r1Stats.Records) != 0 || len(b.r1Stats.UnmappedPackageReasons) != 1 {
		t.Fatal("unmapped operation fabricated a slot", out)
	}
}

func TestR1ConcreteInvalidAndResolvedPathRemainDistinct(t *testing.T) {
	b := r1TestBinding()
	bad := b.r1FreezeConcrete(nil, r1TestPartial(), NeutralEffectVector{Values: []float64{0, 7}, Known: []bool{false, true}, MechanicBoundaries: []contracts.MechanicBoundary{{Kind: contracts.MechanicInvalidOperation, Reason: "bad concrete identity"}}})
	if bad.Complete() || len(bad.MechanicBoundaries) != 1 {
		t.Fatal("concrete invalid operation hidden", bad)
	}
	exact := NeutralExpressions{Effects: map[string]*formula.InputExpression{"known": {Operation: "constant", Value: 2}}, Uncertainty: []string{"existing"}}
	got := b.r1Freeze(nil, exact)
	if !got.Complete() || len(got.Uncertainty) != 1 || got.r1Frozen || b.r1Stats.FallbackReplays != 0 {
		t.Fatal("resolved path changed", got)
	}
}

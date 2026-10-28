package setcontext

import (
	"math"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func compactConstantModel(t *testing.T) (*NeutralModel, []string) {
	t.Helper()
	sha := strings.Repeat("a", 64)
	neutral := &contracts.NeutralInputs{
		Context: contracts.NeutralContext{NoSets: true, DurationFrames: 1},
		World:   &contracts.NeutralWorldLedger{Complete: true, States: []contracts.NeutralWorldState{}},
		Ledger:  contracts.CombatEventLedger{Events: []contracts.CombatEvent{}},
	}
	for i, key := range []string{"actor_a", "actor_b", "actor_c", "actor_d"} {
		neutral.Context.Characters = append(neutral.Context.Characters, contracts.NeutralCharacter{Index: i, Key: key})
	}
	for i, key := range []string{"em", "er", "atk%"} {
		neutral.Stats = append(neutral.Stats, contracts.NeutralStatInput{NodeID: uint32(i + 1), Owner: "actor_a", Kind: "stat", Stat: key,
			Point: contracts.NeutralInputPoint{Mode: "snapshot", Order: 1, Frame: 1}})
	}
	catalog := &seteffects.SourceCatalog{SourceManifestSHA256: sha}
	binding, err := seteffects.NewNeutralBinding(catalog, []contracts.EffectInputsOutput{{SourceManifestBodySHA256: sha, Neutral: neutral}})
	if err != nil {
		t.Fatal(err)
	}
	ports := binding.Ports()
	member := contracts.IRSeedMember{Seed: 1, DurationMS: 1000, TopologySHA256: strings.Repeat("b", 64),
		Nodes: []contracts.IRNode{
			{NodeID: 1, Operation: "constant", Value: "0", Inputs: []contracts.IRInput{}},
			{NodeID: 2, Operation: "constant", Value: "0", Inputs: []contracts.IRInput{}},
			{NodeID: 3, Operation: "constant", Value: "0", Inputs: []contracts.IRInput{}},
			{NodeID: 4, Operation: "artifact_stat", Coordinate: "actor_a.atk", Inputs: []contracts.IRInput{}},
			{NodeID: 5, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "a"}, {NodeID: 2, Relation: "b"}, {NodeID: 4, Relation: "artifact"}}},
		},
		Channels:         []contracts.IRChannel{{ChannelID: "synthetic", Kind: "direct", ActorKey: "actor_a", AttackTag: "skill", DamageType: "synthetic", RootNodeID: 5, HitCount: 1, BaselineDamage: "0", ResponseCoordinates: []string{"actor_a.atk"}}},
		OpaqueBoundaries: []contracts.IROpaqueBoundary{},
	}
	compiled, err := formula.CompileSeedMember(member, []string{"actor_a", "actor_b", "actor_c", "actor_d"}, []string{"actor_a.atk"})
	if err != nil {
		t.Fatal(err)
	}
	// Capture order (binding.Keys) is node order; formula order is deliberately reversed.
	prepared, err := formula.PrepareParametricWithReads([]*formula.CompiledMember{compiled},
		[]formula.EffectPort{ports[1], ports[0], ports[2]},
		[]formula.ReadRoot{{Member: 0, NodeID: 3, Key: "latent_read", Observed: 0}})
	if err != nil {
		t.Fatal(err)
	}
	if got, want := prepared.EffectKeys(), []string{ports[1].Key, ports[0].Key, ports[2].Key}; len(got) != len(want) || got[0] != want[0] || got[1] != want[1] || got[2] != want[2] {
		t.Fatalf("fixture did not reverse formula/binding order: formula=%v binding=%v", got, binding.Keys())
	}
	return &NeutralModel{binding: binding, prepared: prepared}, binding.Keys()
}

func compactMapEffects(keys []string, values []float64) map[string]*formula.InputExpression {
	out := make(map[string]*formula.InputExpression, len(keys))
	for i, key := range keys {
		out[key] = &formula.InputExpression{Operation: "constant", Value: values[i]}
	}
	return out
}

func TestNeutralDenseAndMapConstantsShareCacheAcrossReorderedPorts(t *testing.T) {
	model, keys := compactConstantModel(t)
	values := []float64{10, 20, 30}
	dense, err := model.bindConstants(values)
	if err != nil {
		t.Fatal(err)
	}
	mapProgram, err := model.bindProgram(compactMapEffects(keys, values))
	if err != nil || mapProgram != dense {
		t.Fatalf("map binding did not reuse dense program: same=%v stats=%+v err=%v", mapProgram == dense, model.stats, err)
	}
	got, err := dense.Evaluate([]float64{4}, nil)
	if err != nil || got != 34 {
		t.Fatalf("reordered vector bound wrong ports: got=%v want=34 err=%v", got, err)
	}
	if model.stats.ProgramMisses != 1 || model.stats.ProgramHits != 1 {
		t.Fatalf("dense/map cache accounting: %+v", model.stats)
	}

	// Latent-only changes are validated but do not change a damage-only cache key.
	latentChanged := []float64{10, 20, 31}
	reused, err := model.bindConstants(latentChanged)
	if err != nil || reused != dense {
		t.Fatalf("latent-only dense change missed cache: same=%v err=%v", reused == dense, err)
	}
	reused, err = model.bindProgram(compactMapEffects(keys, latentChanged))
	if err != nil || reused != dense {
		t.Fatalf("latent-only map change missed cache: same=%v err=%v", reused == dense, err)
	}

	// Both representations key signed zero by its exact IEEE bits.
	positiveZero := []float64{0, 0, 0}
	positive, err := model.bindConstants(positiveZero)
	if err != nil {
		t.Fatal(err)
	}
	negativeZero := []float64{math.Copysign(0, -1), 0, 0}
	negative, err := model.bindProgram(compactMapEffects(keys, negativeZero))
	if err != nil || negative == positive {
		t.Fatalf("signed-zero vectors aliased in map/dense cache: same=%v err=%v", negative == positive, err)
	}
	negativeAgain, err := model.bindConstants(negativeZero)
	if err != nil || negativeAgain != negative {
		t.Fatalf("map/dense signed-zero cache reuse failed: same=%v err=%v", negativeAgain == negative, err)
	}
}

func TestNeutralDenseConstantsRejectBadBijectionAndLatentValuesBeforeCacheHit(t *testing.T) {
	model, _ := compactConstantModel(t)
	valid := []float64{10, 20, 30}
	if _, err := model.bindConstants(valid); err != nil {
		t.Fatal(err)
	}
	for _, bad := range [][]float64{{10, 20}, {10, 20, 30, 40}, {10, 20, math.NaN()}, {10, 20, math.Inf(1)}, {10, 20, math.Inf(-1)}} {
		if _, err := model.bindConstants(bad); err == nil {
			t.Fatalf("invalid dense values accepted: %#v", bad)
		}
	}

	// The valid vector has a cached damage projection; a latent NaN still fails before lookup.
	if _, err := model.bindConstants([]float64{10, 20, math.NaN()}); err == nil {
		t.Fatal("cached live projection hid a nonfinite latent port")
	}

	// Same-length formula inputs with one unknown key must fail the full bijection.
	keys := model.binding.Keys()
	ports := model.binding.Ports()
	ports[0].Key = "missing-neutral-key"
	member := compactFormulaMember(t)
	prepared, err := formula.PrepareParametric([]*formula.CompiledMember{member}, ports)
	if err != nil {
		t.Fatal(err)
	}
	wrong := &NeutralModel{binding: model.binding, prepared: prepared}
	if _, err := wrong.bindConstants(valid); err == nil {
		t.Fatal("missing key in neutral/formula bijection accepted", keys)
	}
}

func compactFormulaMember(t *testing.T) *formula.CompiledMember {
	t.Helper()
	member := contracts.IRSeedMember{Seed: 1, DurationMS: 1000, TopologySHA256: strings.Repeat("b", 64),
		Nodes: []contracts.IRNode{
			{NodeID: 1, Operation: "constant", Value: "0", Inputs: []contracts.IRInput{}},
			{NodeID: 2, Operation: "constant", Value: "0", Inputs: []contracts.IRInput{}},
			{NodeID: 3, Operation: "constant", Value: "0", Inputs: []contracts.IRInput{}},
			{NodeID: 4, Operation: "artifact_stat", Coordinate: "actor_a.atk", Inputs: []contracts.IRInput{}},
			{NodeID: 5, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "a"}, {NodeID: 2, Relation: "b"}, {NodeID: 4, Relation: "artifact"}}},
		},
		Channels:         []contracts.IRChannel{{ChannelID: "synthetic", Kind: "direct", ActorKey: "actor_a", AttackTag: "skill", DamageType: "synthetic", RootNodeID: 5, HitCount: 1, BaselineDamage: "0", ResponseCoordinates: []string{"actor_a.atk"}}},
		OpaqueBoundaries: []contracts.IROpaqueBoundary{},
	}
	compiled, err := formula.CompileSeedMember(member, []string{"actor_a", "actor_b", "actor_c", "actor_d"}, []string{"actor_a.atk"})
	if err != nil {
		t.Fatal(err)
	}
	return compiled
}

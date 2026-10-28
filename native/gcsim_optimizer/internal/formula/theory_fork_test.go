package formula

import (
	"maps"
	"math"
	"reflect"
	"testing"
)

func TestArtifactProgramTheoryForkOwnsPreviousAndValueScratch(t *testing.T) {
	_, member := parametricMember(t, 1000)
	prepared, err := PrepareParametric([]*CompiledMember{member}, nil)
	if err != nil {
		t.Fatal(err)
	}
	parent := prepared.program
	point := []float64{1, 7}
	want, err := parent.Evaluate(point)
	if err != nil || !parent.previousValid {
		t.Fatalf("fixture did not initialize incremental scratch: %v", err)
	}
	values, previous := append([]float64(nil), parent.values...), append([]float64(nil), parent.previous...)
	branch, sibling := parent.ForkTheory(), parent.ForkTheory()
	if &branch.values[0] == &parent.values[0] || &branch.previous[0] == &parent.previous[0] || &branch.values[0] == &sibling.values[0] {
		t.Fatal("fork shares evaluation scratch")
	}
	if &branch.nodes[0] != &parent.nodes[0] || branch.root != parent.root || !reflect.DeepEqual(branch.coordinates, parent.coordinates) {
		t.Fatal("fork changed immutable arithmetic identity")
	}
	if _, err := branch.Evaluate([]float64{-2, 9}); err != nil {
		t.Fatal(err)
	}
	branch.previousValid, branch.unresolved = false, true
	if !reflect.DeepEqual(parent.values, values) || !reflect.DeepEqual(parent.previous, previous) || !parent.previousValid || parent.unresolved ||
		!reflect.DeepEqual(sibling.values, values) || !reflect.DeepEqual(sibling.previous, previous) {
		t.Fatal("branch evaluation or proof status changed parent/sibling scratch")
	}
	got, err := parent.Evaluate(point)
	if err != nil || math.Float64bits(got) != math.Float64bits(want) {
		t.Fatalf("parent's unchanged-input reuse was corrupted: got %g want %g err %v", got, want, err)
	}
}

func TestParametricProgramTheoryForkOwnsSpecializationFIFOAndKeepsSourceIdentity(t *testing.T) {
	_, member := parametricMember(t, 1000)
	prepared, err := PrepareParametric([]*CompiledMember{member}, []EffectPort{{0, 1, "bonus", 20}})
	if err != nil {
		t.Fatal(err)
	}
	parent := prepared.WithSpecializationCache(NewSpecializationCache(1, 1000))
	if _, err := parent.Specialize([]float64{1, 7}, []float64{2}, 0); err != nil {
		t.Fatal(err)
	}
	cache := parent.specializations
	stats, key := cache.Stats(), cache.order[0]
	retainedValues := append([]float64(nil), cache.entries[key].values...)
	branch := parent.ForkTheory()
	if branch.specializations == cache || branch.specializationSource != parent.specializationSource || branch.specializations.order[0] != key {
		t.Fatal("fork shared the cache or changed specialization source identity")
	}
	if branch.specializations.entries[key] == cache.entries[key] || &branch.specializations.entries[key].values[0] == &cache.entries[key].values[0] {
		t.Fatal("retained specialization scratch was not forked")
	}
	branch.specializations.entries[key].values[0] = 999
	if !reflect.DeepEqual(cache.entries[key].values, retainedValues) {
		t.Fatal("retained child scratch mutation reached the parent cache")
	}
	if _, err := branch.Specialize([]float64{3, 7}, []float64{2}, 0); err != nil || branch.specializations.Stats().Hits != stats.Hits+1 {
		t.Fatalf("fork missed a retained exact specialization: %+v %v", branch.specializations.Stats(), err)
	}
	if _, err := branch.Specialize([]float64{3, 8}, []float64{2}, 0); err != nil {
		t.Fatal(err)
	}
	if branch.specializations.entries[key] != nil || branch.specializations.Stats().Entries != 1 {
		t.Fatal("child did not exercise its own FIFO eviction")
	}
	if cache.Stats() != stats || cache.order[0] != key || cache.entries[key] == nil {
		t.Fatal("child lookup/eviction changed the parent cache or counters")
	}
	retained, err := parent.Specialize([]float64{3, 7}, []float64{2}, 0)
	if err != nil || cache.Stats().Hits != stats.Hits+1 {
		t.Fatalf("parent lost its retained cache entry: %+v %v", cache.Stats(), err)
	}
	value, err := retained.Evaluate([]float64{3})
	if err != nil || value != 25*27 {
		t.Fatalf("parent specialization arithmetic changed: %g %v", value, err)
	}
}

func theoryWideRegionProgram(t *testing.T) *ParametricProgram {
	t.Helper()
	b := newProgramBuilder([]string{"provider.em", "recipient.atk", "effect:a", "effect:b"})
	add := func(op uint8, coordinate int, inputs ...uint32) uint32 {
		id, err := b.add(compiledNode{op: op, coordinate: coordinate, inputs: inputs})
		if err != nil {
			t.Fatal(err)
		}
		return id
	}
	a, other := add(opArtifactStat, 0), add(opArtifactStat, 1)
	x, y := add(opArtifactStat, 2), add(opArtifactStat, 3)
	root := add(opAdd, -1, a, x, other, y, a)
	return &ParametricProgram{program: b.finish(root), artifactCount: 2, effects: []string{"a", "b"}, actors: []string{"provider", "recipient"}, input: make([]float64, 4)}
}

func TestParametricProgramTheoryForkOwnsRegionArenaAndBindingScratch(t *testing.T) {
	parent := theoryWideRegionProgram(t)
	if _, err := parent.BindConstantEffectsRegions([]float64{1, 2}); err != nil {
		t.Fatal(err)
	}
	r := parent.regions
	if r == nil || len(r.arena.wideMemo) == 0 {
		t.Fatal("fixture did not initialize a wide-node arena")
	}
	// Spare capacity makes an accidental shared append observable after each
	// branch extends the arena with different constants.
	ownedNodes := make([]compiledNode, len(r.arena.program.nodes), len(r.arena.program.nodes)+64)
	copy(ownedNodes, r.arena.program.nodes)
	r.arena.program.nodes = ownedNodes
	mapped, changed := append([]uint32(nil), r.mapped...), append([]bool(nil), r.changed...)
	values := append([]float64(nil), r.values...)
	live, exported, exportMap := append([]uint32(nil), r.liveStamp...), append([]uint32(nil), r.exportedStamp...), append([]uint32(nil), r.exportMap...)
	memo, wideMemo := maps.Clone(r.arena.memo), maps.Clone(r.arena.wideMemo)
	nodes, arenaValues := append([]compiledNode(nil), r.arena.program.nodes...), append([]float64(nil), r.arena.program.values...)
	stats, generation, inputCount := parent.regionStats, r.generation, r.inputCount
	branch := parent.ForkTheory()
	if branch.regions == r || branch.regions.arena == r.arena || branch.regions.arena.program == r.arena.program {
		t.Fatal("fork shared mutable region objects")
	}
	check := func(program *ParametricProgram, effects []float64) {
		t.Helper()
		got, err := program.BindConstantEffectsRegions(effects)
		want, oracleErr := program.BindConstantEffects(effects)
		if err != nil || oracleErr != nil || got.program.root != want.program.root || !reflect.DeepEqual(got.program.nodes, want.program.nodes) {
			t.Fatalf("fork changed ordered region arithmetic: %v %v", err, oracleErr)
		}
		value, gradient, _, err := got.program.ValueGradient([]float64{5, 7})
		oracle, oracleGradient, _, oracleErr := want.program.ValueGradient([]float64{5, 7})
		if err != nil || oracleErr != nil || math.Float64bits(value) != math.Float64bits(oracle) || !reflect.DeepEqual(gradient, oracleGradient) {
			t.Fatalf("fork changed exact value/gradient: %g %g %v %v", value, oracle, err, oracleErr)
		}
	}
	check(branch, []float64{3, 4})
	if parent.regionStats != stats || r.generation != generation || r.inputCount != inputCount ||
		!reflect.DeepEqual(r.mapped, mapped) || !reflect.DeepEqual(r.changed, changed) || !reflect.DeepEqual(r.values, values) ||
		!reflect.DeepEqual(r.liveStamp, live) || !reflect.DeepEqual(r.exportedStamp, exported) || !reflect.DeepEqual(r.exportMap, exportMap) ||
		!reflect.DeepEqual(r.arena.memo, memo) || !reflect.DeepEqual(r.arena.wideMemo, wideMemo) ||
		!reflect.DeepEqual(r.arena.program.nodes, nodes) || !reflect.DeepEqual(r.arena.program.values, arenaValues) {
		t.Fatal("child binding changed parent arena, scratch, or counters")
	}
	check(parent, []float64{5, 6})
	parentStats := parent.regionStats
	check(branch, []float64{3, 4})
	if parent.regionStats != parentStats {
		t.Fatal("child reuse changed parent binding counters")
	}
}

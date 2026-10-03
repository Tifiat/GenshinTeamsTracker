package seteffects

import (
	"fmt"
	"math"
	"reflect"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

func TestNeutralCompactCompositionMatchesMapAndKeepsSourceBoundaries(t *testing.T) {
	keys := []string{"resistance", "stat_a", "stat_b"}
	curveRows, err := ExtractScalarSlices([]byte(scalarWitness), "Resistance", "ResMod")
	if err != nil || len(curveRows) != 1 {
		t.Fatal(curveRows, err)
	}
	neutral := ruleTestNeutral()
	ports := []neutralBoundPort{
		{dimension: 0, resistance: .5, observed: .5, curve: &curveRows[0]},
		{dimension: 1}, {dimension: 2},
	}
	first, second := RuleChoice{Owner: 0, Key: "synthetic_a", Pieces: 4}, RuleChoice{Owner: 1, Key: "synthetic_b", Pieces: 4}
	component := func(raw []float64) neutralComponent { return neutralComponent{raw: raw, usable: true} }
	binding := &NeutralBinding{
		catalog: &SourceCatalog{Sets: []DiscoveredSet{{Key: first.Key}, {Key: second.Key}}},
		members: []neutralBoundMember{{neutral: neutral, ports: ports}}, keys: keys,
		components: map[RuleChoice]neutralComponent{
			first:  component([]float64{-.3, 2, 0}),
			second: component([]float64{-.3, 3, 0}),
		},
	}
	choices := []RuleChoice{first, second}
	mapResult := binding.CompilePackages(choices)
	denseResult := binding.CompilePackagesCompact(choices)
	if !mapResult.Complete() || !denseResult.Complete() || mapResult.Constants != nil || denseResult.Effects != nil {
		t.Fatalf("unexpected representation/boundary: map=%+v compact=%+v", mapResult, denseResult)
	}
	if !reflect.DeepEqual(mapResult.Uncertainty, denseResult.Uncertainty) || len(denseResult.Constants) != len(keys) || len(mapResult.Effects) != len(keys) {
		t.Fatalf("composition metadata mismatch: map=%+v compact=%+v", mapResult, denseResult)
	}
	for i, key := range keys {
		expression := mapResult.Effects[key]
		if expression == nil || expression.Operation != "constant" || len(expression.Inputs) != 0 || expression.Value != denseResult.Constants[i] {
			t.Fatalf("port %q differs: map=%+v dense=%v", key, expression, denseResult.Constants[i])
		}
	}
	postSum, err := curveRows[0].Evaluate(.5 - .3 - .3)
	if err != nil || math.Abs(denseResult.Constants[0]-(postSum-.5)) > 1e-12 {
		t.Fatalf("resistance was not transformed after raw summation: got=%v want=%v err=%v", denseResult.Constants[0], postSum-.5, err)
	}
	separate, _ := curveRows[0].Evaluate(.5 - .3)
	if denseResult.Constants[0] == 2*(separate-.5) {
		t.Fatal("resistance increments were transformed separately before summing")
	}

	zeroMap, zeroDense := binding.CompilePackages(nil), binding.CompilePackagesCompact(nil)
	if !zeroMap.Complete() || !zeroDense.Complete() || zeroDense.Constants[0] != 0 || zeroMap.Effects[keys[0]].Value != 0 {
		t.Fatalf("zero package did not preserve exact zero: map=%+v compact=%+v", zeroMap, zeroDense)
	}
	invalid := binding.CompilePackagesCompact([]RuleChoice{{Owner: 0, Key: first.Key, Pieces: 4}, {Owner: 0, Key: second.Key, Pieces: 2}})
	if invalid.Complete() || len(invalid.Boundaries) == 0 || invalid.Constants != nil {
		t.Fatalf("illegal source package became dense constants: %+v", invalid)
	}

	unknown := &NeutralBinding{catalog: &SourceCatalog{}, members: []neutralBoundMember{{neutral: neutral, ports: []neutralBoundPort{{dimension: 0}}}}, keys: keys[:1]}
	boundary := unknown.CompilePackagesCompact([]RuleChoice{{Owner: 0, Key: "missing_source_set", Pieces: 2}})
	if boundary.Complete() || boundary.Constants != nil || len(boundary.Boundaries) == 0 {
		t.Fatalf("missing source rule was converted to a constant: %+v", boundary)
	}
}

func TestNeutralCompactCompositionFallsBackForSymbolicSourceEffects(t *testing.T) {
	catalog := activeRuleCatalog(t)
	burst := ruleTestConstant(t, catalog, "pkg/core/attacks", "AttackTagElementalBurst")
	neutral := ruleTestNeutral()
	neutral.Context.Active = 2
	neutral.World.States = append(neutral.World.States, contracts.NeutralWorldState{Order: 30, Frame: 20, Active: 2, Modifiers: []contracts.NeutralModifierIdentity{}})
	neutral.ReadsComplete = true
	neutral.Reads = []contracts.NeutralReadRoot{{NodeID: 2, Owner: "gamma", Stat: "er", Observed: "2",
		Point: contracts.NeutralInputPoint{Order: 40, Frame: 20, Mode: "non_extra_stat"}, Uncertainty: []string{}}}
	attack := contracts.EventValue{Kind: "object", Type: "*github.com/genshinsim/gcsim/pkg/core/info.AttackEvent", Fields: map[string]contracts.EventValue{
		"Info": ruleTestAttack(2, burst, 0),
	}}
	neutral.Hits = []contracts.NeutralHitPoint{{HitID: 1, Actor: 2, Attack: &attack,
		Point: contracts.NeutralInputPoint{HitID: 1, HitOrder: 39, HitFrame: 20, AttackOrder: 40}}}
	neutral.Stats = []contracts.NeutralStatInput{{NodeID: 1, Owner: "gamma", Kind: "attack", Stat: "dmg%",
		Point: contracts.NeutralInputPoint{HitID: 1, Order: 40, Frame: 20, Mode: "stat"}}}
	binding, err := NewNeutralBinding(catalog, []contracts.EffectInputsOutput{{SourceManifestBodySHA256: catalog.SourceManifestSHA256, Neutral: neutral}})
	if err != nil {
		t.Fatal(err)
	}
	choice := RuleChoice{Owner: 2, Key: "emblemofseveredfate", Pieces: 4}
	// A stat-dependent isolated result is deliberately not eligible for additive composition.
	binding.components[choice] = neutralComponent{usable: false, footprint: ruleFootprint{statDependent: true}}
	result := binding.CompilePackagesCompact([]RuleChoice{choice})
	if !result.Complete() || result.Constants != nil || len(result.Effects) != 1 || binding.PreparationStats().FullFallbacks != 1 {
		t.Fatalf("symbolic source result did not fall back to expression binding: result=%+v stats=%+v", result, binding.PreparationStats())
	}
	expression := result.Effects[binding.Keys()[0]]
	if expression == nil || expression.Operation == "constant" || !containsReadKey(expression, "neutral-read:0:2") {
		t.Fatalf("stat-dependent source expression was frozen or lost its neutral root: %+v", expression)
	}
}

func containsReadKey(expression *formula.InputExpression, key string) bool {
	if expression == nil {
		return false
	}
	if expression.Operation == "read" && expression.Key == key {
		return true
	}
	for _, input := range expression.Inputs {
		if containsReadKey(input, key) {
			return true
		}
	}
	return false
}

var compactBenchmarkSink NeutralExpressions

func BenchmarkCompactComposition16012Ports(b *testing.B) {
	const portCount = 16012
	keys := make([]string, portCount)
	ports := make([]neutralBoundPort, portCount)
	neutral := ruleTestNeutral()
	for i := range keys {
		keys[i] = fmt.Sprintf("port:%05d", i)
		ports[i].dimension = i
	}
	choices := make([]RuleChoice, 4)
	components := make(map[RuleChoice]neutralComponent, len(choices))
	sets := make([]DiscoveredSet, len(choices))
	for owner := range choices {
		choice := RuleChoice{Owner: owner, Key: fmt.Sprintf("bench_set_%d", owner), Pieces: 4}
		choices[owner], sets[owner] = choice, DiscoveredSet{Key: choice.Key}
		raw := make([]float64, portCount)
		for i := range raw {
			raw[i] = float64((owner+1)*(i%17+1)) / 1000
		}
		components[choice] = neutralComponent{raw: raw, usable: true}
	}
	binding := &NeutralBinding{catalog: &SourceCatalog{Sets: sets}, keys: keys,
		members: []neutralBoundMember{{neutral: neutral, ports: ports}}, components: components}
	mapResult := binding.CompilePackages(choices)
	denseResult := binding.CompilePackagesCompact(choices)
	if !mapResult.Complete() || !denseResult.Complete() || len(denseResult.Constants) != portCount || len(mapResult.Effects) != portCount {
		b.Fatal("synthetic parity setup did not produce complete outputs")
	}
	for i, key := range keys {
		if mapResult.Effects[key] == nil || mapResult.Effects[key].Value != denseResult.Constants[i] {
			b.Fatalf("port %d parity mismatch", i)
		}
	}
	b.Run("map", func(b *testing.B) {
		b.ReportAllocs()
		b.ResetTimer()
		for i := 0; i < b.N; i++ {
			compactBenchmarkSink = binding.CompilePackages(choices)
		}
	})
	b.Run("dense", func(b *testing.B) {
		b.ReportAllocs()
		b.ResetTimer()
		for i := 0; i < b.N; i++ {
			compactBenchmarkSink = binding.CompilePackagesCompact(choices)
		}
	})
}

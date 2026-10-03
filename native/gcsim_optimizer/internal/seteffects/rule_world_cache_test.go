package seteffects

import (
	"fmt"
	"reflect"
	"sort"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestRuleTouchedIdentityKeepsOwnerTargetAndDeletionSeparate(t *testing.T) {
	h := &ruleReplayHost{stateComplete: true,
		touched: map[ruleModifierIdentity]bool{{owner: 0, target: -1, key: "same"}: true,
			{owner: -1, target: 7, key: "same"}: true},
		state: []RuleState{{Owner: 0, Key: "same", Expiry: -1}, {Owner: 1, Key: "same", Expiry: -1}}}
	if h.statusActive(0, "same") || !h.statusActive(1, "same") {
		t.Fatal("deletion leaked across character identity")
	}
	for _, target := range []int{7, 8} {
		_, err := ruleTry(func() any {
			return h.query(RuleQuery{Owner: 2, Target: target, Kind: "resistance", TargetKeys: []string{"same"}})
		})
		if (err != nil) != (target == 7) {
			t.Fatal("target replacement identity changed", target, err)
		}
	}
}

func ruleWorldCacheFixture(first, second string, firstTarget, secondTarget int) *contracts.NeutralWorldLedger {
	state := func(order uint64, marker string, target int) contracts.NeutralWorldState {
		return contracts.NeutralWorldState{
			Order: order,
			Facts: &contracts.EventValue{Kind: "object", Fields: map[string]contracts.EventValue{
				"Identity": {Kind: "string", Text: marker},
			}},
			Targets: []contracts.EventValue{{Kind: "target", Fields: map[string]contracts.EventValue{
				"Key":      {Kind: "number", Number: float64(target)},
				"Identity": {Kind: "string", Text: marker},
			}}},
			Modifiers: []contracts.NeutralModifierIdentity{{Owner: 0, Key: marker, Expiry: 50}},
		}
	}
	return &contracts.NeutralWorldLedger{
		Complete: true,
		States:   []contracts.NeutralWorldState{state(10, first, firstTarget), state(20, second, secondTarget)},
	}
}

func TestRuleWorldAtCachesOnlySameSnapshotAndIndex(t *testing.T) {
	first := ruleWorldCacheFixture("first", "later", 7, 8)
	h := &ruleReplayHost{}
	h.worldAt(first, 15)
	if !h.stateComplete || h.worldView.world != first || h.worldView.index != 0 || len(h.state) != 1 || h.state[0].Key != "first" {
		t.Fatal("initial world baseline was not selected", h.stateComplete, h.worldView, h.state)
	}
	baselineState := h.worldView.state

	// A query's complete state is an override for that query only. A subsequent
	// lookup at the same snapshot/index must restore the converted world baseline.
	h.state = []RuleState{{Owner: 9, Key: "query-only", Expiry: -1}}
	h.stateComplete = true
	h.targets = map[int]contracts.EventValue{}
	h.facts = nil
	h.worldAt(first, 19)
	if !h.stateComplete || len(h.state) != 1 || h.state[0].Key != "first" || &h.state[0] != &baselineState[0] {
		t.Fatal("same-world cache hit did not restore its baseline state", h.stateComplete, h.state)
	}
	if h.facts == nil || h.facts.Fields["Identity"].Text != "first" || h.targets[7].Fields["Identity"].Text != "first" {
		t.Fatal("same-world cache hit did not restore baseline facts and targets", h.facts, h.targets)
	}

	// A different immutable ledger at the same state index must replace the
	// single-entry host cache, and switching back must convert the first ledger.
	second := ruleWorldCacheFixture("other-first", "other-later", 7, 8)
	h.worldAt(second, 15)
	if h.worldView.world != second || h.worldView.index != 0 || h.state[0].Key != "other-first" || h.facts.Fields["Identity"].Text != "other-first" || h.targets[7].Fields["Identity"].Text != "other-first" {
		t.Fatal("different-world lookup reused stale converted fields", h.worldView, h.state)
	}
	h.worldAt(first, 15)
	if h.worldView.world != first || h.state[0].Key != "first" || h.targets[7].Fields["Identity"].Text != "first" {
		t.Fatal("switching back reused a different world's converted fields", h.worldView, h.state)
	}
}

func TestRuleWorldAtBackwardAndInvalidLookups(t *testing.T) {
	world := ruleWorldCacheFixture("first", "later", 7, 8)
	h := &ruleReplayHost{}
	h.worldAt(world, 25)
	if h.worldView.index != 1 || h.state[0].Key != "later" || h.targets[8].Fields["Identity"].Text != "later" {
		t.Fatal("latest snapshot was not selected", h.worldView, h.state)
	}
	h.worldAt(world, 15)
	if !h.stateComplete || h.worldView.index != 0 || h.state[0].Key != "first" || h.targets[7].Fields["Identity"].Text != "first" {
		t.Fatal("backward lookup did not select the earlier snapshot", h.worldView, h.state)
	}

	h.worldAt(world, 9)
	if h.stateComplete || h.state != nil || h.targets != nil || h.facts != nil || h.worldView.valid {
		t.Fatal("lookup before first snapshot retained a previous world", h.stateComplete, h.state, h.targets, h.facts, h.worldView)
	}
	incomplete := &contracts.NeutralWorldLedger{Complete: false, States: world.States}
	h.worldAt(incomplete, 25)
	if h.stateComplete || h.state != nil || h.targets != nil || h.facts != nil || h.worldView.valid {
		t.Fatal("incomplete world retained a previous baseline", h.stateComplete, h.state, h.targets, h.facts, h.worldView)
	}
	h.worldAt(nil, 25)
	if h.stateComplete || h.state != nil || h.targets != nil || h.facts != nil || h.worldView.valid {
		t.Fatal("nil world retained a previous baseline", h.stateComplete, h.state, h.targets, h.facts, h.worldView)
	}
}

func ruleWorldAtOriginalConversion(world *contracts.NeutralWorldLedger, order uint64) (*contracts.EventValue, []RuleState, map[int]contracts.EventValue, bool) {
	if world == nil || !world.Complete {
		return nil, nil, nil, false
	}
	i := sort.Search(len(world.States), func(i int) bool { return world.States[i].Order > order }) - 1
	if i < 0 {
		return nil, nil, nil, false
	}
	facts := world.States[i].Facts
	var state []RuleState
	for _, modifier := range world.States[i].Modifiers {
		state = append(state, RuleState{modifier.Owner, modifier.Key, modifier.Expiry})
	}
	targets := map[int]contracts.EventValue{}
	for _, target := range world.States[i].Targets {
		if key, ok := target.Fields["Key"]; ok && key.Kind == "number" {
			targets[int(key.Number)] = target
		}
	}
	return facts, state, targets, true
}

func TestRuleWorldAtMatchesOriginalConversionAcrossLookups(t *testing.T) {
	first := ruleWorldCacheFixture("first", "later", 7, 8)
	second := ruleWorldCacheFixture("other-first", "other-later", 7, 8)
	emptyState := ruleWorldCacheFixture("empty", "later", 7, 8)
	emptyState.States[0].Modifiers = nil
	incomplete := &contracts.NeutralWorldLedger{Complete: false, States: first.States}
	lookups := []struct {
		world *contracts.NeutralWorldLedger
		order uint64
	}{
		{first, 15}, {first, 19}, {second, 15}, {first, 25}, {first, 15},
		{first, 9}, {emptyState, 15}, {incomplete, 15}, {nil, 15},
	}
	h := &ruleReplayHost{}
	for i, lookup := range lookups {
		h.worldAt(lookup.world, lookup.order)
		wantFacts, wantState, wantTargets, wantComplete := ruleWorldAtOriginalConversion(lookup.world, lookup.order)
		if !reflect.DeepEqual(h.facts, wantFacts) || !reflect.DeepEqual(h.state, wantState) || !reflect.DeepEqual(h.targets, wantTargets) || h.stateComplete != wantComplete {
			t.Fatalf("lookup %d differs from original conversion:\n facts: got %#v want %#v\n state: got %#v want %#v\n targets: got %#v want %#v\n complete: got %v want %v", i, h.facts, wantFacts, h.state, wantState, h.targets, wantTargets, h.stateComplete, wantComplete)
		}
		if i%2 == 0 && wantComplete {
			// Exercise the per-query complete-state override between lookups.
			h.state = []RuleState{{Owner: 9, Key: "query-only", Expiry: -1}}
			h.stateComplete = true
			h.facts = nil
			h.targets = map[int]contracts.EventValue{}
		}
	}
}

var ruleWorldAtBenchmarkSink int

func BenchmarkRuleWorldAtCachedVsOriginalConversion(b *testing.B) {
	// A long observed rotation commonly has thousands of world points while each
	// point carries a small modifier set and a few enemy targets. The cached case
	// deliberately repeats one world/index, so it measures cache-hit best case.
	const stateCount, modifierCount, targetCount = 2048, 12, 4
	facts := &contracts.EventValue{Kind: "object", Fields: map[string]contracts.EventValue{
		"Identity": {Kind: "string", Text: "benchmark"},
	}}
	targets := make([]contracts.EventValue, targetCount)
	for i := range targets {
		targets[i] = contracts.EventValue{Kind: "target", Fields: map[string]contracts.EventValue{
			"Key":      {Kind: "number", Number: float64(i)},
			"Identity": {Kind: "string", Text: fmt.Sprintf("target-%d", i)},
		}}
	}
	world := &contracts.NeutralWorldLedger{Complete: true, States: make([]contracts.NeutralWorldState, stateCount)}
	for i := range world.States {
		modifiers := make([]contracts.NeutralModifierIdentity, modifierCount)
		for j := range modifiers {
			modifiers[j] = contracts.NeutralModifierIdentity{Owner: j % 4, Key: fmt.Sprintf("modifier-%d", j), Expiry: i + 100}
		}
		world.States[i] = contracts.NeutralWorldState{
			Order: uint64(i + 1), Frame: i * 2, Active: i % 4,
			Facts: facts, Targets: targets, Modifiers: modifiers,
		}
	}
	order := world.States[1535].Order

	b.Run("cached_same_world_index", func(b *testing.B) {
		h := &ruleReplayHost{}
		h.worldAt(world, order)
		b.ReportAllocs()
		b.ResetTimer()
		for i := 0; i < b.N; i++ {
			h.worldAt(world, order)
			ruleWorldAtBenchmarkSink = len(h.state) + len(h.targets)
		}
	})
	b.Run("original_conversion", func(b *testing.B) {
		b.ReportAllocs()
		b.ResetTimer()
		for i := 0; i < b.N; i++ {
			_, state, targetMap, _ := ruleWorldAtOriginalConversion(world, order)
			ruleWorldAtBenchmarkSink = len(state) + len(targetMap)
		}
	})
}

package seteffects

import (
	"math"
	"reflect"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func targetGuardHealEvent() contracts.CombatEvent {
	number := func(value float64) contracts.EventValue {
		return contracts.EventValue{Kind: "number", Number: value}
	}
	return contracts.CombatEvent{
		Order: 100, EndOrder: 101, Frame: 10, Active: 1, Event: 7,
		Arguments: []contracts.EventValue{
			{Kind: "object", Type: "*" + gcsimImport + "pkg/core/info.HealInfo", Fields: map[string]contracts.EventValue{
				"Caller": number(1), "Src": number(10), "Bonus": number(.15),
				"Nested": {Kind: "array", Items: []contracts.EventValue{number(3)}},
			}},
			number(1), number(5000), number(0), number(5000),
		},
	}
}

func TestRuleEmitUsesOwnedHealArgumentsAcrossSubscriptions(t *testing.T) {
	for _, symbolic := range []bool{false, true} {
		t.Run(map[bool]string{false: "ordinary", true: "symbolic"}[symbolic], func(t *testing.T) {
			vm := testRule(t, `import (
	e "github.com/genshinsim/gcsim/pkg/core/event"
	"github.com/genshinsim/gcsim/pkg/core/info"
)
func Start(events any, symbolic bool) any {
	accepted := false
	var first, second any
	events.Subscribe(e.OnHeal, func(args ...any) {
		// Rebind the caller/recipient arguments and mutate fresh nested values.
		// Event objects and arrays are intentionally read-only in this VM.
		first = args[0]
		args[0] = nil
		args[1] = 99
		nested := make([][]int, 1)
		nested[0] = make([]int, 1)
		nested[0][0] = 99
		args[2] = nested
		object := map[int]int{0: 1}
		object[0] = 99
		args[3] = object
	}, "mutator")
	events.Subscribe(e.OnHeal, func(args ...any) {
		payload := args[0].(*info.HealInfo)
		second = args[0]
		accepted = payload.Caller == 1 && payload.Nested[0] == 3 && args[1].(float64) == 1
		if !symbolic {
			accepted = accepted && args[2].(float64) == 5000 && args[3].(float64) == 0 && args[4].(float64) == 5000
		}
	}, "reader")
	return func() []any { return []any{accepted, first, second} }
}`, map[string][]byte{
				"pkg/core/event/event.go": []byte("package event; const OnHeal = 7"),
				"pkg/core/info/heal.go":   []byte("package info; type HealInfo struct { Caller int; Src, Bonus float64; Nested []int }"),
			})
			host := &ruleReplayHost{
				subs: map[int][]ruleSubscription{}, uncertainty: map[string]bool{}, symbolic: symbolic,
			}
			vm.host, host.vm = host, vm
			accepted, err := vm.entry("Start", ruleRef{kind: "events"}, symbolic)
			if err != nil {
				t.Fatal(err)
			}
			event, original := targetGuardHealEvent(), targetGuardHealEvent()
			if err := host.emit(event); err != nil {
				t.Fatal(err)
			}
			result, err := ruleTry(func() any { return vm.invoke(accepted, nil) })
			if err != nil {
				t.Fatal(err)
			}
			captured := ruleArray(result)
			if len(captured) != 3 || captured[0] != true {
				t.Fatalf("second subscription saw leaked event values: captured=%v", captured)
			}
			first, firstOK := captured[1].(*ruleObject)
			second, secondOK := captured[2].(*ruleObject)
			if !firstOK || !secondOK || first == second || first.fields == nil || second.fields == nil {
				t.Fatalf("subscriptions did not receive separate event objects: %T %T", captured[1], captured[2])
			}
			firstNested, firstNestedOK := first.fields["Nested"].(*ruleSlice)
			secondNested, secondNestedOK := second.fields["Nested"].(*ruleSlice)
			if !firstNestedOK || !secondNestedOK || firstNested == secondNested {
				t.Fatalf("subscriptions did not receive separate nested arrays: %T %T", first.fields["Nested"], second.fields["Nested"])
			}
			// Mutating the first callback's captured graph through the Go test
			// internals cannot affect the second callback's independent wire value.
			first.fields["Caller"] = float64(99)
			firstNested.values[0] = float64(99)
			if ruleNumber(second.fields["Caller"]) != 1 || ruleNumber(secondNested.values[0]) != 3 {
				t.Fatal("a mutation to one subscription's captured event leaked to another")
			}
			if !reflect.DeepEqual(event, original) {
				t.Fatalf("callback changed the caller-owned CombatEvent: got=%+v want=%+v", event, original)
			}
			if !host.uncertainty["set_activation_heal_amount_frozen_to_observed_build"] {
				t.Fatal("heal replay uncertainty provenance was not retained")
			}
		})
	}
}

func TestRuleEmitRejectsObservedHealPayloadMutation(t *testing.T) {
	for _, mutation := range []struct {
		name, expression, boundary string
	}{
		{"object field", `args[0].(*info.HealInfo).Caller = 9`, "event payload mutation"},
		{"nested slice", `args[0].(*info.HealInfo).Nested[0] = 9`, "event stat mutation needs a bound output expression"},
	} {
		t.Run(mutation.name, func(t *testing.T) {
			vm := testRule(t, `import (
	e "github.com/genshinsim/gcsim/pkg/core/event"
	"github.com/genshinsim/gcsim/pkg/core/info"
)
func Start(events any) any {
	secondRan := false
	events.Subscribe(e.OnHeal, func(args ...any) { `+mutation.expression+` }, "mutator")
	events.Subscribe(e.OnHeal, func(args ...any) { secondRan = true }, "reader")
	return func() bool { return secondRan }
}`, map[string][]byte{
				"pkg/core/event/event.go": []byte("package event; const OnHeal = 7"),
				"pkg/core/info/heal.go":   []byte("package info; type HealInfo struct { Caller int; Src, Bonus float64; Nested []int }"),
			})
			host := &ruleReplayHost{subs: map[int][]ruleSubscription{}, uncertainty: map[string]bool{}}
			vm.host, host.vm = host, vm
			secondRan, err := vm.entry("Start", ruleRef{kind: "events"})
			if err != nil {
				t.Fatal(err)
			}
			event, original := targetGuardHealEvent(), targetGuardHealEvent()
			err = host.emit(event)
			if err == nil || !strings.Contains(err.Error(), mutation.boundary) {
				t.Fatalf("observed payload mutation was not rejected: %v", err)
			}
			result, invokeErr := ruleTry(func() any { return vm.invoke(secondRan, nil) })
			if invokeErr != nil || result != false {
				t.Fatalf("later subscriber ran after rejected mutation: result=%v err=%v", result, invokeErr)
			}
			if !reflect.DeepEqual(event, original) {
				t.Fatalf("rejected callback changed the caller-owned CombatEvent: got=%+v want=%+v", event, original)
			}
		})
	}
}

func TestRuleActiveHealGuardOrdinaryAndSymbolicContracts(t *testing.T) {
	catalog := activeRuleCatalog(t)
	number := func(value float64) contracts.EventValue {
		return contracts.EventValue{Kind: "number", Number: value}
	}
	onHeal := int(ruleTestConstant(t, catalog, "pkg/core/event", "OnHeal"))
	onEnemyHit := int(ruleTestConstant(t, catalog, "pkg/core/event", "OnEnemyHit"))

	t.Run("Marechaussee", func(t *testing.T) {
		makeInputs := func() *contracts.NeutralInputs {
			n := ruleTestNeutral()
			n.World.States[0].Facts = ruleResourceFacts()
			n.Hitlag = &contracts.NeutralHitlagLedger{Complete: true}
			n.Ledger.Events = []contracts.CombatEvent{{
				Order: 100, EndOrder: 101, Frame: 10, Active: 1, Event: onHeal,
				Arguments: []contracts.EventValue{{Kind: "nil"}, number(1), number(5000), number(0), number(5000)},
			}}
			return n
		}
		choice := []RuleChoice{{Owner: 1, Key: "marechausseehunter", Pieces: 4}}
		query := []RuleQuery{{Order: 200, Frame: 20, Active: 1, Owner: 1, Kind: "stat", Stat: "cr", Mode: "stat"}}
		observed := catalog.ReplayNeutralRules(makeInputs(), choice, query)
		if observed.Boundary != "" || len(observed.Values) != 1 || !observed.Values[0].Known || math.Abs(observed.Values[0].Value-.12) > 1e-12 {
			t.Fatalf("ordinary observed source replay changed the .12 value: %+v", observed)
		}
		symbolic := catalog.CompileNeutralRules(makeInputs(), choice, query)
		if !strings.Contains(symbolic.Boundary, "neutral heal amount has no bound health-operation expression") {
			t.Fatalf("symbolic heal amount was not rejected at the explicit health boundary: %+v", symbolic)
		}
	})

	t.Run("Song", func(t *testing.T) {
		makeInputs := func() *contracts.NeutralInputs {
			n := ruleTestNeutral()
			n.World.States[0].Facts = ruleResourceFacts()
			attackInfo := ruleTestAttack(1,
				ruleTestConstant(t, catalog, "pkg/core/attacks", "AttackTagNormal"),
				ruleTestConstant(t, catalog, "pkg/core/attributes", "Physical"))
			attackInfo.Fields["FlatDmg"] = number(17)
			attack := contracts.EventValue{Kind: "object", Type: "*" + gcsimImport + "pkg/core/info.AttackEvent", Fields: map[string]contracts.EventValue{
				"Info": attackInfo, "HitID": number(7),
			}}
			healInfo := contracts.EventValue{Kind: "object", Type: "*" + gcsimImport + "pkg/core/info.HealInfo", Fields: map[string]contracts.EventValue{
				"Caller": number(1),
			}}
			n.Ledger.Events = []contracts.CombatEvent{
				{Order: 100, EndOrder: 101, Frame: 10, Active: 1, Event: onHeal,
					Arguments: []contracts.EventValue{healInfo, number(1), number(5000), number(5000), number(10000)}},
				{Order: 3900, EndOrder: 3901, Frame: 390, Active: 1, Event: onEnemyHit,
					Arguments: []contracts.EventValue{{Kind: "nil"}, attack}},
			}
			return n
		}
		choice := []RuleChoice{{Owner: 1, Key: "songofdayspast", Pieces: 4}}
		query := []RuleQuery{{Order: 4000, Frame: 400, Active: 1, Owner: 1, Kind: "flat_event", Stat: "FlatDmg", HitID: 7}}
		observed := catalog.ReplayNeutralRules(makeInputs(), choice, query)
		if observed.Boundary != "" || len(observed.Values) != 1 || !observed.Values[0].Known || observed.Values[0].Value != 800 {
			t.Fatalf("ordinary observed source replay changed the 800 value: %+v", observed)
		}
		symbolic := catalog.CompileNeutralRules(makeInputs(), choice, query)
		if !strings.Contains(symbolic.Boundary, "neutral heal amount has no bound health-operation expression") {
			t.Fatalf("symbolic heal amount was not rejected at the explicit health boundary: %+v", symbolic)
		}
	})
}

// Replays the eight preserved rule_health_boundary_test.go cases without
// taking that old uncommitted fixture as a target source prerequisite.
func TestRuleTargetHealOperandsRequireBinding(t *testing.T) {
	for _, tc := range []struct {
		name, body string
		symbolic   bool
		boundary   string
	}{
		{"raw", "return args[4].(float64) > 0", true, "neutral heal amount"},
		{"received", "return args[2].(float64) > 0", true, "neutral heal amount"},
		{"overheal", "return args[3].(float64) > 0", true, "neutral heal amount"},
		{"source", "return args[0].(*info.HealInfo).Src > 0", true, "neutral heal source operand"},
		{"bonus", "return args[0].(*info.HealInfo).Bonus > 0", true, "neutral heal source operand"},
		{"identity only", "return args[0].(*info.HealInfo).Caller == 1 && args[1].(int) == 1", true, ""},
		{"irrelevant recipient", "if args[1].(int) != 3 { return true }; return args[4].(float64) > 0", true, ""},
		{"observed diagnostic", "return args[4].(float64) > 0", false, ""},
	} {
		t.Run(tc.name, func(t *testing.T) {
			vm := testRule(t, `import (
	e "github.com/genshinsim/gcsim/pkg/core/event"
	"github.com/genshinsim/gcsim/pkg/core/info"
)
func Start() any { _ = e.OnHeal; return func(args ...any) bool { `+tc.body+` } }`, map[string][]byte{
				"pkg/core/event/event.go": []byte("package event; const OnHeal = 7; const OnEnemyHit = 8"),
				"pkg/core/info/heal.go":   []byte("package info; type HealInfo struct { Caller int; Src, Bonus float64 }"),
			})
			callback, err := vm.entry("Start")
			if err != nil {
				t.Fatal(err)
			}
			host := &ruleReplayHost{vm: vm, symbolic: tc.symbolic, uncertainty: map[string]bool{}}
			number := func(value float64) contracts.EventValue {
				return contracts.EventValue{Kind: "number", Number: value}
			}
			payload := host.wire(contracts.EventValue{Kind: "object", Type: "*" + gcsimImport + "pkg/core/info.HealInfo", Fields: map[string]contracts.EventValue{
				"Caller": number(1), "Src": number(10), "Bonus": number(.15),
			}})
			value, err := ruleTry(func() any {
				return host.invokeEvent(ruleSubscription{vm: vm, fn: callback}, contracts.CombatEvent{Event: 7},
					[]any{payload, float64(1), float64(11.5), float64(0), float64(11.5)})
			})
			if tc.boundary != "" {
				if err == nil || !strings.Contains(err.Error(), tc.boundary) {
					t.Fatalf("unbound heal operand became a counterfactual value: value=%v err=%v", value, err)
				}
			} else if err != nil || value != true {
				t.Fatalf("identity/observed diagnostic branch was rejected: value=%v err=%v", value, err)
			}
		})
	}
}

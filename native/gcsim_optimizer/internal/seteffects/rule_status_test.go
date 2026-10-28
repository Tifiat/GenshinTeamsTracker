package seteffects

import (
	"math"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestRuleStatusDurationLifecycle(t *testing.T) {
	h := &ruleReplayHost{frame: 10, stateComplete: true,
		touched: map[ruleModifierIdentity]bool{}, uncertainty: map[string]bool{},
		state: []RuleState{{Owner: 0, Key: "timer", Expiry: 80}}}
	read := func(owner int, key string, want float64) {
		t.Helper()
		value, handled := h.call(ruleRef{kind: "char", index: owner}, "StatusDuration", []any{key})
		if !handled || value != want {
			t.Fatalf("duration %d/%s: %v, handled=%v, want %v", owner, key, value, handled, want)
		}
	}
	read(0, "timer", 70) // independently observed neutral state
	read(1, "timer", 0)  // same key does not alias a different owner
	for _, expiry := range []int{40, 10, 9, -1} {
		h.replaceMod(replayMod{owner: 0, target: -1, key: "timer", expiry: expiry, hitlag: true})
		read(0, "timer", float64(max(0, expiry-10)))
		if h.statusActive(0, "timer") != (expiry == -1 || expiry >= 10) {
			t.Fatal("duration changed the existing active-status semantics")
		}
	}
	if !h.uncertainty["set_hitlag_expiry_approximate"] {
		t.Fatal("missing hitlag evidence was not marked uncertain")
	}
	h.call(ruleRef{kind: "char", index: 0}, "AddStatus", []any{"timer", float64(30), false})
	read(0, "timer", 30) // refresh replaces expiry, not adds to it
	h.frame = 20
	read(0, "timer", 20)
	h.call(ruleRef{kind: "char", index: 0}, "DeleteStatus", []any{"timer"})
	read(0, "timer", 0) // deletion cannot resurrect neutral expiry80
	h.stateComplete = false
	read(0, "timer", 0) // an explicit deletion is still evidence
	_, err := ruleTry(func() any { return h.statusDuration(2, "unknown") })
	if err == nil {
		t.Fatal("unobserved absence became zero duration")
	}
}

// Runs only with a managed bundle of the active engine's actual set source.
func TestRuleActiveCelestialDurationTransfer(t *testing.T) {
	c := activeRuleCatalog(t)
	num := func(x float64) contracts.EventValue { return contracts.EventValue{Kind: "number", Number: x} }
	for _, test := range []struct {
		name        string
		skill       bool
		swap, query int
		want        float64
	}{
		{"no skill", false, 100, 110, 0},
		{"transfer", true, 100, 110, .4},
		{"not refreshed by swap", true, 100, 1250, 0},
		{"expired before swap", true, 1250, 1260, 0},
	} {
		t.Run(test.name, func(t *testing.T) {
			n := ruleTestNeutral()
			for i := range n.Context.Characters {
				char := &n.Context.Characters[i]
				char.Facts = map[string]contracts.EventValue{"IsHexerei": {Kind: "bool", Boolean: i < 2}}
				element := "Hydro"
				if i == 1 {
					element = "Electro"
				}
				char.Base.Fields["Element"] = num(ruleTestConstant(t, c, "pkg/core/attributes", element))
				char.Base.Fields["Key"] = contracts.EventValue{Kind: "string", Text: char.Key}
			}
			event := func(name string, frame, active int) contracts.CombatEvent {
				return contracts.CombatEvent{Order: uint64(frame * 10), EndOrder: uint64(frame*10 + 1), Frame: frame, Active: active,
					Event: int(ruleTestConstant(t, c, "pkg/core/event", name))}
			}
			if test.skill {
				n.Ledger.Events = append(n.Ledger.Events, event("OnSkill", 10, 1))
			}
			n.Ledger.Events = append(n.Ledger.Events, event("OnCharacterSwap", test.swap, 0))
			q := RuleQuery{Order: uint64(test.query * 10), Frame: test.query, Active: 0, Owner: 0, Kind: "stat", Mode: "stat", Stat: "hydro%"}
			out := c.ReplayNeutralRules(n, []RuleChoice{{1, "celestialgift", 4}}, []RuleQuery{q})
			if out.Boundary != "" || len(out.Values) != 1 || !out.Values[0].Known || math.Abs(out.Values[0].Value-test.want) > 1e-12 {
				t.Fatalf("%+v values=%+v", out, out.Values)
			}
		})
	}
}

package seteffects

import (
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// This self-contained contract needs no installed engine/source tree. It checks
// the separately frozen heal prerequisite; it does not implement health rules.
func TestTheoryHealPrerequisiteConsumedOperandsAndObservedControl(t *testing.T) {
	checks := []struct {
		name, expression string
		symbolic         bool
		unknown          string
	}{
		{"received", "return args[2].(float64) > 0", true, "neutral heal amount"},
		{"overheal", "return args[3].(float64) == 0", true, "neutral heal amount"},
		{"raw", "return args[4].(float64) > 0", true, "neutral heal amount"},
		{"source", "return args[0].(*info.HealInfo).Src > 0", true, "neutral heal source operand"},
		{"bonus", "return args[0].(*info.HealInfo).Bonus > 0", true, "neutral heal source operand"},
		{"event identity", "return args[0].(*info.HealInfo).Caller == 1 && args[1].(int) == 1", true, ""},
		{"unused amount", "if args[1].(int) != 3 { return true }; return args[4].(float64) > 0", true, ""},
		{"ordinary observed replay", "return args[4].(float64) > 0", false, ""},
	}
	for _, check := range checks {
		t.Run(check.name, func(t *testing.T) {
			vm := testRule(t, `import (
 e "github.com/genshinsim/gcsim/pkg/core/event"
 "github.com/genshinsim/gcsim/pkg/core/info"
)
func Callback() any { _ = e.OnHeal; return func(args ...any) bool { `+check.expression+` } }`, map[string][]byte{
				"pkg/core/event/event.go": []byte("package event; const OnHeal = 7"),
				"pkg/core/info/heal.go":   []byte("package info; type HealInfo struct { Caller int; Src, Bonus float64 }"),
			})
			callback, err := vm.entry("Callback")
			if err != nil {
				t.Fatal(err)
			}
			host := &ruleReplayHost{vm: vm, symbolic: check.symbolic, uncertainty: map[string]bool{}}
			number := func(value float64) contracts.EventValue {
				return contracts.EventValue{Kind: "number", Number: value}
			}
			info := host.wire(contracts.EventValue{Kind: "object", Type: "*" + gcsimImport + "pkg/core/info.HealInfo", Fields: map[string]contracts.EventValue{
				"Caller": number(1), "Src": number(10), "Bonus": number(.15),
			}})
			value, err := ruleTry(func() any {
				return host.invokeEvent(ruleSubscription{vm: vm, fn: callback}, contracts.CombatEvent{Event: 7}, []any{
					info, float64(1), float64(11.5), float64(0), float64(11.5),
				})
			})
			if check.unknown != "" {
				if err == nil || !strings.Contains(err.Error(), check.unknown) {
					t.Fatalf("consumed unbound heal operand accepted: value=%v err=%v", value, err)
				}
			} else if err != nil || value != true {
				t.Fatalf("independent identity/ordinary replay rejected: value=%v err=%v", value, err)
			}
			if !host.uncertainty["set_activation_heal_amount_frozen_to_observed_build"] {
				t.Fatal("observed heal uncertainty provenance lost")
			}
		})
	}
}

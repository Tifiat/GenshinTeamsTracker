package seteffects

// Selected-engine source controls of generic host capabilities. Numeric expected
// values pin today's source behavior, not a consumer mechanics implementation.
import (
	"math"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func ruleResourceFacts() *contracts.EventValue {
	number := func(x float64) contracts.EventValue { return contracts.EventValue{Kind: "number", Number: x} }
	chars := []contracts.EventValue{}
	for range 4 {
		chars = append(chars, contracts.EventValue{Kind: "object", Fields: map[string]contracts.EventValue{"Energy": number(100), "EnergyMax": number(100)}})
	}
	return &contracts.EventValue{Kind: "object", Fields: map[string]contracts.EventValue{
		"Characters": {Kind: "array", Items: chars}, "Shields": {Kind: "array", Items: []contracts.EventValue{}}, "Constructs": {Kind: "array", Items: []contracts.EventValue{}},
		"Statuses": {Kind: "map", Fields: map[string]contracts.EventValue{}}, "Custom": {Kind: "map", Fields: map[string]contracts.EventValue{}}, "IgnoreBurstEnergy": {Kind: "bool", Boolean: true},
		"Position": {Kind: "observation", Type: gcsimImport + "pkg/core/info.Point", Fields: map[string]contracts.EventValue{"X": number(0), "Y": number(0)}},
	}}
}

func TestRuleActiveResourceBonuses(t *testing.T) {
	c := activeRuleCatalog(t)
	event := func(name string, frame int, args ...contracts.EventValue) contracts.CombatEvent {
		return contracts.CombatEvent{Order: uint64(frame * 10), EndOrder: uint64(frame*10 + 1), Frame: frame, Active: 1, Event: int(ruleTestConstant(t, c, "pkg/core/event", name)), Arguments: args}
	}
	num := func(x float64) contracts.EventValue { return contracts.EventValue{Kind: "number", Number: x} }
	shield := func(kind string) contracts.EventValue {
		return contracts.EventValue{Kind: "observation", Type: gcsimImport + "pkg/core/player/shield.Shield", Fields: map[string]contracts.EventValue{"Type": num(ruleTestConstant(t, c, "pkg/core/player/shield", kind)), "Expiry": num(900), "Element": num(ruleTestConstant(t, c, "pkg/core/attributes", "Hydro"))}}
	}
	query := func(kind, stat string, frame int) RuleQuery {
		return RuleQuery{Order: uint64(frame * 10), Frame: frame, Active: 1, Owner: 1, Kind: kind, Stat: stat, Mode: "stat", HitID: 7}
	}
	attack := func() contracts.EventValue {
		i := ruleTestAttack(1, ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagNormal"), ruleTestConstant(t, c, "pkg/core/attributes", "Physical"))
		i.Fields["FlatDmg"] = num(17)
		return contracts.EventValue{Kind: "object", Type: "*" + gcsimImport + "pkg/core/info.AttackEvent", Fields: map[string]contracts.EventValue{"Info": i, "HitID": num(7)}}
	}
	for _, test := range []struct {
		name, key string
		events    []contracts.CombatEvent
		q         RuleQuery
		want      float64
		energy    *float64
	}{
		{"maiden no skill", "maidenbeloved", nil, query("heal_bonus", "heal_bonus", 20), 0, nil},
		{"maiden received", "maidenbeloved", []contracts.CombatEvent{event("OnSkill", 10)}, query("heal_bonus", "heal_bonus", 20), .2, nil},
		{"maiden expired", "maidenbeloved", []contracts.CombatEvent{event("OnSkill", 10)}, query("heal_bonus", "heal_bonus", 700), 0, nil},
		{"whispers no crystal", "nighttimewhispersintheechoingwoods", []contracts.CombatEvent{event("OnSkill", 10)}, query("stat", "geo%", 20), .2, nil},
		{"whispers wrong shield", "nighttimewhispersintheechoingwoods", []contracts.CombatEvent{event("OnSkill", 10), event("OnShielded", 11, shield("IneffaSkill"))}, query("stat", "geo%", 20), .2, nil},
		{"whispers crystal", "nighttimewhispersintheechoingwoods", []contracts.CombatEvent{event("OnSkill", 10), event("OnShielded", 11, shield("Crystallize"))}, query("stat", "geo%", 20), .5, nil},
		{"petra wrong shield", "archaicpetra", []contracts.CombatEvent{event("OnShielded", 11, shield("IneffaSkill"))}, query("stat", "hydro%", 20), 0, nil},
		{"petra crystal", "archaicpetra", []contracts.CombatEvent{event("OnShielded", 11, shield("Crystallize"))}, query("stat", "hydro%", 20), .35, nil},
		{"song no healing", "songofdayspast", nil, query("flat_event", "FlatDmg", 400), 0, nil},
		{"song accumulated healing", "songofdayspast", []contracts.CombatEvent{
			event("OnHeal", 10, contracts.EventValue{Kind: "object", Type: "*" + gcsimImport + "pkg/core/info.HealInfo", Fields: map[string]contracts.EventValue{"Caller": num(1)}}, num(1), num(5000), num(5000), num(10000)),
			event("OnEnemyHit", 390, contracts.EventValue{Kind: "nil"}, attack()),
		}, query("flat_event", "FlatDmg", 400), 800, nil},
	} {
		t.Run(test.name, func(t *testing.T) {
			n := ruleTestNeutral()
			n.World.States[0].Facts = ruleResourceFacts()
			n.Ledger.Events = test.events
			out := c.ReplayNeutralRules(n, []RuleChoice{{1, test.key, 4}}, []RuleQuery{test.q})
			if out.Boundary != "" || !out.Values[0].Known || math.Abs(out.Values[0].Value-test.want) > 1e-9 {
				t.Fatalf("%+v values=%+v", out, out.Values)
			}
		})
	}
	for _, energy := range []float64{0, 100} {
		n := ruleTestNeutral()
		n.World.States[0].Facts = ruleResourceFacts()
		n.World.States[0].Facts.Fields["Characters"].Items[1].Fields["Energy"] = num(energy)
		n.Ledger.Events = []contracts.CombatEvent{event("OnSkill", 10)}
		q := query("attack", "dmg%", 20)
		q.Attack = attack()
		out := c.ReplayNeutralRules(n, []RuleChoice{{1, "shimenawasreminiscence", 4}}, []RuleQuery{q})
		want := 0.0
		if energy >= 15 {
			want = .5
		}
		if out.Boundary != "" || !out.Values[0].Known || math.Abs(out.Values[0].Value-want) > 1e-9 {
			t.Fatalf("energy=%v %+v values=%+v", energy, out, out.Values)
		}
	}
	for _, distance := range []float64{10, 30} {
		n := ruleTestNeutral()
		n.World.States[0].Facts = ruleResourceFacts()
		position := n.World.States[0].Facts.Fields["Position"]
		position.Fields = map[string]contracts.EventValue{"X": num(distance), "Y": num(0)}
		n.World.States[0].Facts.Fields["Constructs"] = contracts.EventValue{Kind: "array", Items: []contracts.EventValue{{Kind: "observation", Type: gcsimImport + "pkg/core/construct.Construct", Fields: map[string]contracts.EventValue{
			"Type": num(ruleTestConstant(t, c, "pkg/core/construct", "GeoConstructLunarCrystallize")), "Pos": position, "Expiry": num(2000),
		}}}}
		// Current source starts the ticker before installing the first skill mod;
		// a second skill during the active window exercises its nearby query.
		n.Ledger.Events = []contracts.CombatEvent{event("OnSkill", 10), event("OnSkill", 100)}
		out := c.ReplayNeutralRules(n, []RuleChoice{{1, "nighttimewhispersintheechoingwoods", 4}}, []RuleQuery{query("stat", "geo%", 110)})
		want := .2
		if distance < 20 {
			want = .5
		}
		if out.Boundary != "" || !out.Values[0].Known || math.Abs(out.Values[0].Value-want) > 1e-9 {
			t.Fatalf("distance=%v %+v values=%+v", distance, out, out.Values)
		}
	}
}

func TestRuleResourcesRequireObservedFacts(t *testing.T) {
	h := &ruleReplayHost{}
	_, err := ruleTry(func() any {
		value, _ := h.resourceCall(ruleRef{kind: "shields"}, "Get", []any{float64(0)})
		return value
	})
	if err == nil {
		t.Fatal("missing shield observation became absence")
	}
}

func TestRuleActiveMarechausseeHealingBranch(t *testing.T) {
	c := activeRuleCatalog(t)
	num := func(x float64) contracts.EventValue { return contracts.EventValue{Kind: "number", Number: x} }
	for _, test := range []struct {
		name                       string
		active, healed, count      int
		amount, overheal, expected float64
	}{
		{"actual heal", 1, 1, 1, 5000, 0, .12},
		{"only overheal", 1, 1, 1, 5000, 5000, 0},
		{"zero heal", 1, 1, 1, 0, 0, 0},
		{"different target", 1, 2, 1, 5000, 0, 0},
		{"off field", 2, 1, 1, 5000, 0, 0},
		{"two heals", 1, 1, 2, 5000, 0, .24},
		{"capped stacks", 1, 1, 4, 5000, 0, .36},
	} {
		t.Run(test.name, func(t *testing.T) {
			n := ruleTestNeutral()
			n.World.States[0].Facts = ruleResourceFacts()
			n.Hitlag = &contracts.NeutralHitlagLedger{Complete: true}
			for i := range test.count {
				frame := 10 + i
				n.Ledger.Events = append(n.Ledger.Events, contracts.CombatEvent{
					Order: uint64(frame * 10), EndOrder: uint64(frame*10 + 1), Frame: frame, Active: test.active,
					Event:     int(ruleTestConstant(t, c, "pkg/core/event", "OnHeal")),
					Arguments: []contracts.EventValue{{Kind: "nil"}, num(float64(test.healed)), num(test.amount), num(test.overheal), num(test.amount)},
				})
			}
			out := c.CompileNeutralRules(n, []RuleChoice{{1, "marechausseehunter", 4}}, []RuleQuery{
				{Order: 200, Frame: 20, Active: test.active, Owner: 1, Kind: "stat", Stat: "cr", Mode: "stat"},
				{Order: 4000, Frame: 400, Active: test.active, Owner: 1, Kind: "stat", Stat: "cr", Mode: "stat"},
			})
			if out.Boundary != "" || !out.Values[0].Known || math.Abs(out.Values[0].Value-test.expected) > 1e-12 || !out.Values[1].Known || out.Values[1].Value != 0 {
				t.Fatalf("%+v values=%+v", out, out.Values)
			}
		})
	}
}

func TestRuleActiveSongRejectsMissingHitIdentity(t *testing.T) {
	c := activeRuleCatalog(t)
	num := func(x float64) contracts.EventValue { return contracts.EventValue{Kind: "number", Number: x} }
	for _, kind := range []string{"zero", "missing", "missing-port"} {
		t.Run(kind, func(t *testing.T) {
			n := ruleTestNeutral()
			n.World.States[0].Facts = ruleResourceFacts()
			info := ruleTestAttack(1, ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagNormal"), ruleTestConstant(t, c, "pkg/core/attributes", "Physical"))
			info.Fields["FlatDmg"] = num(17)
			attack := contracts.EventValue{Kind: "object", Type: "*" + gcsimImport + "pkg/core/info.AttackEvent", Fields: map[string]contracts.EventValue{"Info": info}}
			if kind != "missing" {
				attack.Fields["HitID"] = num(0)
				if kind == "missing-port" {
					attack.Fields["HitID"] = num(8)
				}
			}
			n.Ledger.Events = []contracts.CombatEvent{
				{Order: 100, EndOrder: 101, Frame: 10, Active: 1, Event: int(ruleTestConstant(t, c, "pkg/core/event", "OnHeal")),
					Arguments: []contracts.EventValue{{Kind: "object", Type: "*" + gcsimImport + "pkg/core/info.HealInfo", Fields: map[string]contracts.EventValue{"Caller": num(1)}}, num(1), num(5000), num(5000), num(10000)}},
				{Order: 3900, EndOrder: 3901, Frame: 390, Active: 1, Event: int(ruleTestConstant(t, c, "pkg/core/event", "OnEnemyHit")),
					Arguments: []contracts.EventValue{{Kind: "nil"}, attack}},
			}
			out := c.CompileNeutralRules(n, []RuleChoice{{1, "songofdayspast", 4}}, []RuleQuery{{Order: 4000, Frame: 400, Active: 1, Owner: 1, Kind: "flat_event", Stat: "FlatDmg", HitID: 7}})
			want := "event flat damage has no observed hit identity"
			if kind == "missing-port" {
				want = "event flat damage has no retained formula port"
			}
			if !strings.Contains(out.Boundary, want) {
				t.Fatalf("missing binding was not diagnosed: %+v", out)
			}
		})
	}
}

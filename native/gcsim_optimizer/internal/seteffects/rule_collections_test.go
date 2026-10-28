package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"math"
	"testing"
)

func TestRuleMapRegistrationRequiresOrderIndependence(t *testing.T) {
	for _, test := range []struct {
		body  string
		valid bool
	}{
		{`for k,n := range map[int]int{1:3,2:7} {c.Events.Subscribe(k,func(){_ = n},"test")}`, true},
		{`for _,n := range map[int]int{1:3,2:7} {c.Events.Subscribe(1,func(){_ = n},"test")}`, false},
		{`for k := range map[int]int{1:3,2:7} {c.Events.Subscribe(k,func(){},"test");break}`, false},
		{`n:=0; for k := range map[int]int{1:3,2:7} {n=k};_ = n`, false},
	} {
		v := testRule(t, "func Start(c any){"+test.body+"}", nil)
		h := &ruleReplayHost{vm: v, subs: map[int][]ruleSubscription{}, uncertainty: map[string]bool{}}
		v.host = h
		_, err := v.entry("Start", ruleRef{kind: "core"})
		if (err == nil) != test.valid {
			t.Fatal(test, err)
		}
	}
}

func TestRuleFieldScratchClearDoesNotLeakOrAdmitAliases(t *testing.T) {
	for _, body := range []string{
		`clear(s.buff);s.buff[1]=9;return s.buff`,
		`alias:=s.buff;clear(alias);return s.buff`,
		`clear:=func(x []float64){x[0]=7};clear(s.buff);return s.buff`,
	} {
		v := testRule(t, `type Set struct{buff []float64}
func Start() any {s:=Set{buff:[]float64{5,6}};return func() []float64 {`+body+`}}`, nil)
		fn, err := v.entry("Start")
		if err != nil {
			t.Fatal(err)
		}
		value, err := ruleTry(func() any { return v.invokeAmount(fn.(*ruleFunction), nil) })
		if body != `clear(s.buff);s.buff[1]=9;return s.buff` {
			if err == nil {
				t.Fatal("scratch alias admitted", body, value)
			}
			continue
		}
		if err != nil || ruleArray(value)[0] != float64(0) || ruleArray(value)[1] != float64(9) {
			t.Fatal(value, err)
		}
		saved := v.amountScratch(fn.(*ruleFunction))
		if saved.values[0] != float64(5) || saved.values[1] != float64(6) {
			t.Fatal("scratch not restored", saved)
		}
	}
}

func TestRuleSourceEnumFormattingKeepsSourceKey(t *testing.T) {
	v := testRule(t, `type Kind int
const (First Kind=iota;Second)
func(k Kind)String()string{return []string{"first","second"}[k]}
func Start() any{return Second}`, nil)
	value, err := v.entry("Start")
	if err != nil {
		t.Fatal(err)
	}
	if got := v.formatRule("prefix-%v", []any{value}); got != "prefix-second" {
		t.Fatal(got)
	}
}

func TestRuleActiveSourceScrollPartialAndFullCoverage(t *testing.T) {
	c := activeRuleCatalog(t)
	electro := ruleTestConstant(t, c, "pkg/core/attributes", "Electro")
	hydro := ruleTestConstant(t, c, "pkg/core/attributes", "Hydro")
	trigger := int(ruleTestConstant(t, c, "pkg/core/event", "OnElectroCharged"))
	targetType := ruleTestConstant(t, c, "pkg/core/info", "TargettableEnemy")
	// Native target types are observer facts; no source mechanics are supplied
	// by this test. Only the event and Nightsoul status are varied.
	for _, nightsoul := range []bool{false, true} {
		n := ruleTestNeutral()
		n.Context.Characters[2].Base.Fields["Element"] = contracts.EventValue{Kind: "number", Type: gcsimImport + "pkg/core/attributes.Element", Number: electro}
		n.World.States[0].Targets = []contracts.EventValue{{Kind: "target", Type: "*" + gcsimImport + "pkg/enemy.Enemy", Fields: map[string]contracts.EventValue{
			"Key": {Kind: "number", Number: 9}, "Type": {Kind: "number", Number: targetType}, "Interfaces": {Kind: "map", Fields: map[string]contracts.EventValue{gcsimImport + "pkg/core/info.Target": {Kind: "bool", Boolean: true}}},
		}}}
		if nightsoul {
			var status string
			for _, s := range c.Sets {
				if s.rule != nil {
					v := newRuleVM(s.rule, nil, 1000)
					m := v.program.modules[gcsimImport+"internal/template/nightsoul"]
					status = ruleString(v.lookup(m.envs[m.files[0]], "NightsoulBlessingStatus"))
					break
				}
			}
			n.World.States[0].Modifiers = append(n.World.States[0].Modifiers, contracts.NeutralModifierIdentity{Owner: 2, Key: status, Expiry: 1000})
		}
		n.Ledger.Events = []contracts.CombatEvent{ruleTestEvent(trigger, 2, 0, hydro, 1)}
		queries := []RuleQuery{}
		for _, stat := range []string{"electro%", "hydro%", "pyro%"} {
			queries = append(queries, RuleQuery{Order: 20, Frame: 11, Active: 1, Owner: 0, Target: 9, Kind: "stat", Mode: "stat", Stat: stat})
		}
		result := c.CompileNeutralRules(n, []RuleChoice{{2, "scrolloftheheroofcindercity", 4}}, queries)
		if result.Boundary != "" {
			t.Fatal(nightsoul, result.Boundary)
		}
		for i, value := range result.Values {
			want := .12
			if nightsoul {
				want = .4
			}
			if i == 2 {
				want = 0
			}
			if !value.Known || math.Abs(value.Value-want) > 1e-12 {
				t.Fatal(nightsoul, i, value, want)
			}
		}
	}
}

func TestRuleActiveSourceScrollBurgeonHyperbloomEventGadgetWithoutWorldTarget(t *testing.T) {
	c := activeRuleCatalog(t)
	dendro := ruleTestConstant(t, c, "pkg/core/attributes", "Dendro")
	hyperbloom := int(ruleTestConstant(t, c, "pkg/core/event", "OnHyperbloom"))
	burgeon := int(ruleTestConstant(t, c, "pkg/core/event", "OnBurgeon"))
	enemyType := ruleTestConstant(t, c, "pkg/core/info", "TargettableEnemy")
	gadgetType := ruleTestConstant(t, c, "pkg/core/info", "TargettableGadget")
	tests := []struct {
		name       string
		event      int
		targetType float64
		actor      int
		bonusStats []string
	}{
		{"hyperbloom gadget owner", hyperbloom, gadgetType, 2, []string{"dendro%", "electro%"}},
		{"hyperbloom enemy target", hyperbloom, enemyType, 2, nil},
		{"hyperbloom wrong owner", hyperbloom, gadgetType, 1, nil},
		{"burgeon gadget owner", burgeon, gadgetType, 2, []string{"dendro%", "pyro%"}},
		{"burgeon enemy target", burgeon, enemyType, 2, nil},
		{"burgeon wrong owner", burgeon, gadgetType, 1, nil},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			n := ruleTestNeutral()
			n.Context.Characters[2].Base.Fields["Element"] = contracts.EventValue{Kind: "number", Type: gcsimImport + "pkg/core/attributes.Element", Number: dendro}
			event := ruleTestEvent(test.event, test.actor, 0, 0, 1)
			event.Arguments[0] = contracts.EventValue{Kind: "target", Type: "*" + gcsimImport + "pkg/enemy.Enemy", Fields: map[string]contracts.EventValue{
				"Key": {Kind: "number", Number: 9}, "Type": {Kind: "number", Number: test.targetType},
			}}
			n.Ledger.Events = []contracts.CombatEvent{event}
			stats := []string{"dendro%", "electro%", "pyro%"}
			queries := make([]RuleQuery, 0, len(stats))
			for _, stat := range stats {
				queries = append(queries, RuleQuery{Order: 20, Frame: 11, Active: 1, Owner: 0, Target: 9, Kind: "stat", Mode: "stat", Stat: stat})
			}
			result := c.CompileNeutralRules(n, []RuleChoice{{2, "scrolloftheheroofcindercity", 4}}, queries)
			if result.Boundary != "" {
				t.Fatal(result.Boundary)
			}
			for i, stat := range stats {
				want := 0.0
				for _, bonus := range test.bonusStats {
					if stat == bonus {
						want = .12
					}
				}
				if len(n.World.States[0].Targets) != 0 {
					t.Fatal("test unexpectedly populated the world target snapshot")
				}
				if !result.Values[i].Known || math.Abs(result.Values[i].Value-want) > 1e-12 {
					t.Fatalf("%s = %#v, want %.2f", stat, result.Values[i], want)
				}
			}
		})
	}
}

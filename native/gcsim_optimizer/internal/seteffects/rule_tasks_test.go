package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"strings"
	"testing"
)

func TestRuleScheduleTailCannotHideNewOutput(t *testing.T) {
	for _, delayedEvent := range []bool{false, true} {
		registration := `c.Tasks.Add(func(){c.QueueAttack(1)},50)`
		if delayedEvent {
			registration = `c.Events.Subscribe(99,func(args ...any){c.Tasks.Add(func(){c.QueueAttack(1)},10)},"tail")`
		}
		vm := testRule(t, `type Set struct{}
func(s *Set)Init()error{return nil}
func NewSet(c any,char any,count int,params map[string]int)(*Set,error){`+registration+`;return &Set{},nil}`, map[string][]byte{"pkg/core/attributes/stats.go": []byte("package attributes")})
		catalog := &SourceCatalog{Sets: []DiscoveredSet{{Key: "tail", rule: vm.program}}}
		for _, horizon := range []int{45, 60} {
			n := ruleTestNeutral()
			n.Context.DurationFrames = horizon
			if delayedEvent {
				n.Ledger.Events = []contracts.CombatEvent{{Order: 30, EndOrder: 31, Frame: 40, Active: 1, Event: 99, Arguments: []contracts.EventValue{}}}
			}
			r := catalog.CompileNeutralRules(n, []RuleChoice{{0, "tail", 4}}, []RuleQuery{{Order: 20, Frame: 2, Owner: 0, Active: 1, Kind: "stat", Mode: "stat", Stat: "em"}})
			if horizon == 45 && r.Boundary != "" {
				t.Fatal("task beyond horizon executed", delayedEvent, r)
			}
			if horizon == 60 && !strings.Contains(r.Boundary, "QueueAttack") {
				t.Fatal("tail output silently disappeared", delayedEvent, r)
			}
		}
	}
}

func TestRuleActivatedSpeedCannotBecomeZeroDamageBonus(t *testing.T) {
	c := activeRuleCatalog(t)
	event := int(ruleTestConstant(t, c, "pkg/core/event", "OnEnemyDamage"))
	extra := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagExtra")
	n := ruleTestNeutral()
	q := RuleQuery{Order: 20, Frame: 11, Owner: 0, Active: 1, Kind: "stat", Mode: "stat", Stat: "atk%"}
	choices := []RuleChoice{{0, "desertpavilionchronicle", 4}}
	if r := c.CompileNeutralRules(n, choices, []RuleQuery{q}); r.Boundary != "" || !r.Values[0].Known {
		t.Fatal("inactive speed treated as active", r)
	}
	n.Ledger.Events = []contracts.CombatEvent{ruleTestEvent(event, 0, extra, 0, 1)}
	if r := c.CompileNeutralRules(n, choices, []RuleQuery{q}); !strings.Contains(r.Boundary, "schedule_change:") {
		t.Fatal("active speed vanished from schedule", r)
	}
}

func TestRuleTasksRunOnlyDueSourceCallbacksAndKeepImmediateCharTasks(t *testing.T) {
	v := testRule(t, `func Start(c any, char any) any {
 n:=0
 c.Tasks.Add(func(){ n+=1; c.Tasks.Add(func(){n+=10}, 2) }, 3)
 char.QueueCharTask(func(){ n+=100 }, 0)
 return func() int {return n}
}`, nil)
	h := &ruleReplayHost{vm: v, uncertainty: map[string]bool{}, context: ruleTestNeutral().Context}
	v.host = h
	result, err := v.entry("Start", ruleRef{kind: "core"}, ruleRef{kind: "char", index: 1})
	if err != nil {
		t.Fatal(err)
	}
	for _, point := range []struct {
		frame int
		want  float64
	}{{3, 100}, {4, 101}, {6, 111}} {
		if err := h.tasksBefore(point.frame, nil); err != nil {
			t.Fatal(err)
		}
		x, err := ruleTry(func() any { return v.invoke(result, nil) })
		if err != nil || x != point.want {
			t.Fatal(point, x, err)
		}
	}
	if !h.uncertainty["counterfactual_task_phase_observed_schedule"] {
		t.Fatal("task phase falsely exact")
	}
}

func TestRuleTaskThatCreatesCombatOutputCannotDisappear(t *testing.T) {
	v := testRule(t, `func Start(c any) {c.Tasks.Add(func(){c.QueueAttack(1)},1)}`, nil)
	h := &ruleReplayHost{vm: v, uncertainty: map[string]bool{}}
	v.host = h
	if _, err := v.entry("Start", ruleRef{kind: "core"}); err != nil {
		t.Fatal(err)
	}
	if err := h.tasksBefore(2, nil); err == nil || !strings.Contains(err.Error(), "QueueAttack") {
		t.Fatal("combat task became zero", err)
	}
}

func TestRuleQueuedAttackProducesScheduleChangeBoundary(t *testing.T) {
	vm := testRule(t, `type Set struct{}
func (s *Set) Init() error { return nil }
func NewSet(c any, char any, count int, params map[string]int) (*Set, error) {
 c.QueueAttack(1)
 return &Set{}, nil
}`, map[string][]byte{"pkg/core/attributes/stats.go": []byte("package attributes")})
	catalog := &SourceCatalog{Sets: []DiscoveredSet{{Key: "queued", rule: vm.program}}}
	result := catalog.CompileNeutralRules(ruleTestNeutral(), []RuleChoice{{Owner: 0, Key: "queued", Pieces: 4}}, []RuleQuery{{Order: 20, Frame: 10, Owner: 0, Active: 0, Kind: "stat", Mode: "stat", Stat: "atk%"}})
	if !strings.Contains(result.Boundary, "schedule_change:") || !strings.Contains(result.Boundary, "QueueAttack") {
		t.Fatalf("queued attack did not request an independent schedule: %+v", result)
	}
}

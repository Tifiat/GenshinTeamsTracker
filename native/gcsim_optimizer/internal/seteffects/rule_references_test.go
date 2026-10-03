package seteffects

import (
	"math"
	"strings"
	"testing"
)

func TestRuleScalarPointerIdentityAndMutation(t *testing.T) {
	v := testRule(t, `func cell(n int)*int{return &n}
func Start()int{a:=cell(4);b:=cell(4);if a==b{return -1};x:=2;p:=&x;x=3;if p!=&x{return -2};*p+=4;return *a+*b+x}`, nil)
	value, err := v.entry("Start")
	if err != nil || value != float64(15) {
		t.Fatal(value, err)
	}
}

func TestRuleAmountHelpersOwnOnlyTheirCallLocals(t *testing.T) {
	for _, test := range []struct {
		helper string
		valid  bool
	}{
		{`n:=0;for _,v:=range []int{1,2,3}{n+=v};return n`, true},
		{`n:=0;p:=&n;*p=6;return n`, true},
		{`saved++;return saved`, false},
		{`*p=6;return *p`, false},
	} {
		v := testRule(t, `func Start()any{saved:=2;p:=&saved;helper:=func()int{`+test.helper+`};return func()float64{return float64(helper())}}`, nil)
		fn, err := v.entry("Start")
		if err != nil {
			t.Fatal(err)
		}
		value, err := ruleTry(func() any { return v.invokeAmount(fn.(*ruleFunction), nil) })
		if (err == nil) != test.valid || (err == nil && value != float64(6)) {
			t.Fatal(test, value, err)
		}
	}
}

func TestRuleExternalFrameAddressIsLiveAndReadOnly(t *testing.T) {
	v := testRule(t, `func Start(c any)any {frame:=&c.F;return func()int{return *frame}}
func Bad(c any){frame:=&c.F;*frame=5}`, nil)
	h := &ruleReplayHost{vm: v, frame: 3}
	v.host = h
	fn, err := v.entry("Start", ruleRef{kind: "core"})
	if err != nil {
		t.Fatal(err)
	}
	h.frame = 19
	value, err := ruleTry(func() any { return v.invoke(fn, nil) })
	if err != nil || value != float64(19) {
		t.Fatal(value, err)
	}
	if _, err = v.entry("Bad", ruleRef{kind: "core"}); err == nil || !strings.Contains(err.Error(), "external") {
		t.Fatal(err)
	}
}

func TestRuleCommaOKMissingMapEntryKeepsZeroAndPresence(t *testing.T) {
	v := testRule(t, `type S struct{n int};func Start()int{m:=map[int]S{1:{n:0}};a,ok:=m[1];if !ok{return -1};b,ok:=m[2];if ok{return -2};return a.n+b.n}`, nil)
	value, err := v.entry("Start")
	if err != nil || value != float64(0) {
		t.Fatal(value, err)
	}
}

// Coefficients are expectations from this bound engine source. The production
// evaluator executes longnightsoath.go + core/stacks/refresh.go, not this table.
func TestRuleActiveSourceStackRefreshKeepsPointerIdentity(t *testing.T) {
	c := activeRuleCatalog(t)
	event := int(ruleTestConstant(t, c, "pkg/core/event", "OnEnemyDamage"))
	plunge := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagPlunge")
	skill := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagElementalArt")
	normal := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagNormal")
	for _, pieces := range []int{2, 4} {
		n := ruleTestNeutral()
		for i, point := range []struct {
			frame int
			tag   float64
		}{{10, skill}, {20, normal}, {90, skill}, {170, skill}} {
			x := ruleTestEvent(event, 0, point.tag, 0, 0)
			x.Frame = point.frame
			x.Order = uint64(10 + i*20)
			x.EndOrder = x.Order + 1
			n.Ledger.Events = append(n.Ledger.Events, x)
		}
		queries := []RuleQuery{}
		for i, frame := range []int{11, 21, 91, 171, 400, 470, 540} {
			q := RuleQuery{Order: uint64(20 + i*20), Frame: frame, Owner: 0, Active: 0, Kind: "attack", Stat: "dmg%", Attack: ruleTestEvent(event, 0, plunge, 0, 0).Arguments[1]}
			queries = append(queries, q)
		}
		r := c.CompileNeutralRules(n, []RuleChoice{{0, "longnightsoath", pieces}}, queries)
		if r.Boundary != "" {
			t.Fatal(pieces, r.Boundary)
		}
		for i, stacks := range []int{2, 2, 4, 5, 4, 2, 0} {
			want := .25
			if pieces == 4 {
				want += .15 * float64(stacks)
			}
			if !r.Values[i].Known || math.Abs(r.Values[i].Value-want) > 1e-12 {
				t.Fatal(pieces, i, r.Values[i], want)
			}
		}
	}
}

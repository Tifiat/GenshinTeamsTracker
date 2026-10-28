package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"math"
	"strings"
	"testing"
)

func TestRuleMathAbsRetainsVariableAndNativeSemantics(t *testing.T) {
	v := testRule(t, `import m "math"; func Start(x float64) float64 { return m.Abs(x) }`, nil)
	for _, x := range []float64{-12, -1e-12, math.Copysign(0, -1), 0, 1e-12, 12} {
		out, err := v.entry("Start", x)
		if err != nil || out != math.Abs(x) || math.Signbit(ruleNumber(out)) {
			t.Fatalf("x=%v got=%v err=%v", x, out, err)
		}
	}
	read := RuleStatRead{Owner: 2, Stat: "hp", Mode: "stat", Order: 9}
	out, err := v.entry("Start", &RuleScalar{Operation: "neutral_stat", Read: &read})
	if err != nil {
		t.Fatal(err)
	}
	expr, ok := out.(*RuleScalar)
	if !ok {
		t.Fatal("absolute value froze a variable", out)
	}
	if _, err := expr.Evaluate(nil); err == nil {
		t.Fatal("missing operand became a value")
	}
	for _, x := range []float64{-12, -1e-12, math.Copysign(0, -1), 0, 1e-12, 12} {
		got, err := expr.Evaluate(func(r RuleStatRead) (float64, error) {
			if r != read {
				t.Fatal("input ownership changed", r)
			}
			return x, nil
		})
		if err != nil || got != math.Abs(x) || math.Signbit(got) {
			t.Fatal(x, got, err)
		}
	}
	for _, source := range []string{
		`import "math"; func Start() float64 { return math.Abs() }`,
		`import "math"; func Start() float64 { return math.Abs(1.0, 2.0) }`,
		`import "math"; func Start() float64 { return math.Abs("missing") }`,
		`import "math"; func Start() float64 { return math.Sin(1.0) }`,
	} {
		if _, err := testRule(t, source, nil).entry("Start"); err == nil {
			t.Fatal("unsupported call accepted", source)
		}
	}
}

func TestRuleScalarCapsRetainInputAndRejectSideEffects(t *testing.T) {
	for _, body := range []string{
		"amount:=x*.25;if amount>.75{amount=.75};return amount",
		"amount:=.75;if x*.25<=.75{amount=x*.25};return amount",
		"return min(.75,max(0.0,x*.25))",
	} {
		v := testRule(t, "func Start(x float64) float64 {"+body+"}", nil)
		x, err := v.entry("Start", &RuleScalar{Operation: "neutral_stat", Read: &RuleStatRead{Owner: 2, Stat: "er", Mode: "non_extra_stat", Order: 9}})
		if err != nil {
			t.Fatal(err)
		}
		expr, ok := x.(*RuleScalar)
		if !ok {
			t.Fatal("scalar was frozen", x)
		}
		if _, err = expr.Evaluate(nil); err == nil {
			t.Fatal("unbound input became zero")
		}
		for _, er := range []float64{1, 2, 3, 4} {
			got, err := expr.Evaluate(func(r RuleStatRead) (float64, error) {
				if r.Owner != 2 || r.Stat != "er" || r.Mode != "non_extra_stat" || r.Order != 9 {
					t.Fatal(r)
				}
				return er, nil
			})
			if err != nil || math.Abs(got-math.Min(.75, er*.25)) > 1e-12 {
				t.Fatal(got, err)
			}
		}
	}
	for _, body := range []string{
		"if x>1 { change() };return x",
		"if x>1 { return 0 };return x",
		"out:=[]float64{0};if x>1 {out[0]=1};return out[0]",
		"min:=func(x float64)float64{return x};out:=x;if x>1 {out=min(x)};return out",
	} {
		v := testRule(t, "func Start(x float64) float64 {"+body+"}", nil)
		if _, err := v.entry("Start", &RuleScalar{Operation: "neutral_stat", Read: &RuleStatRead{Stat: "er"}}); err == nil {
			t.Fatal("effectful symbolic branch accepted", body)
		}
	}
}

func TestRuleAmountScratchRestoredAndStatefulWritesRejected(t *testing.T) {
	for _, write := range []string{"m[0]=x", "m[0]+=x", "m[0]=m[0]+x"} {
		v := testRule(t, `func Start() any { m:=[]float64{7};return func(x float64) []float64 { `+write+`;return m } }`, nil)
		x, err := v.entry("Start")
		if err != nil {
			t.Fatal(err)
		}
		fn := x.(*ruleFunction)
		for _, n := range []float64{2, 4} {
			out, err := ruleTry(func() any { return v.invokeAmount(fn, []any{n}) })
			if write != "m[0]=x" {
				if err == nil {
					t.Fatal("stateful Amount accepted")
				}
				continue
			}
			if err != nil || ruleArray(out)[0] != n {
				t.Fatal(out, err)
			}
			if ruleArray(v.lookup(fn.env, "m"))[0] != float64(7) {
				t.Fatal("cached output not restored")
			}
		}
	}
}

func TestRuleAmountCompoundRequiresCurrentInvocationWrite(t *testing.T) {
	for _, body := range []string{"m[0]=x;m[0]+=2", "if x>0 {m[0]=x};m[0]+=2"} {
		v := testRule(t, `func Start() any {m:=[]float64{99};return func(x float64) []float64 {`+body+`;return m}}`, nil)
		x, err := v.entry("Start")
		if err != nil {
			t.Fatal(err)
		}
		fn := x.(*ruleFunction)
		out, err := ruleTry(func() any { return v.invokeAmount(fn, []any{3.0}) })
		if err != nil || ruleArray(out)[0] != 5.0 {
			t.Fatal(out, err)
		}
		if ruleArray(v.lookup(fn.env, "m"))[0] != 99.0 {
			t.Fatal("scratch escaped")
		}
		_, err = ruleTry(func() any { return v.invokeAmount(fn, []any{-1.0}) })
		if strings.HasPrefix(body, "if") && err == nil {
			t.Fatal("read before path-local write accepted")
		}
	}
}

func TestRuleActiveSourceTimedAndWeaponModifiers(t *testing.T) {
	c := activeRuleCatalog(t)
	skill := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagElementalArt")
	swap := int(ruleTestConstant(t, c, "pkg/core/event", "OnCharacterSwap"))
	n := ruleTestNeutral()
	n.Ledger.Events = []contracts.CombatEvent{{Order: 10, EndOrder: 11, Frame: 10, Active: 2, Event: swap, Arguments: []contracts.EventValue{{Kind: "number", Number: 1}, {Kind: "number", Number: 2}}}}
	n.World.States = append(n.World.States, contracts.NeutralWorldState{Order: 10, Frame: 10, Active: 2, Modifiers: []contracts.NeutralModifierIdentity{}})
	q := RuleQuery{Order: 20, Frame: 11, Active: 2, Owner: 2, Target: 9, Kind: "attack", Mode: "stat", Stat: "dmg%", Attack: contracts.EventValue{Kind: "object", Fields: map[string]contracts.EventValue{"Info": ruleTestAttack(2, skill, 0)}}}
	after := q
	after.Order, after.Frame = 30, 131
	r := c.CompileNeutralRules(n, []RuleChoice{{2, "goldentroupe", 4}}, []RuleQuery{q, after})
	if r.Boundary != "" || !r.Values[0].Known || !r.Values[1].Known || math.Abs(r.Values[0].Value-.7) > 1e-12 || math.Abs(r.Values[1].Value-.45) > 1e-12 {
		t.Fatal("timed Troupe", r)
	}
	if len(r.Uncertainty) == 0 {
		t.Fatal("task phase falsely exact")
	}
	n = ruleTestNeutral()
	queries := []RuleQuery{}
	for i, frame := range []int{181, 361, 541, 721} {
		queries = append(queries, RuleQuery{Order: uint64(20 + i), Frame: frame, Active: 1, Owner: 2, Kind: "stat", Mode: "stat", Stat: "def%"})
	}
	r = c.CompileNeutralRules(n, []RuleChoice{{2, "huskofopulentdreams", 4}}, queries)
	if r.Boundary != "" {
		t.Fatal("timed Husk", r)
	}
	for i, value := range r.Values {
		if !value.Known || math.Abs(value.Value-(.36+.06*float64(i))) > 1e-12 {
			t.Fatal("Husk stack", i, r)
		}
	}
	// Imported weapon enums must not degrade into an unknown native selector.
	n = ruleTestNeutral()
	n.Context.Characters[2].Facts = map[string]contracts.EventValue{"Weapon": {Kind: "object", Fields: map[string]contracts.EventValue{"Class": {Kind: "number", Type: gcsimImport + "pkg/core/info.WeaponClass", Number: ruleTestConstant(t, c, "pkg/core/info", "WeaponClassSpear")}}}}
	normal := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagNormal")
	q.Attack.Fields["Info"] = ruleTestAttack(2, normal, 0)
	r = c.CompileNeutralRules(n, []RuleChoice{{2, "gladiatorsfinale", 4}}, []RuleQuery{q})
	if r.Boundary != "" || !r.Values[0].Known || math.Abs(r.Values[0].Value-.35) > 1e-12 {
		t.Fatal("weapon enum", r)
	}
}

func TestRuleAmountMemoKeepsQueryIdentityAndLifecycle(t *testing.T) {
	v := testRule(t, `func Start() any {return func() []float64 {return []float64{2,3}}}`, nil)
	x, err := v.entry("Start")
	if err != nil {
		t.Fatal(err)
	}
	m := replayMod{vm: v, object: &ruleObject{fields: map[string]any{"Amount": x}}}
	h := &ruleReplayHost{order: 10}
	q := RuleQuery{Mode: "snapshot", Target: 9}
	a, err := h.amount(m, q, nil)
	if err != nil || ruleArray(a)[0] != 2.0 {
		t.Fatal(a, err)
	}
	remaining := v.remaining
	if _, err = h.amount(m, q, nil); err != nil || v.remaining != remaining {
		t.Fatal("same query re-evaluated", err)
	}
	h.order++
	if _, err = h.amount(m, q, nil); err != nil || v.remaining >= remaining {
		t.Fatal("different query shared value", err)
	}
	remaining = v.remaining
	h.lifecycle++
	if _, err = h.amount(m, q, nil); err != nil || v.remaining >= remaining {
		t.Fatal("changed closure state shared value", err)
	}
}

func TestRuleActiveSourceStatDependentEmblem(t *testing.T) {
	c := activeRuleCatalog(t)
	burst := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagElementalBurst")
	skill := ruleTestConstant(t, c, "pkg/core/attacks", "AttackTagElementalArt")
	q := RuleQuery{Order: 40, Frame: 20, Owner: 2, Active: 2, Target: 9, Kind: "attack", Mode: "stat", Stat: "dmg%"}
	q.Attack = contracts.EventValue{Kind: "object", Type: "*" + gcsimImport + "pkg/core/info.AttackEvent", Fields: map[string]contracts.EventValue{"Info": ruleTestAttack(2, burst, 0)}}
	n := ruleTestNeutral()
	r := c.CompileNeutralRules(n, []RuleChoice{{2, "emblemofseveredfate", 4}}, []RuleQuery{q})
	if r.Boundary != "" || !r.Values[0].Known || r.Values[0].Expression == nil {
		t.Fatalf("missing source expression: %+v", r)
	}
	for _, er := range []float64{1, 2, 2.8, 4} {
		got, err := r.Values[0].Expression.Evaluate(func(read RuleStatRead) (float64, error) {
			if read.Owner != 2 || read.Stat != "er" || read.Mode != "non_extra_stat" || read.Order != 40 || read.Frame != 20 {
				t.Fatal(read)
			}
			return er, nil
		})
		if err != nil || math.Abs(got-math.Min(.75, (er+.2)*.25)) > 1e-12 {
			t.Fatal(er, got, err)
		}
	}
	q.Attack.Fields["Info"] = ruleTestAttack(2, skill, 0)
	r = c.CompileNeutralRules(n, []RuleChoice{{2, "emblemofseveredfate", 4}}, []RuleQuery{q})
	if r.Boundary != "" || !r.Values[0].Known || r.Values[0].Value != 0 || r.Values[0].Expression != nil {
		t.Fatalf("non-burst received bonus: %+v", r)
	}
	// Legacy constant-vector API must not quietly freeze that same stat read.
	r = c.ReplayNeutralRules(n, []RuleChoice{{2, "emblemofseveredfate", 4}}, []RuleQuery{q})
	if !strings.Contains(r.Boundary, "bound expression") {
		t.Fatal(r)
	}
}

package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"strings"
	"testing"
)

func testRule(t *testing.T, source string, libraries map[string][]byte) *ruleVM {
	t.Helper()
	p, err := compileRuleProgram(map[string][]byte{"internal/artifacts/test/rule.go": []byte("package sample\n" + source)}, libraries)
	if err != nil {
		t.Fatal(err)
	}
	return newRuleVM(p, nil, 10000)
}
func TestRuleLexicalClosureStateAndControl(t *testing.T) {
	v := testRule(t, `
type Set struct { count int }
func Start() any {
 s := Set{}
 makeHook := func(delta int) func() int { return func() int { s.count += delta; return s.count } }
 a := makeHook(2)
 b := makeHook(5)
 result := []float64{float64(a()), float64(b()), float64(a())}
 return result
}`, nil)
	x, err := v.entry("Start")
	if err != nil {
		t.Fatal(err)
	}
	a := ruleArray(x)
	if len(a) != 3 || a[0] != float64(2) || a[1] != float64(7) || a[2] != float64(9) {
		t.Fatal(a)
	}
}
func TestRuleImportedConstantsFunctionAndSwitch(t *testing.T) {
	v := testRule(t, `import a "github.com/genshinsim/gcsim/pkg/example"
func Start() float64 {
 out := 0.0
 for _, n := range []float64{0, 1, 2, 3, 4} {
  if !a.Accept(int(n)) { continue }
  switch int(n) { case a.First: out += 2; default: out += 4 }
 }
 return out
}`, map[string][]byte{"pkg/example/enum.go": []byte(`package example
type Tag int
const (Zero Tag = iota; First; Second; End)
func Accept(n int) bool { return First <= n && n < End }
`)})
	x, err := v.entry("Start")
	if err != nil || x != float64(6) {
		t.Fatal(x, err)
	}
}
func TestRuleRangeBindingsAndEarlyReturn(t *testing.T) {
	v := testRule(t, `
func Start() float64 {
 callbacks := make([]func() float64, 2)
 for i, n := range []float64{7, 11} { callbacks[i] = func() float64 { return n } }
 for i := 0; i < 10; i++ { if i > 2 { break } }
 return callbacks[0]()*10 + callbacks[1]()
}`, nil)
	x, err := v.entry("Start")
	if err != nil || x != float64(81) {
		t.Fatal(x, err)
	}
}
func TestRuleUnknownIsNotFalseAndHostHasNoIO(t *testing.T) {
	for _, source := range []string{
		`func Start(x any) float64 { if _, ok := x.(int); !ok { return 0 }; return 1 }`,
		`import "os"; func Start(x any) float64 { os.Remove("do-not-touch"); return 1 }`,
		`func Start(x any) float64 { for {}; return 1 }`,
		`func Start(x any) float64 { return 5/2 }`,
	} {
		v := testRule(t, source, nil)
		_, err := v.entry("Start", ruleUnknown{"unobserved payload"})
		if err == nil {
			t.Fatal("unsupported rule became a value", source)
		}
	}
}
func TestRuleNewSetThenInitAndVariadicAssertions(t *testing.T) {
	v := testRule(t, `
type Set struct { count int; hook func(...any) }
func (s *Set) Init() error {
 s.hook = func(args ...any) { n, ok := args[0].(float64); if !ok { return }; s.count += int(n) }
 return nil
}
func NewSet(n int) (*Set, error) { s := Set{count:n}; return &s,nil }
func Start() float64 { s, err := NewSet(2); if err != nil { return -1 }; s.Init(); s.hook("bad"); s.hook(5.0); return float64(s.count) }
`, nil)
	x, err := v.entry("Start")
	if err != nil || x != float64(7) {
		t.Fatal(x, err)
	}
}
func TestRuleSourceErrorsRemainLocal(t *testing.T) {
	v := testRule(t, `func Start() float64 { return missing() }`, nil)
	_, err := v.entry("Start")
	if err == nil || !strings.Contains(err.Error(), "unknown source symbol") {
		t.Fatal(err)
	}
}

func TestRuleStructCopiesDoNotAliasPointers(t *testing.T) {
	v := testRule(t, `type S struct { n int }
func (s S) Value() int { s.n += 10; return s.n }
func (s *S) Change() { s.n += 1 }
func Start() float64 { a:=S{n:2}; b:=a; b.Change(); p:=&a; p.Change(); b.Value(); return float64(a.n*100+b.n) }`, nil)
	x, err := v.entry("Start")
	if err != nil || x != float64(303) {
		t.Fatal(x, err)
	}
}

func TestRuleObservedNumberAssertionRetainsType(t *testing.T) {
	v := testRule(t, `func Start(x any) float64 { if _,ok:=x.(int);ok {return 1};return 0 }`, nil)
	x, err := v.entry("Start", ruleTypedNumber{3, "float64"})
	if err != nil || x != float64(0) {
		t.Fatal(x, err)
	}
	x, err = v.entry("Start", ruleTypedNumber{3, "int"})
	if err != nil || x != float64(1) {
		t.Fatal(x, err)
	}
}

func TestRuleAmountCannotMutateCapturedState(t *testing.T) {
	v := testRule(t, `func Start() func() float64 { n:=1.0;return func() float64 { n++;return n } }`, nil)
	f, err := v.entry("Start")
	if err != nil {
		t.Fatal(err)
	}
	v.readOnly = true
	if _, err = ruleTry(func() any { return v.invoke(f, nil) }); err == nil {
		t.Fatal("Amount replay mutated source state")
	}
}

func TestRuleObservedPayloadCannotBeSilentlyMutated(t *testing.T) {
	h := &ruleReplayHost{}
	for _, source := range []string{
		`func Start(x any) { x.Info.Value = 7 }`,
		`func Start(x any) { x.Stats[0] = 7 }`,
	} {
		v := testRule(t, source, nil)
		x := h.wire(contracts.EventValue{Kind: "object", Fields: map[string]contracts.EventValue{
			"Info":  {Kind: "object", Fields: map[string]contracts.EventValue{"Value": {Kind: "number", Number: 1}}},
			"Stats": {Kind: "array", Items: []contracts.EventValue{{Kind: "number", Number: 1}}},
		}})
		if _, err := v.entry("Start", x); err == nil {
			t.Fatal("observed event mutation was dropped instead of diagnosed")
		}
	}
}

func TestRuleDeletionShadowsNeutralStateAndAmountCannotDelete(t *testing.T) {
	h := &ruleReplayHost{frame: 3, stateComplete: true, touched: map[ruleModifierIdentity]bool{}, state: []RuleState{{0, "key", -1}}}
	if !h.statusActive(0, "key") {
		t.Fatal("missing original state")
	}
	h.call(ruleRef{kind: "char", index: 0}, "DeleteStatus", []any{"key"})
	if h.statusActive(0, "key") {
		t.Fatal("deleted status revived from snapshot")
	}
	if _, err := ruleTry(func() any { return h.query(RuleQuery{Owner: 0, Kind: "stat"}) }); err == nil {
		t.Fatal("old modifier remained additive after deletion")
	}
	v := testRule(t, `func Start(c any) { c.DeleteStatus("key") }`, nil)
	v.host, v.readOnly, h.vm = h, true, v
	if _, err := v.entry("Start", ruleRef{kind: "char", index: 0}); err == nil {
		t.Fatal("readonly Amount mutated host lifecycle")
	}
}

func TestRuleHitlagExtendsOnlyLiveMatchingRecipients(t *testing.T) {
	h := &ruleReplayHost{mods: []replayMod{
		{owner: 0, target: -1, expiry: 10, hitlag: true},
		{owner: -1, target: 9, expiry: 10, hitlag: true},
		{owner: -1, target: 8, expiry: 10, hitlag: true},
		{owner: -1, target: 9, expiry: 5, hitlag: true},
	}}
	h.applyHitlag(contracts.NeutralHitlagEvent{Owner: -1, Target: 9, Frame: 5, Extension: 6})
	if h.mods[0].expiry != 10 || h.mods[1].expiry != 16 || h.mods[2].expiry != 10 || h.mods[3].expiry != 5 {
		t.Fatal(h.mods)
	}
	h.applyHitlag(contracts.NeutralHitlagEvent{Owner: 0, Target: -1, Frame: 6, Extension: 3})
	if h.mods[0].expiry != 13 {
		t.Fatal(h.mods)
	}
	h.applyHitlag(contracts.NeutralHitlagEvent{Owner: 0, Target: -1, Frame: 6, Extension: -20})
	if h.mods[0].expiry != 10 || h.mods[0].extension != 0 {
		t.Fatal("extension was not clamped", h.mods)
	}
}

func TestRuleSubscriptionsReplaceDeleteAndDoNotGrowCurrentEmission(t *testing.T) {
	v := testRule(t, `
	func Start(e any) any {
	 n := 0
	 first := true
 e.Subscribe(1, func(...any) {
  n += 1
  e.Subscribe(1, func(...any) { n += 20 }, "later")
  e.Unsubscribe(1, "deleted")
  if first { e.Subscribe(1, func(...any) { n += 100 }, "new"); first = false }
 }, "first")
 e.Subscribe(1, func(...any) { n += 2 }, "later")
 e.Subscribe(1, func(...any) { n += 3 }, "deleted")
	 return func() int { return n }
	}
`, nil)
	h := &ruleReplayHost{subs: map[int][]ruleSubscription{}, uncertainty: map[string]bool{}, vm: v}
	v.host = h
	result, err := v.entry("Start", ruleRef{kind: "events"})
	if err != nil {
		t.Fatal(err)
	}
	for _, want := range []float64{21, 142} {
		if err := h.emit(contracts.CombatEvent{Event: 1}); err != nil {
			t.Fatal(err)
		}
		x, err := ruleTry(func() any { return v.invoke(result, nil) })
		if err != nil || x != want {
			t.Fatal(x, want, err)
		}
	}
}

func TestRuleConstructorCharacterVisibility(t *testing.T) {
	h := &ruleReplayHost{context: ruleTestNeutral().Context}
	for _, count := range []int{1, 2, 4} {
		h.visibleCharacters = count
		x, ok := h.call(ruleRef{kind: "player"}, "Chars", nil)
		if !ok || len(ruleArray(x)) != count {
			t.Fatal(x, ok)
		}
	}
}

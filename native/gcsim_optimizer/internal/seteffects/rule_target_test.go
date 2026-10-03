package seteffects

// The neutral source interpreter must not confuse an unobserved interface with
// a false source guard. These synthetic payloads pin the observer ABI, not game
// constants; the managed fixture gate checks the actual engine export.
import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"go/token"
	"testing"
)

func TestRuleTargetEventTypeAndAttestation(t *testing.T) {
	h := &ruleReplayHost{targets: map[int]contracts.EventValue{
		7: {Kind: "target", Fields: map[string]contracts.EventValue{"Type": {Kind: "number", Number: 1}}},
	}}
	eventTarget := func(id, targetType int, includeType bool) ruleRef {
		fields := map[string]contracts.EventValue{"Key": {Kind: "number", Number: float64(id)}}
		if includeType {
			fields["Type"] = contracts.EventValue{Kind: "number", Number: float64(targetType)}
		}
		value := h.wire(contracts.EventValue{Kind: "target", Type: "*" + gcsimImport + "pkg/enemy.Enemy", Fields: fields})
		ref, ok := value.(ruleRef)
		if !ok {
			t.Fatalf("target event did not wire to a ref: %#v", value)
		}
		return ref
	}
	typeOf := func(ref ruleRef) any {
		t.Helper()
		value, ok := h.call(ref, "Type", nil)
		if !ok {
			t.Fatal("target Type method was not handled")
		}
		return value
	}
	const (
		enemyType  = 0
		gadgetType = 2
	)
	gadget := eventTarget(7, gadgetType, true)
	enemy := eventTarget(8, enemyType, true)
	if got := typeOf(gadget); got != float64(gadgetType) {
		t.Fatalf("event gadget Type = %#v, want %d", got, gadgetType)
	}
	if got := typeOf(enemy); got != float64(enemyType) {
		t.Fatalf("event enemy Type = %#v, want %d", got, enemyType)
	}
	if ruleBinary(token.EQL, typeOf(gadget), typeOf(enemy)) != false {
		t.Fatal("enemy and gadget event types were conflated")
	}
	if ruleBinary(token.EQL, gadget, ruleRef{kind: "target", index: 7, typ: gadget.typ}) != true {
		t.Fatal("event evidence changed target reference identity")
	}
	if implemented, ok := h.field(gadget, "$implements:"+gcsimImport+"pkg/core/info.Target"); !ok || implemented != true {
		t.Fatalf("Target assertion evidence missing: %#v, %v", implemented, ok)
	}
	if other, ok := h.field(gadget, "$implements:"+gcsimImport+"pkg/core.Reactable"); !ok {
		t.Fatal("unobserved non-Target interface was not represented as unknown")
	} else if _, unknown := other.(ruleUnknown); !unknown {
		t.Fatalf("Target attestation was broadened to another interface: %#v", other)
	}
	if missing := typeOf(eventTarget(9, 0, false)); missing == nil {
		t.Fatal("missing event target Type became nil")
	} else if _, unknown := missing.(ruleUnknown); !unknown {
		t.Fatalf("missing event target Type was fabricated from world state: %#v", missing)
	}
	// Query-created refs retain the prior world-backed Type behavior.
	if got := typeOf(ruleRef{kind: "target", index: 7, typ: gadget.typ}); got != float64(1) {
		t.Fatalf("world-backed target Type = %#v, want 1", got)
	}
	if got := typeOf(eventTarget(7, 0, false)); got != float64(1) {
		t.Fatalf("missing event enum must retain independent world evidence: %#v", got)
	}
}

func TestRuleTargetInterfaceEvidenceIsNotConcreteTypeEquality(t *testing.T) {
	for _, test := range []struct {
		present, implemented bool
		want                 float64
	}{{true, true, 1}, {true, false, 0}, {false, false, 0}} {
		v := testRule(t, `import "github.com/genshinsim/gcsim/pkg/core"
func Start(target any) float64 {if _,ok:=target.(core.Reactable);ok{return 1};return 0}`, nil)
		h := &ruleReplayHost{targets: map[int]contracts.EventValue{}}
		v.host = h
		if test.present {
			h.targets[7] = contracts.EventValue{Kind: "target", Fields: map[string]contracts.EventValue{"Interfaces": {Kind: "map", Fields: map[string]contracts.EventValue{gcsimImport + "pkg/core.Reactable": {Kind: "bool", Boolean: test.implemented}}}}}
		}
		x, err := v.entry("Start", ruleRef{kind: "target", index: 7, typ: gcsimImport + "pkg/enemy.Enemy"})
		if test.present && (err != nil || x != test.want) {
			t.Fatal(test, x, err)
		}
		if !test.present && err == nil {
			t.Fatal("missing interface silently became a false guard", x)
		}
	}
}

func TestRuleTargetAuraFollowsObservedQueryWorld(t *testing.T) {
	h := &ruleReplayHost{}
	world := &contracts.NeutralWorldLedger{Complete: true}
	for _, active := range []bool{false, true, false} {
		world.States = append(world.States, contracts.NeutralWorldState{Order: uint64(len(world.States) + 1), Targets: []contracts.EventValue{{Kind: "target", Fields: map[string]contracts.EventValue{
			"Key": {Kind: "number", Number: 7}, "Auras": {Kind: "array", Items: []contracts.EventValue{{Kind: "bool", Boolean: active}}},
		}}}})
	}
	for i, want := range []bool{false, true, false} {
		h.worldAt(world, uint64(i+1))
		value, ok := h.call(ruleRef{kind: "target", index: 7}, "AuraContains", []any{float64(0)})
		if !ok || value != want {
			t.Fatal(i, value, ok)
		}
	}
	h.worldAt(nil, 4)
	value, _ := h.call(ruleRef{kind: "target", index: 7}, "AuraContains", []any{float64(0)})
	if _, unknown := value.(ruleUnknown); !unknown {
		t.Fatal("missing aura became false", value)
	}
}

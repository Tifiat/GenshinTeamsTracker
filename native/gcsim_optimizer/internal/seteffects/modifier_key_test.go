package seteffects

import "testing"

func TestSharedModifierGroupingRequiresLiteralSourceKey(t *testing.T) {
	r := Recipe{Effect: Effect{Kind: "resistance", Fields: []Field{{Name: "Base", Value: Expression{Kind: "call", Inputs: []Expression{{Kind: "qualified", Symbol: "github.com/genshinsim/gcsim/pkg/modifier.NewBaseWithHitlag"}, {Kind: "literal", Text: `"future-key"`}}}}}}}
	if got := SharedModifierKey(r); got != "resistance:future-key" {
		t.Fatal(got)
	}
	r.Effect.Fields[0].Value.Inputs[1] = Expression{Kind: "call", Text: "computedOwnerKey()"}
	if got := SharedModifierKey(r); got != "" {
		t.Fatal("guessed dynamic modifier key", got)
	}
}

package formula

import (
	"math"
	"testing"
)

func TestParametricReadRootsAndVariableEffectSpecialization(t *testing.T) {
	_, c := parametricMember(t, 1000)
	p, err := PrepareParametricWithReads([]*CompiledMember{c}, []EffectPort{{0, 1, "bonus", 20}}, []ReadRoot{{0, 8, "neutral_stat", 0}})
	if err != nil {
		t.Fatal(err)
	}
	before := p.NodeCount()
	// A disconnected read root must survive, without being added to DPS.
	if value, err := p.Evaluate([]float64{2, 3}, []float64{0}); err != nil || value != 22*23 {
		t.Fatal(value, err)
	}
	read := &InputExpression{Operation: "read", Key: "neutral_stat"}
	constant := func(x float64) *InputExpression { return &InputExpression{Operation: "constant", Value: x} }
	expr := &InputExpression{Operation: "min", Inputs: []*InputExpression{read, constant(10)}}
	bound, err := p.BindEffectExpressions(map[string]*InputExpression{"bonus": expr})
	if err != nil {
		t.Fatal(err)
	}
	for _, point := range [][]float64{{2, 3}, {4, 4}, {-1, 3}} {
		got, err := bound.Evaluate(point, nil)
		want := (20 + point[0] + math.Min(point[0]*point[1], 10)) * (20 + point[1])
		if err != nil || math.Abs(got-want) > 1e-9 {
			t.Fatal(got, want, err)
		}
		// Cross-owner stat dependence remains when fixing only one wearer.
		one, err := bound.Specialize(point, nil, 0)
		if err != nil {
			t.Fatal(err)
		}
		value, err := one.Evaluate([]float64{point[0]})
		if err != nil || math.Abs(value-want) > 1e-9 {
			t.Fatal(value, want, err)
		}
	}
	if p.NodeCount() != before {
		t.Fatal("prepared source mutated")
	}
	if _, err = p.BindEffectExpressions(map[string]*InputExpression{}); err == nil {
		t.Fatal("missing effect became zero")
	}
	if _, err = p.BindEffectExpressions(map[string]*InputExpression{"bonus": {Operation: "read", Key: "missing"}}); err == nil {
		t.Fatal("missing read accepted")
	}
	if _, err = p.BindEffectExpressions(map[string]*InputExpression{"bonus": {Operation: "effect", Key: "bonus"}}); err == nil {
		t.Fatal("self-reference accepted")
	}
}

func TestParametricReadCannotReferToOwnAddedEffect(t *testing.T) {
	_, c := parametricMember(t, 1000)
	p, err := PrepareParametricWithReads([]*CompiledMember{c}, []EffectPort{{0, 1, "bonus", 20}}, []ReadRoot{{0, 3, "includes_bonus", 20}})
	if err != nil {
		t.Fatal(err)
	}
	if _, err = p.BindEffectExpressions(map[string]*InputExpression{"bonus": {Operation: "read", Key: "includes_bonus"}}); err == nil {
		t.Fatal("cyclic input was silently frozen")
	}
}

func TestParametricInputExpressionArithmetic(t *testing.T) {
	_, c := parametricMember(t, 1000)
	p, err := PrepareParametric([]*CompiledMember{c}, []EffectPort{{0, 1, "bonus", 20}})
	if err != nil {
		t.Fatal(err)
	}
	for op, want := range map[string]float64{"subtract": 2, "divide": 2} {
		x := &InputExpression{Operation: op, Inputs: []*InputExpression{{Operation: "artifact", Key: "provider.em"}, {Operation: "constant", Value: 2}}}
		bound, err := p.BindEffectExpressions(map[string]*InputExpression{"bonus": x})
		if err != nil {
			t.Fatal(err)
		}
		got, err := bound.Evaluate([]float64{4, 0}, nil)
		if err != nil || got != (24+want)*20 {
			t.Fatal(op, got, err)
		}
	}
}

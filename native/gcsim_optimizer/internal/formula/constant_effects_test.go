package formula

// Synthetic arithmetic/read-root controls, not a new damage recipe. General
// dependency binding is the oracle for the constant fast path and its boundary.
import (
	"math"
	"math/rand"
	"reflect"
	"testing"
)

func TestParametricConstantEffectsMatchGeneralAndKeepLatentReads(t *testing.T) {
	_, c := parametricMember(t, 1000)
	p, err := PrepareParametricWithReads([]*CompiledMember{c}, []EffectPort{{0, 1, "bonus", 20}, {0, 8, "latent", 0}}, []ReadRoot{{0, 8, "saved_latent", 0}})
	if err != nil {
		t.Fatal(err)
	}
	if keys := p.ConstantDamageEffectKeys(); !reflect.DeepEqual(keys, []string{"bonus"}) {
		t.Fatal(keys)
	}
	rng := rand.New(rand.NewSource(29))
	for i := 0; i < 40; i++ {
		effects := map[string]*InputExpression{"bonus": {Operation: "constant", Value: rng.Float64()*20 - 10}, "latent": {Operation: "constant", Value: rng.Float64()*20 - 10}}
		fast, e := p.BindEffectExpressions(effects)
		slow, se := p.bindEffectExpressionsGeneral(effects)
		if e != nil || se != nil || !reflect.DeepEqual(fast.program.nodes, slow.program.nodes) || fast.program.root != slow.program.root {
			t.Fatal(e, se)
		}
		for j := 0; j < 5; j++ {
			point := []float64{rng.Float64()*40 - 20, rng.Float64()*40 - 20}
			a, e := fast.Evaluate(point, nil)
			b, se := slow.Evaluate(point, nil)
			if e != nil || se != nil || a != b {
				t.Fatal(a, b, e, se)
			}
			fa, _ := fast.Specialize(point, nil, 0, 1)
			sa, _ := slow.Specialize(point, nil, 0, 1)
			_, ag, _, e := fa.ValueGradient(point)
			_, bg, _, se := sa.ValueGradient(point)
			if e != nil || se != nil || !reflect.DeepEqual(ag, bg) {
				t.Fatal(ag, bg, e, se)
			}
		}
	}
	// Formerly latent ports become relevant when another effect reads them.
	effects := map[string]*InputExpression{"bonus": {Operation: "read", Key: "saved_latent"}, "latent": {Operation: "constant", Value: 5}}
	if _, constant, _ := p.bindConstantEffects(effects); constant {
		t.Fatal("read expression used constant projection")
	}
	bound, err := p.BindEffectExpressions(effects)
	if err != nil {
		t.Fatal(err)
	}
	got, err := bound.Evaluate([]float64{2, 3}, nil)
	if err != nil || got != (20+2+2*3+5)*23 {
		t.Fatal(got, err)
	}
	// Even an unused nonconstant/malformed input cannot authorize fast reuse.
	for _, x := range []*InputExpression{{Operation: "artifact", Key: "provider.em"}, {Operation: "constant", Value: math.NaN()}, {Operation: "constant", Inputs: []*InputExpression{{Operation: "constant"}}}} {
		effects = map[string]*InputExpression{"bonus": {Operation: "constant"}, "latent": x}
		if _, constant, _ := p.bindConstantEffects(effects); constant {
			t.Fatal("invalid constant projection")
		}
	}
}

func TestParametricConstantBindingPreservesGradientAccumulationOrder(t *testing.T) {
	// These cancelling contributions expose different reverse accumulation
	// orders exactly: the source storage order is NOT the root's operand order.
	p := &ParametricProgram{artifactCount: 1, actors: []string{"actor"}, program: &ArtifactProgram{coordinates: []string{"actor.atk"}, root: 7, nodes: []compiledNode{
		{op: opArtifactStat, coordinate: 0},
		{op: opConstant, coordinate: -1, value: 1e16},
		{op: opConstant, coordinate: -1, value: 1},
		{op: opConstant, coordinate: -1, value: -1e16},
		{op: opMultiply, coordinate: -1, inputs: []uint32{0, 1}},
		{op: opMultiply, coordinate: -1, inputs: []uint32{0, 2}},
		{op: opMultiply, coordinate: -1, inputs: []uint32{0, 3}},
		{op: opAdd, coordinate: -1, inputs: []uint32{5, 6, 4}},
	}}}
	fast, err := p.BindEffectExpressions(nil)
	slow, se := p.bindEffectExpressionsGeneral(nil)
	if err != nil || se != nil {
		t.Fatal(err, se)
	}
	_, a, _, err := fast.program.ValueGradient([]float64{0})
	_, b, _, se := slow.program.ValueGradient([]float64{0})
	if err != nil || se != nil || !reflect.DeepEqual(a, b) || a[0] != 1 || !reflect.DeepEqual(fast.program.nodes, slow.program.nodes) {
		t.Fatal(a, b, err, se)
	}
}

func TestParametricConstantEffectsPreserveProofAndBranches(t *testing.T) {
	_, c := parametricMember(t, 1000)
	c.hasOpaque = true
	c.nodes = append(c.nodes, compiledNode{op: opConstant, value: 21, coordinate: -1})
	c.nodes = append(c.nodes, compiledNode{op: opSelectLT, coordinate: -1, inputs: []uint32{1, 9, 3, 6}})
	c.channels[0].root = 10
	if err := c.buildEvaluationPlan(); err != nil {
		t.Fatal(err)
	}
	p, err := PrepareParametric([]*CompiledMember{c}, []EffectPort{{0, 1, "condition", 20}})
	if err != nil {
		t.Fatal(err)
	}
	for _, value := range []float64{0, 2, math.Copysign(0, -1)} {
		effects := map[string]*InputExpression{"condition": {Operation: "constant", Value: value}}
		fast, e := p.BindEffectExpressions(effects)
		slow, se := p.bindEffectExpressionsGeneral(effects)
		if e != nil || se != nil {
			t.Fatal(e, se)
		}
		a, e := fast.Evaluate([]float64{3, 7}, nil)
		b, se := slow.Evaluate([]float64{3, 7}, nil)
		if e != nil || se != nil || a != b || !fast.program.unresolved {
			t.Fatal(a, b, e, se)
		}
	}
}

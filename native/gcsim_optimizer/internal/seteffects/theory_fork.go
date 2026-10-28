package seteffects

import "genshinteamstracker/native/gcsim_optimizer/internal/formula"

// ForkTheory retains the immutable validated source/evidence but gives every
// continuation branch its own cache maps, FIFO order, counters and payloads.
func theoryMap[K comparable, V any](source map[K]V) map[K]V {
	if source == nil {
		return nil
	}
	out := make(map[K]V, len(source))
	for k, v := range source {
		out[k] = v
	}
	return out
}
func theoryFootprint(f ruleFootprint) ruleFootprint {
	f.reads = theoryMap(f.reads)
	f.writes = theoryMap(f.writes)
	f.statReads = theoryMap(f.statReads)
	f.statWrites = theoryMap(f.statWrites)
	return f
}

// One memo covers every retained payload in a fork, preserving ordered
// operands and shared subgraphs without sharing mutable expression nodes.
func theoryExpression(x *formula.InputExpression, memo map[*formula.InputExpression]*formula.InputExpression) *formula.InputExpression {
	if x == nil {
		return nil
	}
	if out, ok := memo[x]; ok {
		return out
	}
	out := *x
	memo[x] = &out
	if x.Inputs != nil {
		out.Inputs = make([]*formula.InputExpression, len(x.Inputs))
		for i, input := range x.Inputs {
			out.Inputs[i] = theoryExpression(input, memo)
		}
	}
	return &out
}
func theoryExpressionMap[K comparable](source map[K]*formula.InputExpression, memo map[*formula.InputExpression]*formula.InputExpression) map[K]*formula.InputExpression {
	if source == nil {
		return nil
	}
	out := make(map[K]*formula.InputExpression, len(source))
	for k, v := range source {
		out[k] = theoryExpression(v, memo)
	}
	return out
}
func theoryComponent(c neutralComponent, memo map[*formula.InputExpression]*formula.InputExpression) neutralComponent {
	c.raw = append([]float64(nil), c.raw...)
	c.expressions = theoryExpressionMap(c.expressions, memo)
	c.uncertainty = append([]string(nil), c.uncertainty...)
	c.footprint = theoryFootprint(c.footprint)
	return c
}
func theoryExpressions(x NeutralExpressions, memo map[*formula.InputExpression]*formula.InputExpression) NeutralExpressions {
	x.raw = append([]float64(nil), x.raw...)
	x.Constants = append([]float64(nil), x.Constants...)
	x.SparseEffects = theoryExpressionMap(x.SparseEffects, memo)
	x.Effects = theoryExpressionMap(x.Effects, memo)
	x.Boundaries = append([]string(nil), x.Boundaries...)
	x.Uncertainty = append([]string(nil), x.Uncertainty...)
	x.footprint = theoryFootprint(x.footprint)
	return x
}
func (b *NeutralBinding) ForkTheory() *NeutralBinding {
	if b == nil {
		return nil
	}
	out := *b
	memo := map[*formula.InputExpression]*formula.InputExpression{}
	out.twoPieceFamilies = theoryMap(b.twoPieceFamilies)
	out.composedPayloads = theoryMap(b.composedPayloads)
	for k, v := range out.composedPayloads {
		out.composedPayloads[k] = theoryExpressions(v, memo)
	}
	out.composedPayloadOrder = append([]string(nil), b.composedPayloadOrder...)
	out.components = theoryMap(b.components)
	for k, v := range out.components {
		out.components[k] = theoryComponent(v, memo)
	}
	out.groups = theoryMap(b.groups)
	for k, v := range out.groups {
		out.groups[k] = theoryComponent(v, memo)
	}
	out.groupOrder = append([]string(nil), b.groupOrder...)
	return &out
}

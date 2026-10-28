package formula

import "fmt"

// BindMixedEffects keeps the general traversal with direct literal effect leaves.
// Artifact/read/inter-effect dependencies and ordered arithmetic stay intact.
func (p *ParametricProgram) BindMixedEffects(constants []float64, sparse map[int]*InputExpression) (*ParametricProgram, error) {
	if p == nil || len(constants) != len(p.effects) {
		return nil, fmt.Errorf("mixed effect dimensions differ")
	}
	for _, value := range constants {
		if !isFinite(value) {
			return nil, fmt.Errorf("nonfinite mixed effect constant")
		}
	}
	for index, expression := range sparse {
		if index < 0 || index >= len(constants) || expression == nil {
			return nil, fmt.Errorf("invalid mixed expression coordinate")
		}
	}
	if len(sparse) == 0 {
		return p.BindConstantEffects(constants)
	}
	return p.bindEffectExpressionsInputs(nil, constants, sparse)
}

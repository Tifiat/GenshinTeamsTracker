package setcontext

// Research-only single-point ordering hint. It never produces a bound search
// program or a pruning certificate; callers must resolve shortlisted contexts
// through the ordinary exact path before accepting their scores.
import (
	"fmt"
	"math"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

// HypothesisConstantPoint evaluates one actual artifact delta against complete
// constant effects in the already prepared arithmetic graph. ok=false means
// that the exact Resolve path is required; it never denotes a zero effect.
func (m *NeutralModel) HypothesisConstantPoint(target *Context, coordinates []string, dense []float64) (float64, bool, error) {
	if m == nil || target == nil || m.origin == nil || m.prepared == nil || m.binding == nil || !m.origin.SameFrame(target) {
		return 0, false, fmt.Errorf("neutral point target differs from captured run frame")
	}
	choices := []seteffects.RuleChoice{}
	for _, actor := range target.actors {
		owner, ok := m.owners[actor]
		if !ok {
			return 0, false, fmt.Errorf("neutral point target changed owner identity")
		}
		for _, set := range target.Sets(actor) {
			if strings.TrimSpace(set.Parameters) != "" {
				return 0, false, nil
			}
			choices = append(choices, seteffects.RuleChoice{Owner: owner, Key: set.UID, Pieces: set.Count})
		}
	}
	artifacts, ok, err := hypothesisPointCoordinates(m.prepared.Coordinates(), coordinates, dense)
	if err != nil || !ok {
		return 0, false, err
	}
	effects := m.binding.CompilePackagesSparse(choices)
	if !effects.Complete() || effects.SparseEffects != nil || effects.Constants == nil {
		return 0, false, nil
	}
	if err := m.prepareEffectDimensions(); err != nil {
		return 0, false, err
	}
	if len(effects.Constants) != len(m.effectDimensions) {
		return 0, false, nil
	}
	// Check every capture-order port, including latent or damage-dead roots,
	// before translating to the formula's independent effect-input order.
	for _, value := range effects.Constants {
		if math.IsNaN(value) || math.IsInf(value, 0) {
			return 0, false, fmt.Errorf("nonfinite neutral point effect")
		}
	}
	ordered := make([]float64, len(m.effectDimensions))
	for i, dimension := range m.effectDimensions {
		if dimension < 0 || dimension >= len(effects.Constants) {
			return 0, false, fmt.Errorf("neutral point effect dimension mismatch")
		}
		ordered[i] = effects.Constants[dimension]
	}
	// A dedicated run-local scratch copy is reused by this serial prepass.
	// Source uncertainty is the SAME as Resolve, not a bound certificate;
	// selected contexts still Resolve normally and export their warnings.
	if m.hypothesisPointProgram == nil {
		m.hypothesisPointProgram = m.prepared.WithOwnScratch()
	}
	score, err := m.hypothesisPointProgram.Evaluate(artifacts, ordered)
	if err != nil {
		return 0, false, err
	}
	if math.IsNaN(score) || math.IsInf(score, 0) {
		return 0, false, fmt.Errorf("nonfinite neutral point score")
	}
	return score, true, nil
}

func hypothesisPointCoordinates(prepared, coordinates []string, dense []float64) ([]float64, bool, error) {
	if len(prepared) != len(coordinates) || len(coordinates) != len(dense) {
		return nil, false, nil
	}
	byKey := make(map[string]float64, len(coordinates))
	for i, key := range coordinates {
		if key == "" {
			return nil, false, nil
		}
		if _, duplicate := byKey[key]; duplicate {
			return nil, false, nil
		}
		value := dense[i]
		if math.IsNaN(value) || math.IsInf(value, 0) {
			return nil, false, fmt.Errorf("nonfinite neutral point artifact delta")
		}
		byKey[key] = value
	}
	ordered := make([]float64, len(prepared))
	for i, key := range prepared {
		value, found := byKey[key]
		if !found {
			return nil, false, nil
		}
		ordered[i] = value
		delete(byKey, key)
	}
	if len(byKey) != 0 {
		return nil, false, nil
	}
	return ordered, true, nil
}

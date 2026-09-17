package seteffects

import "fmt"

// Members of a seed panel can expose different coordinates. The caller checks
// the complete panel domain once; a coordinate absent from one member has no
// represented response in that member, not an invented dependency.
func anchorVector(coords []string, delta map[string]float64, strict bool) ([]float64, error) {
	indices := map[string]int{}
	for i, k := range coords {
		indices[k] = i
	}
	out := make([]float64, len(coords))
	for k, v := range delta {
		if !finite(v) {
			return nil, fmt.Errorf("nonfinite guide anchor")
		}
		i, ok := indices[k]
		if !ok {
			if strict && v != 0 {
				return nil, fmt.Errorf("unrepresented guide anchor: %s", k)
			}
			continue
		}
		out[i] = v
	}
	return out, nil
}

// Reanchor keeps the exact captured graph, but computes marginal priorities at
// the current artifact combination, not permanently at its original stats.
// It is not permission to move the guide across a changed set context.
func (p *ExposureProbe) Reanchor(delta map[string]float64) error {
	if p == nil {
		return fmt.Errorf("missing exposure probe")
	}
	dense, e := anchorVector(p.panel.Coordinates(), delta, true)
	if e != nil {
		return e
	}
	base, e := p.panel.EvaluateChannelDPS(dense)
	if e != nil {
		return e
	}
	p.anchor = dense
	p.baseline = base
	p.cache = map[string][][]float64{}
	p.Evaluations++
	return nil
}

func (p *InputProbe) Reanchor(delta map[string]float64) error {
	if p == nil {
		return fmt.Errorf("missing input probe")
	}
	dense, e := anchorVector(p.coordinates, delta, false)
	if e != nil {
		return e
	}
	base, e := p.program.Evaluate(dense, nil)
	if e != nil {
		return e
	}
	p.zero = dense
	p.baseline = base.Damage
	return nil
}

func (p *ResistanceProbe) Reanchor(delta map[string]float64) error {
	if p == nil {
		return fmt.Errorf("missing resistance probe")
	}
	dense, e := anchorVector(p.coordinates, delta, false)
	if e != nil {
		return e
	}
	base, e := p.program.Evaluate(dense, nil)
	if e != nil {
		return e
	}
	p.zero = dense
	p.baseline = base.Damage
	return nil
}

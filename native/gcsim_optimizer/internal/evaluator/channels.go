package evaluator

import "fmt"

// EvaluateChannelDPS returns each member's original ordered channel values,
// already weighted by member duration and panel probability. Summing every row
// equals EvaluateDPS. Intended for bounded source-effect guide probes, not an
// alternate formula scorer or permission to replace a captured set effect.
func (panel *Panel) EvaluateChannelDPS(deltas []float64) ([][]float64, error) {
	if panel == nil || len(panel.members) == 0 {
		return nil, fmt.Errorf("compiled panel required")
	}
	out := make([][]float64, len(panel.members))
	for i, member := range panel.members {
		values, e := member.EvaluateChannelDamageDense(deltas)
		if e != nil {
			return nil, e
		}
		weight := 1000 / (float64(member.DurationMS()) * float64(len(panel.members)))
		for j := range values {
			values[j] *= weight
		}
		out[i] = values
	}
	return out, nil
}

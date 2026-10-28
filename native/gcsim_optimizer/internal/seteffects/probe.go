package seteffects

import (
	"fmt"
	"math"
	"strconv"
)

// FormulaPanel is the existing compiled FAST panel. No alternate damage
// formula or engine simulation is introduced for discovery signals.
type FormulaPanel interface {
	Coordinates() []string
	EvaluateDPS([]float64) (float64, error)
}
type ResponseSignal struct {
	StatSignal
	Wearer                   string  `json:"wearer"`
	HypotheticalIncrementDPS float64 `json:"hypothetical_increment_dps"`
	Represented              bool    `json:"represented"`
}
type SignalProbe struct {
	panel       FormulaPanel
	coordinates map[string]int
	width       int
	baseline    float64
	cache       map[string]float64
	Evaluations int
}

// NewSignalProbe binds to one unchanged captured context and artifact anchor.
// Each output answers ONLY: if this amount were a raw-stat increment here, how
// would the known formulas respond? It is a proposal-order feature, not the
// candidate set's DPS: old bonuses are still present, activation/Extra semantics
// may differ, and effects with absent coordinates remain unrepresented, not zero.
func NewSignalProbe(panel FormulaPanel) (*SignalProbe, error) {
	if panel == nil {
		return nil, fmt.Errorf("formula panel required")
	}
	coords := panel.Coordinates()
	index := map[string]int{}
	for i, key := range coords {
		if _, ok := index[key]; ok {
			return nil, fmt.Errorf("duplicate coordinate")
		}
		index[key] = i
	}
	baseline, e := panel.EvaluateDPS(make([]float64, len(coords)))
	if e != nil {
		return nil, e
	}
	if math.IsNaN(baseline) || math.IsInf(baseline, 0) {
		return nil, fmt.Errorf("nonfinite formula baseline")
	}
	return &SignalProbe{panel: panel, coordinates: index, width: len(coords), baseline: baseline, cache: map[string]float64{}, Evaluations: 1}, nil
}
func (p *SignalProbe) Probe(wearer string, signal StatSignal) (ResponseSignal, error) {
	out := ResponseSignal{StatSignal: signal, Wearer: wearer}
	if p == nil || wearer == "" || math.IsNaN(signal.Amount) || math.IsInf(signal.Amount, 0) {
		return out, fmt.Errorf("invalid response signal")
	}
	coordinate := wearer + "." + signal.StatKey
	index, ok := p.coordinates[coordinate]
	if !ok {
		return out, nil
	}
	out.Represented = true
	cacheKey := coordinate + "=" + strconv.FormatFloat(signal.Amount, 'g', -1, 64)
	if gain, ok := p.cache[cacheKey]; ok {
		out.HypotheticalIncrementDPS = gain
		return out, nil
	}
	deltas := make([]float64, p.width)
	deltas[index] = signal.Amount
	score, e := p.panel.EvaluateDPS(deltas)
	if e != nil {
		return out, e
	}
	if math.IsNaN(score) || math.IsInf(score, 0) {
		return out, fmt.Errorf("nonfinite response")
	}
	out.HypotheticalIncrementDPS = score - p.baseline
	p.cache[cacheKey] = out.HypotheticalIncrementDPS
	p.Evaluations++
	return out, nil
}

package theoryalloc

import "math"

// StatKeys returns substat keys in the objective gradient's coordinate order.
func StatKeys() [10]string { return statKeys }

// StatValues returns the maximum roll values corresponding to StatKeys.
func StatValues() [10]float64 { return statValues }

// MainValues returns an independent copy of the idealized main-stat values.
func MainValues() map[string]float64 {
	out := make(map[string]float64, len(mainValues))
	for key, value := range mainValues {
		out[key] = value
	}
	return out
}

// MainChoices returns independent main choices for flower, plume, sands,
// goblet, and circlet, respectively.
func MainChoices() [5][]string {
	var out [5][]string
	for slot, choices := range mainChoices {
		out[slot] = append([]string(nil), choices...)
	}
	return out
}

// This comparison is the only dependency extracted from the research
// marginal.go file. Its threshold is retained exactly.
func quarterBetter(value, incumbent float64) bool {
	return value > incumbent+1e-12*(1+math.Abs(incumbent))
}

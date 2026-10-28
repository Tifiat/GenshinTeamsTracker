package search

import "testing"

// Tiny counterexamples explain why player priorities are experimental, not
// universal certificates. Coefficients here are synthetic, not game rules.
func TestHypothesisPlayerPriorityCounterexamples(t *testing.T) {
	damage := func(atk, cr, cd float64) float64 {
		if cr > 1 {
			cr = 1
		}
		return atk * (1 + cr*cd)
	}
	// Higher crit mass loses at capped chance; another item wins by damage.
	if 2*.20 < .30 || damage(100, 1+.20, 1) >= damage(100, 1, 1+.30) {
		t.Fatal("crit-mass counterexample lost")
	}
	// A chance bonus has zero utility on fixed capped gear, yet enables a
	// better chance/damage split. Fixed-build zero cannot delete its family.
	if damage(100, 1+.4, 1) != damage(100, 1, 1) || damage(100, .6+.4, 1.8) <= damage(100, 1, 1) {
		t.Fatal("zero-at-anchor is not global zero")
	}
	// A larger full bonus does not compensate arbitrarily weak set pieces.
	if damage(100, .5+.4, 1) >= damage(180, .5, 1) {
		t.Fatal("bonus-only rank counterexample lost")
	}
}

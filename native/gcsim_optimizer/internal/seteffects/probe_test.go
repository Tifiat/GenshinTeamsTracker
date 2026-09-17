package seteffects

import "testing"

type syntheticPanel struct{}

func (syntheticPanel) Coordinates() []string                    { return []string{"holder.hp", "holder.em"} }
func (syntheticPanel) EvaluateDPS(d []float64) (float64, error) { return 100 + 3*d[0] + 2*d[1], nil }

func TestSignalsShareExistingFormulaAndCacheWithoutCallingMissingStatZero(t *testing.T) {
	p, e := NewSignalProbe(syntheticPanel{})
	if e != nil {
		t.Fatal(e)
	}
	signal := StatSignal{EffectID: "a", StatKey: "hp", Amount: 10, Activation: Unknown}
	got, e := p.Probe("holder", signal)
	if e != nil || !got.Represented || got.HypotheticalIncrementDPS != 30 {
		t.Fatal(got, e)
	}
	signal.EffectID = "other"
	if _, e = p.Probe("holder", signal); e != nil || p.Evaluations != 2 {
		t.Fatal("duplicate calculation", e, p.Evaluations)
	}
	signal.StatKey = "attack_speed"
	got, e = p.Probe("holder", signal)
	if e != nil || got.Represented || p.Evaluations != 2 {
		t.Fatal("unknown stat was represented as zero effect", got, e)
	}
}

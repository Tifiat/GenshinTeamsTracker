package evaluator

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"math"
	"testing"
)

func TestParametricSearchViewUsesBoundProgramAndNoStaleActorDetail(t *testing.T) {
	req, ir := fixtures(t)
	panel, err := Compile(req, ir)
	if err != nil {
		t.Fatal(err)
	}
	var ports []formula.EffectPort
	for i, m := range ir.Members {
		for _, n := range m.Nodes {
			if n.Operation == "constant" && n.Value == "100" {
				ports = append(ports, formula.EffectPort{Member: i, NodeID: n.NodeID, Key: "bonus", Observed: 100})
				break
			}
		}
	}
	if len(ports) != len(ir.Members) {
		t.Fatal("fixture lost test constant")
	}
	prepared, err := panel.PrepareEffectInputs(ports)
	if err != nil {
		t.Fatal(err)
	}
	bound, err := prepared.BindEffectExpressions(map[string]*formula.InputExpression{"bonus": {Operation: "constant", Value: 20}})
	if err != nil {
		t.Fatal(err)
	}
	view, err := panel.ParametricView(bound, []string{"test_approximate_window"})
	if err != nil {
		t.Fatal(err)
	}
	for _, amount := range []float64{0, .1, -.1} {
		x := make([]float64, len(view.Coordinates()))
		for i := range x {
			x[i] = amount
		}
		want, err := prepared.Evaluate(x, []float64{20})
		if err != nil {
			t.Fatal(err)
		}
		got, err := view.EvaluateDPS(x)
		if err != nil || math.Abs(got-want) > 1e-12 {
			t.Fatal(got, want, err)
		}
		local, err := view.ArtifactProgram(x, 0)
		if err != nil || !local.HasUnresolvedDependencies() {
			t.Fatal(local, err)
		}
		got, err = view.EvaluateDPSForActor(x, 0)
		if err != nil || got != want {
			t.Fatal(got, want, err)
		}
		if _, err = view.Evaluate(x); err == nil {
			t.Fatal("stale actor detail returned")
		}
		if _, err = view.EvaluateChannelDPS(x); err == nil {
			t.Fatal("stale channel detail returned")
		}
	}
	if _, err := panel.ParametricView(prepared, nil); err == nil {
		t.Fatal("unbound inputs accepted")
	}
}

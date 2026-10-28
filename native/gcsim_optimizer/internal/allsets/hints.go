package allsets

import (
	"context"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"math"
	"strings"
)

func packageHintFor(wearer string, p domain.Package, hints map[HintKey]Hint) (Hint, error) {
	hint := Hint{SharedGroups: map[string]float64{}}
	for _, s := range p.Sets {
		h, ok := hints[HintKey{wearer, s.SetUID, s.Count}]
		if !ok {
			hint.Unresolved = true
		}
		if math.IsNaN(h.PeakIncrement) || math.IsInf(h.PeakIncrement, 0) {
			return hint, fmt.Errorf("nonfinite source hint")
		}
		hint.PeakIncrement = math.Max(hint.PeakIncrement, h.PeakIncrement)
		for k, v := range h.SharedGroups {
			if k == "" || math.IsNaN(v) || math.IsInf(v, 0) {
				return hint, fmt.Errorf("invalid shared hint")
			}
			hint.SharedGroups[k] = math.Max(hint.SharedGroups[k], v)
		}
		hint.Shared = hint.Shared || h.Shared
		hint.NewOutput = hint.NewOutput || h.NewOutput
		hint.Unresolved = hint.Unresolved || h.Unresolved
	}
	return hint, nil
}

func sharedPeak(hints [4]Hint) map[string]float64 {
	out := map[string]float64{}
	for _, h := range hints {
		for k, v := range h.SharedGroups {
			out[k] = math.Max(out[k], v)
		}
	}
	return out
}

func rawPriorities(ctx context.Context, index *domain.Index, panel *evaluator.Panel) ([]float64, []float64, error) {
	if index == nil || panel == nil || strings.Join(index.Coordinates, "\x00") != strings.Join(panel.Coordinates(), "\x00") {
		return nil, nil, fmt.Errorf("proposal coordinate mismatch")
	}
	anchor, e := index.DenseDeltas(index.Incumbent)
	if e != nil {
		return nil, nil, e
	}
	baseline, e := panel.EvaluateDPS(anchor)
	if e != nil {
		return nil, nil, e
	}
	weights := make([]float64, len(anchor))
	delta := append([]float64(nil), anchor...)
	for i := range weights {
		if e = ctx.Err(); e != nil {
			return nil, nil, e
		}
		delta[i] = anchor[i] + .001
		v, e := panel.EvaluateDPS(delta)
		if e != nil {
			return nil, nil, e
		}
		weights[i] = (v - baseline) / .001
		delta[i] = anchor[i]
	}
	return weights, anchor, nil
}

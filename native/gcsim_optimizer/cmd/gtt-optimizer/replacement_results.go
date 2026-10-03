package main

import (
	"context"

	"genshinteamstracker/native/gcsim_optimizer/internal/allsets"
	"genshinteamstracker/native/gcsim_optimizer/internal/energy"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

// Each group retains one anchor and independently scored one-item neighbours.
// Context/bonus ownership stays with that group's candidate, including captures.
func allSetReplacements(ctx context.Context, rows []allsets.Candidate, count int) ([]allsets.Candidate, error) {
	seen := map[string]bool{}
	var out []allsets.Candidate
	for _, candidate := range rows {
		key := candidate.Context.Key()
		if seen[key] {
			continue
		}
		seen[key] = true
		out = append(out, candidate)
		panel, err := candidate.Handle.SearchPanel()
		if err != nil {
			return nil, err
		}
		alternatives, err := search.SingleReplacements(ctx, candidate.Index, panel, candidate.Score, count, candidate.EnergyModel)
		if err != nil {
			return nil, err
		}
		for _, score := range alternatives {
			row := candidate
			row.Score = score
			if row.EnergyModel != nil {
				assessment, err := row.EnergyModel.Assess(score.Assignment)
				if err != nil {
					return nil, err
				}
				row.Energy = &energy.Feasibility{Feasible: assessment.Feasible, MaximumShortage: assessment.MaximumShortage}
			}
			out = append(out, row)
		}
	}
	return out, nil
}

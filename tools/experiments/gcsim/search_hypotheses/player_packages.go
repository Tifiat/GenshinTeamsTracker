package allsets

import (
	"context"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
	"sort"
)

// Research heuristic, not an upper bound. Rank only plain recognized 2p/2+2
// by attainable item quality plus their source-derived owner-stat bonus.
// Unknown effects, all 4p, no-bonus and the incumbent always get exact work.
func hypothesisPackages(ctx context.Context, anchor Candidate, actor int, feasible []domain.Package, sources *seteffects.SourceCatalog, width int) ([]domain.Package, error) {
	panel, err := anchor.Handle.SearchPanel()
	if err != nil {
		return nil, err
	}
	weights, _, err := rawPriorities(ctx, anchor.Index, panel)
	if err != nil {
		return nil, err
	}
	priority, err := anchor.Index.ArtifactLinearPriorities(actor, weights)
	if err != nil {
		return nil, err
	}
	coordinates := map[string]int{}
	for i, key := range anchor.Index.Coordinates {
		coordinates[key] = i
	}
	occupied := map[int64]bool{}
	for owner, ids := range anchor.Score.Assignment {
		if owner != actor {
			for _, id := range ids {
				occupied[id] = true
			}
		}
	}
	type ranked struct {
		index int
		value float64
	}
	var rankedRows []ranked
	selected := map[int]bool{}
	for i, pack := range feasible {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		if len(pack.Sets) == 0 || pack.Key() == anchor.Packages[actor].Key() {
			selected[i] = true
			continue
		}
		bonus, known := 0.0, true
		for _, set := range pack.Sets {
			if set.Count != 2 {
				known = false
				break
			}
			stats, ok := sources.HypothesisLiteral2P(set.SetUID)
			if !ok {
				known = false
				break
			}
			keys := make([]string, 0, len(stats))
			for key := range stats {
				keys = append(keys, key)
			}
			sort.Strings(keys)
			for _, key := range keys {
				if n, ok := coordinates[anchor.Index.Wearers[actor].WearerKey+"."+key]; ok {
					bonus += weights[n] * stats[key]
				}
			}
		}
		if !known {
			selected[i] = true
			continue
		}
		_, value, err := anchor.Index.PackageLinearAssignment(pack, priority, occupied)
		// Reservation failure is not a weak-set certificate. Exact route may
		// release another wearer through its joint allocation fallback.
		if err != nil {
			selected[i] = true
			continue
		}
		rankedRows = append(rankedRows, ranked{i, value + bonus})
	}
	sort.SliceStable(rankedRows, func(i, j int) bool { return rankedRows[i].value > rankedRows[j].value })
	for i := 0; i < len(rankedRows) && i < width; i++ {
		selected[rankedRows[i].index] = true
	}
	out := make([]domain.Package, 0, len(selected))
	for i, pack := range feasible {
		if selected[i] {
			out = append(out, pack)
		}
	}
	fmt.Printf("HYPOTHESIS_PACKAGE_SHORTLIST actor=%d full=%d ranked_simple=%d selected=%d width=%d\n", actor, len(feasible), len(rankedRows), len(out), width)
	return out, nil
}

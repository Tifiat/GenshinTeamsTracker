package allsets

import (
	"context"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"sort"
	"time"
)

const hypothesisAdaptivePoint = false

// Exact value for ONE legal seed is not a bound on the package's best build.
// This experiment avoids building a reduced context for weak single-point
// proposals; every symbolic/unknown/unallocatable context retains exact work.
func hypothesisPointPackages(ctx context.Context, anchor Candidate, actor int, feasible []domain.Package, model *setcontext.NeutralModel, width int) ([]domain.Package, error) {
	started := time.Now()
	panel, err := anchor.Handle.SearchPanel()
	if err != nil {
		return nil, err
	}
	weights, _, err := rawPriorities(ctx, anchor.Index, panel)
	if err != nil {
		return nil, err
	}
	priorities, err := anchor.Index.ArtifactLinearPriorities(actor, weights)
	if err != nil {
		return nil, err
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
	var rows []ranked
	unsupported := 0
	selected := map[int]bool{}
	for i, pack := range feasible {
		if err := ctx.Err(); err != nil {
			return nil, err
		}
		if len(pack.Sets) == 0 || pack.Key() == anchor.Packages[actor].Key() {
			selected[i] = true
			continue
		}
		ids, _, err := anchor.Index.PackageLinearAssignment(pack, priorities, occupied)
		if err != nil {
			selected[i] = true
			continue
		}
		assignment := anchor.Score.Assignment
		assignment[actor] = ids
		packs := anchor.Packages
		packs[actor] = pack
		view, err := anchor.Index.ForPackages(packs, assignment, anchor.Index.Coordinates)
		if err != nil {
			return nil, err
		}
		dense, err := view.DenseDeltas(assignment)
		if err != nil {
			return nil, err
		}
		sets := []setcontext.Set{}
		for _, set := range pack.Sets {
			sets = append(sets, setcontext.Set{UID: set.SetUID, Count: set.Count})
		}
		target, err := anchor.Context.Replace(map[string][]setcontext.Set{anchor.Index.Wearers[actor].WearerKey: sets})
		if err != nil {
			return nil, err
		}
		score, ok, err := model.HypothesisConstantPoint(target, view.Coordinates, dense)
		if err != nil {
			return nil, err
		}
		if !ok {
			unsupported++
			// If the cheap path cannot handle this actor block, stop paying
			// for speculative setup and keep the ENTIRE original package list.
			// This may forgo a speedup; it never excludes another candidate.
			if hypothesisAdaptivePoint && len(rows) == 0 && unsupported >= 16 {
				fmt.Printf("HYPOTHESIS_POINT_SCREEN actor=%d full=%d scalar_scored=0 selected=%d bypass_after=%d seconds=%.6f\n", actor, len(feasible), len(feasible), unsupported, time.Since(started).Seconds())
				return feasible, nil
			}
			selected[i] = true
			continue
		}
		rows = append(rows, ranked{i, score})
	}
	sort.SliceStable(rows, func(i, j int) bool { return rows[i].value > rows[j].value })
	for i := 0; i < len(rows) && i < width; i++ {
		selected[rows[i].index] = true
	}
	out := make([]domain.Package, 0, len(selected))
	for i, pack := range feasible {
		if selected[i] {
			out = append(out, pack)
		}
	}
	fmt.Printf("HYPOTHESIS_POINT_SCREEN actor=%d full=%d scalar_scored=%d selected=%d width=%d seconds=%.6f\n", actor, len(feasible), len(rows), len(out), width, time.Since(started).Seconds())
	return out, nil
}

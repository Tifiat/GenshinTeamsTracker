package allsets

import (
	"context"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

// A generic reservation escape lane: every permutation of the four currently
// observed packages is considered, without guessing a shared buff's strength.
// The 24 ordering attempts resolve REAL IDs; a failed greedy allocation is
// merely an unavailable seed, never a certificate that a package is weak.
func permutedPackages(ctx context.Context, anchor Candidate) ([]contextProposal, error) {
	panel, e := anchor.Handle.SearchPanel()
	if e != nil {
		return nil, e
	}
	weights, _, e := rawPriorities(ctx, anchor.Index, panel)
	if e != nil {
		return nil, e
	}
	var priorities [4]map[int64]float64
	for actor := range priorities {
		priorities[actor], e = anchor.Index.ArtifactLinearPriorities(actor, weights)
		if e != nil {
			return nil, e
		}
	}
	out := []contextProposal{}
	seen := map[string]bool{}
	var permute func([]int, [4]bool) error
	permute = func(order []int, used [4]bool) error {
		if e := ctx.Err(); e != nil {
			return e
		}
		if len(order) < 4 {
			for i := 0; i < 4; i++ {
				if !used[i] {
					next := used
					next[i] = true
					if e := permute(append(order, i), next); e != nil {
						return e
					}
				}
			}
			return nil
		}
		var packs [4]domain.Package
		keys := []string{}
		changed := false
		for actor, from := range order {
			packs[actor] = anchor.Packages[from]
			keys = append(keys, packs[actor].Key())
			changed = changed || packs[actor].Key() != anchor.Packages[actor].Key()
		}
		key := strings.Join(keys, "|")
		if !changed || seen[key] {
			return nil
		}
		seen[key] = true
		seed, ok := teamPackageSeed(anchor.Index, packs, priorities)
		if ok {
			out = append(out, contextProposal{source: anchor, packages: packs, seed: seed, lane: "joint", wearer: -1})
		}
		return nil
	}
	e = permute(nil, [4]bool{})
	return out, e
}

func teamPackageSeed(index *domain.Index, packs [4]domain.Package, priorities [4]map[int64]float64) (domain.Assignment, bool) {
	var best domain.Assignment
	found := false
	bestScore := 0.0
	var visit func([]int, [4]bool)
	visit = func(order []int, chosen [4]bool) {
		if len(order) < 4 {
			for i := 0; i < 4; i++ {
				if !chosen[i] {
					next := chosen
					next[i] = true
					visit(append(order, i), next)
				}
			}
			return
		}
		seed := index.Incumbent
		occupied := map[int64]bool{}
		score := 0.0
		for _, actor := range order {
			// PackageSeed reserves three wearers; PackageLinearAssignment takes
			// an explicit growing reservation instead, freeing all old wearers.
			ids, _, e := index.PackageLinearAssignment(packs[actor], priorities[actor], occupied)
			if e != nil {
				return
			}
			seed[actor] = ids
			for _, id := range ids {
				occupied[id] = true
				score += priorities[actor][id]
			}
		}
		if _, e := index.ForPackages(packs, seed, index.Coordinates); e != nil {
			return
		}
		if !found || score > bestScore {
			best, bestScore, found = seed, score, true
		}
	}
	visit(nil, [4]bool{})
	return best, found
}

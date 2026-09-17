package allsets

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

type TransferProposal struct {
	Actors        [2]int            `json:"actors"`
	Packages      [4]domain.Package `json:"packages"`
	Seed          domain.Assignment `json:"seed"`
	SharedGroup   string            `json:"shared_group"`
	Priority      float64           `json:"priority_not_candidate_dps"`
	RawContextDPS float64           `json:"raw_context_dps"`
}
type TransferReport struct {
	Queue                                                                 []TransferProposal `json:"queue"`
	LinearPackages, JointSeeds, RawEvaluations, InfeasiblePairs, Unqueued int
}
type rankedPackage struct {
	pack     domain.Package
	hint     Hint
	priority float64
}

// ProposeTransfers escapes some single-wearer local optima: a source-key
// opportunity moves to another wearer while the old wearer changes package.
// Only two linear alternatives per role are combined, not all package pairs
// or physical items. Unknown/dynamic keys retain ordinary discovery lanes.
// Activation and actual DPS always require a fresh JOINT captured context.
func (g *Guide) ProposeTransfers(ctx context.Context, index *domain.Index, handle *setcontext.Handle, catalog []domain.SetCapability, limit int) (TransferReport, error) {
	var out TransferReport
	if g == nil || index == nil || handle == nil || limit < 1 || limit > 16 || g.contextKey != handle.ContextKey() || g.graphSHA != handle.GraphSHA256() {
		return out, fmt.Errorf("invalid/stale transfer guide")
	}
	_, sha, e := guideAnchor(index)
	if e != nil {
		return out, e
	}
	if sha != g.anchorSHA {
		return out, fmt.Errorf("stale transfer artifact anchor")
	}
	panel, e := handle.SearchPanel()
	if e != nil {
		return out, e
	}
	weights, _, e := rawPriorities(ctx, index, panel)
	if e != nil {
		return out, e
	}
	var packages [4]domain.Package
	var hints [4]Hint
	var priorities [4]map[int64]float64
	for i, w := range index.Wearers {
		packages[i] = domain.Package{Sets: w.SelectedSets}
		hints[i], e = packageHintFor(w.WearerKey, packages[i], g.hints)
		if e != nil {
			return out, e
		}
		priorities[i], e = index.ArtifactLinearPriorities(i, weights)
		if e != nil {
			return out, e
		}
	}
	beforeShared := sharedPeak(hints)
	all := []TransferProposal{}
	seen := map[string]bool{}
	for from := 0; from < 4; from++ {
		for to := 0; to < 4; to++ {
			if from == to {
				continue
			}
			if e = ctx.Err(); e != nil {
				return out, e
			}
			groups := []string{}
			for k, v := range hints[from].SharedGroups {
				if v > 0 && hints[to].SharedGroups[k] == 0 {
					groups = append(groups, k)
				}
			}
			sort.Strings(groups)
			if len(groups) == 0 {
				continue
			}
			occupied := map[int64]bool{}
			for actor, ids := range index.Incumbent {
				if actor != from && actor != to {
					for _, id := range ids {
						occupied[id] = true
					}
				}
			}
			feasible, e := index.FeasiblePackages(catalog, occupied)
			if e != nil {
				return out, e
			}
			actors := [2]int{from, to}
			pairWeights := [2]map[int64]float64{priorities[from], priorities[to]}
			var ranked [2][]rankedPackage
			for role, actor := range actors {
				for _, p := range feasible {
					if e = ctx.Err(); e != nil {
						return out, e
					}
					if p.Key() == packages[actor].Key() {
						continue
					}
					h, e := packageHintFor(index.Wearers[actor].WearerKey, p, g.hints)
					if e != nil {
						return out, e
					}
					linear, e := index.PackagePriority(p, priorities[actor], occupied)
					if e != nil {
						return out, e
					}
					ranked[role] = append(ranked[role], rankedPackage{pack: p, hint: h, priority: linear + h.PeakIncrement})
					out.LinearPackages++
				}
				sort.Slice(ranked[role], func(i, j int) bool {
					a, b := ranked[role][i], ranked[role][j]
					if a.priority != b.priority {
						return a.priority > b.priority
					}
					return a.pack.Key() < b.pack.Key()
				})
			}
			baseSeed, e := index.PairPackageSeed(index.Incumbent, actors, [2]domain.Package{packages[from], packages[to]}, pairWeights)
			if e != nil {
				return out, e
			}
			d, e := index.DenseDeltas(baseSeed)
			if e != nil {
				return out, e
			}
			anchorRaw, e := panel.EvaluateDPS(d)
			if e != nil {
				return out, e
			}
			out.RawEvaluations++
			for _, group := range groups {
				var short [2][]rankedPackage
				for role := 0; role < 2; role++ {
					for _, p := range ranked[role] {
						keeps := p.hint.SharedGroups[group] > 0
						if (role == 0 && keeps) || (role == 1 && !keeps) {
							continue
						}
						short[role] = append(short[role], p)
						if len(short[role]) == 2 {
							break
						}
					}
				}
				for _, a := range short[0] {
					for _, b := range short[1] {
						if e = ctx.Err(); e != nil {
							return out, e
						}
						next := packages
						next[from] = a.pack
						next[to] = b.pack
						keys := []string{}
						for _, p := range next {
							keys = append(keys, p.Key())
						}
						key := strings.Join(keys, "|")
						if seen[key] {
							continue
						}
						seen[key] = true
						seed, e := index.PairPackageSeed(index.Incumbent, actors, [2]domain.Package{a.pack, b.pack}, pairWeights)
						out.JointSeeds++
						if e != nil {
							out.InfeasiblePairs++
							continue
						}
						view, e := index.ForPackages(next, seed, index.Coordinates)
						if e != nil {
							return out, e
						}
						delta, e := view.DenseDeltas(seed)
						if e != nil {
							return out, e
						}
						raw, e := panel.EvaluateDPS(delta)
						if e != nil {
							return out, e
						}
						out.RawEvaluations++
						future := hints
						future[from] = a.hint
						future[to] = b.hint
						afterShared := sharedPeak(future)
						gain := raw - anchorRaw + a.hint.PeakIncrement + b.hint.PeakIncrement - hints[from].PeakIncrement - hints[to].PeakIncrement
						ks := map[string]bool{}
						for k := range beforeShared {
							ks[k] = true
						}
						for k := range afterShared {
							ks[k] = true
						}
						ordered := []string{}
						for k := range ks {
							ordered = append(ordered, k)
						}
						sort.Strings(ordered)
						for _, k := range ordered {
							gain += afterShared[k] - beforeShared[k]
						}
						all = append(all, TransferProposal{Actors: actors, Packages: next, Seed: seed, SharedGroup: group, Priority: gain, RawContextDPS: raw})
					}
				}
			}
		}
	}
	sort.SliceStable(all, func(i, j int) bool { return all[i].Priority > all[j].Priority })
	if len(all) > limit {
		out.Unqueued = len(all) - limit
		all = all[:limit]
	}
	out.Queue = all
	return out, nil
}

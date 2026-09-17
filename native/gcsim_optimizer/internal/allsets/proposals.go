// Package allsets orchestrates bounded set proposals over the shared scorer
// and physical domain. It is isolated from the installed Selected entrypoint.
package allsets

import (
	"context"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"sort"
	"strings"
)

// Hint is the strongest individually observed source-term opportunity, NOT a
// sum of mutually exclusive writes, a whole-set score or an upper bound.
type Hint struct {
	PeakIncrement float64
	SharedGroups  map[string]float64
	Shared        bool
	NewOutput     bool
	Unresolved    bool
}
type HintKey struct {
	Wearer, Set string
	Pieces      int
}
type Proposal struct {
	Wearer        int               `json:"wearer"`
	Package       domain.Package    `json:"package"`
	Seed          domain.Assignment `json:"seed"`
	RawContextDPS float64           `json:"raw_context_dps"`
	RawAdvantage  float64           `json:"raw_advantage_not_candidate_gain"`
	Priority      float64           `json:"priority_not_candidate_dps"`
	Hint          Hint              `json:"hint"`
	Lane          string            `json:"lane"`
}
type ProposalReport struct {
	Queue                 []Proposal `json:"queue"`
	FeasibleByWearer      [4]int     `json:"feasible_by_wearer"`
	RawFormulaEvaluations int        `json:"raw_formula_evaluations"`
	SlopeEvaluations      int        `json:"slope_evaluations"`
	Unqueued              int        `json:"unqueued"`
}

// Propose enumerates cheap SET PACKAGES, not physical item combinations. Each
// gets one legal seed from source-formula slopes and at most 3^5 slot patterns.
// The old graph is used only for its raw-stat counterfactual. Changed packages
// must subsequently resolve through setcontext before being scored as builds.
// limit includes all discovery lanes; no separate unbounded fallback queue.
func Propose(ctx context.Context, index *domain.Index, panel *evaluator.Panel, catalog []domain.SetCapability, hints map[HintKey]Hint, limit int) (ProposalReport, error) {
	var out ProposalReport
	if index == nil || panel == nil || limit < 1 || limit > 64 {
		return out, fmt.Errorf("invalid bounded proposal input")
	}
	if strings.Join(index.Coordinates, "\x00") != strings.Join(panel.Coordinates(), "\x00") {
		return out, fmt.Errorf("proposal coordinate mismatch")
	}
	var packages [4]domain.Package
	actors := panel.ActorKeys()
	if len(actors) != 4 {
		return out, fmt.Errorf("proposal requires four actors")
	}
	for i, w := range index.Wearers {
		if actors[i] != w.WearerKey {
			return out, fmt.Errorf("proposal actor order mismatch")
		}
		packages[i] = domain.Package{Sets: w.SelectedSets}
	}
	packageHint := func(actor int, p domain.Package) (Hint, error) {
		return packageHintFor(index.Wearers[actor].WearerKey, p, hints)
	}
	var currentHints [4]Hint
	for i, p := range packages {
		h, e := packageHint(i, p)
		if e != nil {
			return out, e
		}
		currentHints[i] = h
	}
	currentShared := sharedPeak(currentHints)
	weights, anchorDelta, e := rawPriorities(ctx, index, panel)
	if e != nil {
		return out, e
	}
	out.SlopeEvaluations = len(weights)
	all := []Proposal{}
	for actor := range index.Wearers {
		if _, e = panel.EvaluateDPS(anchorDelta); e != nil {
			return out, e
		} // reset other actors after slope/previous-wearer probes
		occupied := map[int64]bool{}
		for other, ids := range index.Incumbent {
			if other != actor {
				for _, id := range ids {
					occupied[id] = true
				}
			}
		}
		feasible, e := index.FeasiblePackages(catalog, occupied)
		if e != nil {
			return out, e
		}
		out.FeasibleByWearer[actor] = len(feasible)
		priority, e := index.ArtifactLinearPriorities(actor, weights)
		if e != nil {
			return out, e
		}
		anchorSeed, e := index.PackageSeed(index.Incumbent, actor, packages[actor], priority)
		if e != nil {
			return out, e
		}
		anchorDeltas, e := index.DenseDeltas(anchorSeed)
		if e != nil {
			return out, e
		}
		anchorRaw, e := panel.EvaluateDPSForActor(anchorDeltas, actor)
		if e != nil {
			return out, e
		}
		out.RawFormulaEvaluations++
		for _, p := range feasible {
			if e = ctx.Err(); e != nil {
				return out, e
			}
			if p.Key() == packages[actor].Key() {
				continue
			} // incumbent is retained separately, without recapture
			seed, e := index.PackageSeed(index.Incumbent, actor, p, priority)
			if e != nil {
				return out, e
			}
			next := packages
			next[actor] = p
			view, e := index.ForPackages(next, seed, index.Coordinates)
			if e != nil {
				return out, e
			}
			d, e := view.DenseDeltas(seed)
			if e != nil {
				return out, e
			}
			raw, e := panel.EvaluateDPSForActor(d, actor)
			if e != nil {
				return out, e
			}
			out.RawFormulaEvaluations++
			hint, e := packageHint(actor, p)
			if e != nil {
				return out, e
			}
			prospective := currentHints
			prospective[actor] = hint
			sharedAfter := sharedPeak(prospective)
			gain := raw - anchorRaw + hint.PeakIncrement - currentHints[actor].PeakIncrement
			keys := map[string]bool{}
			for k := range currentShared {
				keys[k] = true
			}
			for k := range sharedAfter {
				keys[k] = true
			}
			ordered := []string{}
			for k := range keys {
				ordered = append(ordered, k)
			}
			sort.Strings(ordered)
			for _, k := range ordered {
				gain += sharedAfter[k] - currentShared[k]
			}
			all = append(all, Proposal{Wearer: actor, Package: p, Seed: seed, RawContextDPS: raw, RawAdvantage: raw - anchorRaw, Priority: gain, Hint: hint})
		}
	}
	// Global order is deterministic. Reserve breadth across wearers, then effect
	// families and unknown/new-output routes; fill remaining places by priority.
	sort.Slice(all, func(i, j int) bool {
		if all[i].Priority != all[j].Priority {
			return all[i].Priority > all[j].Priority
		}
		if all[i].Wearer != all[j].Wearer {
			return all[i].Wearer < all[j].Wearer
		}
		return all[i].Package.Key() < all[j].Package.Key()
	})
	used := map[int]bool{}
	take := func(lane string, accept func(Proposal) bool) {
		if len(out.Queue) >= limit {
			return
		}
		for i, p := range all {
			if !used[i] && accept(p) {
				used[i] = true
				p.Lane = lane
				out.Queue = append(out.Queue, p)
				return
			}
		}
	}
	for actor := 0; actor < 4; actor++ {
		a := actor
		take("wearer", func(p Proposal) bool { return p.Wearer == a })
	}
	take("shared_effect", func(p Proposal) bool { return p.Hint.Shared })
	take("new_output", func(p Proposal) bool { return p.Hint.NewOutput })
	take("unresolved", func(p Proposal) bool { return p.Hint.Unresolved })
	for len(out.Queue) < limit && len(out.Queue) < len(all) {
		// Repeated best alternatives of one wearer cannot consume every place
		// before other wearers get a second package. Uneven pools use remaining
		// budget naturally; there is still a single global limit.
		for actor := 0; actor < 4; actor++ {
			a := actor
			take("wearer_diversity", func(p Proposal) bool { return p.Wearer == a })
		}
	}
	out.Unqueued = len(all) - len(out.Queue)
	return out, nil
}

package allsets

import (
	"context"
	"fmt"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

// TheoryProposal ranks set packages without requiring owned pieces. It is a
// source/formula shortlist for farming guidance, never a physical feasibility
// result or a hard-prune proof.
type TheoryProposal struct {
	Wearer   int            `json:"wearer"`
	Package  domain.Package `json:"package"`
	Priority float64        `json:"priority_not_candidate_dps"`
	Hint     Hint           `json:"hint"`
	Lane     string         `json:"lane"`
}

type TheoryProposalReport struct {
	Queue              []TheoryProposal `json:"queue"`
	PackagesConsidered int              `json:"packages_considered"`
	Unqueued           int              `json:"unqueued"`
}

// ProposeTheory considers every source-supported 4p and distinct 2+2 package.
// It deliberately does not inspect account inventory. Expensive fresh formula
// capture remains bounded by the caller and validates only the shortlist.
func (g *Guide) ProposeTheory(ctx context.Context, index *domain.Index, handle *setcontext.Handle, catalog []domain.SetCapability, limit int) (TheoryProposalReport, error) {
	var out TheoryProposalReport
	if g == nil || index == nil || handle == nil || limit < 1 || limit > 64 || g.contextKey != handle.ContextKey() || g.graphSHA != handle.GraphSHA256() {
		return out, fmt.Errorf("invalid or stale theory set guide")
	}
	_, anchorSHA, err := guideAnchor(index)
	if err != nil {
		return out, err
	}
	if anchorSHA != g.anchorSHA {
		return out, fmt.Errorf("stale theory guide artifact anchor")
	}
	packages, err := theoreticalPackages(catalog)
	if err != nil {
		return out, err
	}
	var current [4]domain.Package
	var currentHints [4]Hint
	for actor, wearer := range index.Wearers {
		current[actor] = domain.Package{Sets: wearer.SelectedSets}
		currentHints[actor], err = packageHintFor(wearer.WearerKey, current[actor], g.hints)
		if err != nil {
			return out, err
		}
	}
	currentShared := sharedPeak(currentHints)
	all := make([]TheoryProposal, 0, len(packages)*4)
	for actor, wearer := range index.Wearers {
		for _, candidate := range packages {
			if err = ctx.Err(); err != nil {
				return out, err
			}
			if candidate.Key() == current[actor].Key() {
				continue
			}
			hint, hintErr := packageHintFor(wearer.WearerKey, candidate, g.hints)
			if hintErr != nil {
				return out, hintErr
			}
			prospective := currentHints
			prospective[actor] = hint
			nextShared := sharedPeak(prospective)
			priority := hint.PeakIncrement - currentHints[actor].PeakIncrement
			keys := map[string]bool{}
			for key := range currentShared {
				keys[key] = true
			}
			for key := range nextShared {
				keys[key] = true
			}
			for key := range keys {
				priority += nextShared[key] - currentShared[key]
			}
			all = append(all, TheoryProposal{Wearer: actor, Package: candidate, Priority: priority, Hint: hint})
		}
	}
	out.PackagesConsidered = len(all)
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
	take := func(lane string, accept func(TheoryProposal) bool) {
		if len(out.Queue) >= limit {
			return
		}
		for i, row := range all {
			if !used[i] && accept(row) {
				used[i] = true
				row.Lane = lane
				out.Queue = append(out.Queue, row)
				return
			}
		}
	}
	for actor := 0; actor < 4; actor++ {
		a := actor
		take("wearer", func(row TheoryProposal) bool { return row.Wearer == a })
	}
	take("shared_effect", func(row TheoryProposal) bool { return row.Hint.Shared })
	take("new_output", func(row TheoryProposal) bool { return row.Hint.NewOutput })
	take("unresolved", func(row TheoryProposal) bool { return row.Hint.Unresolved })
	for len(out.Queue) < limit && len(out.Queue) < len(all) {
		for actor := 0; actor < 4; actor++ {
			a := actor
			take("wearer_diversity", func(row TheoryProposal) bool { return row.Wearer == a })
		}
	}
	out.Unqueued = len(all) - len(out.Queue)
	return out, nil
}

func theoreticalPackages(catalog []domain.SetCapability) ([]domain.Package, error) {
	seen := map[string]bool{}
	var four []domain.Package
	var pairs []string
	for _, set := range catalog {
		if set.UID == "" || seen[set.UID] || (!set.TwoPiece && set.FourPiece) {
			return nil, fmt.Errorf("invalid or duplicate theory set capability")
		}
		seen[set.UID] = true
		if set.FourPiece {
			four = append(four, domain.Package{Sets: []contracts.SetRequirement{{SetUID: set.UID, Count: 4}}})
		}
		if set.TwoPiece {
			pairs = append(pairs, set.UID)
		}
	}
	sort.Strings(pairs)
	out := append([]domain.Package(nil), four...)
	for i, left := range pairs {
		for _, right := range pairs[i+1:] {
			out = append(out, domain.Package{Sets: []contracts.SetRequirement{{SetUID: left, Count: 2}, {SetUID: right, Count: 2}}})
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].Key() < out[j].Key() })
	return out, nil
}

package allsets

import (
	"context"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

type RefinedProposal struct {
	Proposal Proposal
	Context  *setcontext.Context
	Step     search.ActorStep
}

// Refine resolves every shortlisted package BEFORE passing its graph to the
// existing artifact solver. The caller owns the single capture/time budget;
// this function cannot simulate, retry or create a second budget itself.
// Results remain formula candidates until ordinary finalist verification.
func Refine(ctx context.Context, index *domain.Index, base *setcontext.Context, baseline *setcontext.Handle, session *setcontext.Session, queue []Proposal, cfg search.Config) ([]RefinedProposal, error) {
	if index == nil || base == nil || baseline == nil || session == nil {
		return nil, fmt.Errorf("missing set-search context")
	}
	rows := []RefinedProposal{}
	seen := map[string]bool{}
	for _, p := range queue {
		if e := ctx.Err(); e != nil {
			return rows, e
		}
		if p.Wearer < 0 || p.Wearer >= 4 {
			return rows, fmt.Errorf("proposal actor outside team")
		}
		key := fmt.Sprint(p.Wearer) + "/" + p.Package.Key()
		if seen[key] {
			return rows, fmt.Errorf("duplicate proposal")
		}
		seen[key] = true
		var packages [4]domain.Package
		for i, w := range index.Wearers {
			packages[i] = domain.Package{Sets: w.SelectedSets}
			if i != p.Wearer && p.Seed[i] != index.Incumbent[i] {
				return rows, fmt.Errorf("single-wearer proposal changes reserved items")
			}
		}
		packages[p.Wearer] = p.Package
		view, e := index.ForPackages(packages, p.Seed, index.Coordinates)
		if e != nil {
			return rows, e
		}
		counts, e := view.SelectedSetCounts(p.Seed)
		if e != nil {
			return rows, e
		}
		changes := []setcontext.Set{}
		for _, s := range counts[p.Wearer] {
			changes = append(changes, setcontext.Set{UID: s.SetUID, Count: s.Count})
		}
		target, e := base.Replace(map[string][]setcontext.Set{index.Wearers[p.Wearer].WearerKey: changes})
		if e != nil {
			return rows, e
		}
		handle, e := session.Resolve(ctx, target, baseline, nil)
		if e != nil {
			return rows, e
		}
		panel, e := handle.SearchPanel()
		if e != nil {
			return rows, e
		}
		view, e = index.ForPackages(packages, p.Seed, panel.Coordinates())
		if e != nil {
			return rows, e
		}
		solver, e := search.New(view, panel, cfg)
		if e != nil {
			return rows, e
		}
		step, e := solver.RefineWearer(ctx, p.Seed, p.Wearer)
		if e != nil {
			return rows, e
		}
		rows = append(rows, RefinedProposal{p, target, step})
	}
	return rows, nil
}

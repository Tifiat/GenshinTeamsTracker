package allsets

import (
	"context"
	"fmt"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

type RefinedTransfer struct {
	Proposal TransferProposal
	Context  *setcontext.Context
	Handle   *setcontext.Handle
	Result   search.Result
}

// Both package changes form ONE context and spend from the same caller-owned
// capture budget/deadline as single-wearer proposals. No sequential reuse of
// a half-changed graph and no gameplay bonus manually carried to the new holder.
func RefineTransfers(ctx context.Context, index *domain.Index, base *setcontext.Context, baseline *setcontext.Handle, session *setcontext.Session, queue []TransferProposal, cfg search.Config) ([]RefinedTransfer, error) {
	rows := []RefinedTransfer{}
	if index == nil || base == nil || baseline == nil || session == nil {
		return rows, fmt.Errorf("missing joint refinement context")
	}
	seen := map[string]bool{}
	for _, p := range queue {
		if e := ctx.Err(); e != nil {
			return rows, e
		}
		from, to := p.Actors[0], p.Actors[1]
		if from < 0 || from >= 4 || to < 0 || to >= 4 || from == to {
			return rows, fmt.Errorf("invalid transfer actors")
		}
		keys := []string{}
		for i, w := range index.Wearers {
			keys = append(keys, p.Packages[i].Key())
			if i != from && i != to && (p.Seed[i] != index.Incumbent[i] || p.Packages[i].Key() != (domain.Package{Sets: w.SelectedSets}).Key()) {
				return rows, fmt.Errorf("joint proposal changes reserved wearer")
			}
		}
		key := strings.Join(keys, "|")
		if seen[key] {
			return rows, fmt.Errorf("duplicate joint package proposal")
		}
		seen[key] = true
		view, e := index.ForPackages(p.Packages, p.Seed, index.Coordinates)
		if e != nil {
			return rows, e
		}
		counts, e := view.SelectedSetCounts(p.Seed)
		if e != nil {
			return rows, e
		}
		changes := map[string][]setcontext.Set{}
		for _, actor := range p.Actors {
			for _, s := range counts[actor] {
				key := index.Wearers[actor].WearerKey
				changes[key] = append(changes[key], setcontext.Set{UID: s.SetUID, Count: s.Count})
			}
		}
		target, e := base.Replace(changes)
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
		view, e = index.ForPackages(p.Packages, p.Seed, panel.Coordinates())
		if e != nil {
			return rows, e
		}
		solver, e := search.New(view, panel, cfg)
		if e != nil {
			return rows, e
		}
		result, e := solver.Run(ctx)
		if e != nil {
			return rows, e
		}
		rows = append(rows, RefinedTransfer{Proposal: p, Context: target, Handle: handle, Result: result})
	}
	return rows, nil
}

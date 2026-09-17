package allsets

import (
	"context"
	"errors"
	"fmt"
	"math"
	"sort"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

// Limits are supplied once by the outer run, never renewed per package. Product
// defaults remain gated by the combined account benchmark and finalist budget.
type CoordinatorConfig struct {
	MaxContexts, MaxGuides, SingleQueue, TransferQueue, FinalistLimit int
	MaxSearchExpansions                                               int
	SearchTime                                                        time.Duration
	Search                                                            search.Config
}

// Candidate retains its OWN complete context/domain. Its graph's raw-stat
// reference is unchanged; a different set package cannot inherit this DPS.
type Candidate struct {
	Score    search.ScoredAssignment
	Context  *setcontext.Context
	Handle   *setcontext.Handle
	Index    *domain.Index
	Packages [4]domain.Package
}

type ContextWork struct {
	ContextSHA256                 string  `json:"context_sha256"`
	Lane                          string  `json:"lane"`
	FormulaDPS                    float64 `json:"formula_dps"`
	CaptureSeconds, SearchSeconds float64
	Expansions                    int
}

type CoordinatorResult struct {
	Initial, Selected, Leader                                                             Candidate
	Finalists                                                                             []Candidate
	Work                                                                                  []ContextWork
	Guides, Queued, Unqueued, SkippedDuplicate, Pending, CaptureMembers, SearchExpansions int
	GuideSeconds, ProposalSeconds, TotalSeconds                                           float64
	StopReason                                                                            string
	Boundaries                                                                            []string
}

type contextProposal struct {
	source   Candidate
	packages [4]domain.Package
	seed     domain.Assignment
	lane     string
	wearer   int
	hint     Hint
	consumed bool
}

// Run captures at most MaxContexts complete panels, preserves the initial and
// Selected candidates, and applies the same FGBS arithmetic inside each panel.
// A deadline/budget ends discovery visibly with completed results intact.
// Provenance/engine errors remain errors, not successful unknown mechanics.
func Run(ctx context.Context, index *domain.Index, base *setcontext.Context, sources *seteffects.SourceCatalog, provider setcontext.CaptureProvider, cfg CoordinatorConfig) (out CoordinatorResult, err error) {
	if index == nil || base == nil || sources == nil || provider == nil || cfg.MaxContexts < 1 || cfg.MaxContexts > 32 || cfg.MaxGuides < 1 || cfg.MaxGuides > cfg.MaxContexts || cfg.SingleQueue < 1 || cfg.SingleQueue > 64 || cfg.TransferQueue < 1 || cfg.TransferQueue > 16 || cfg.FinalistLimit < 3 || cfg.FinalistLimit > 32 || cfg.MaxSearchExpansions < 1 || cfg.SearchTime <= 0 {
		return out, fmt.Errorf("invalid bounded All Sets coordinator configuration")
	}
	started := time.Now()
	runCtx, cancel := context.WithTimeout(ctx, cfg.SearchTime)
	defer cancel()
	session, e := setcontext.NewSession(provider, cfg.MaxContexts*len(base.Seeds()))
	if e != nil {
		return out, e
	}
	pool := []Candidate{}
	pending := []contextProposal{}
	seen := map[string]bool{}
	defer func() {
		out.TotalSeconds = time.Since(started).Seconds()
		out.CaptureMembers = session.AttemptedCaptureMembers()
		for _, p := range pending {
			if !p.consumed {
				out.Pending++
			}
		}
		out.Finalists = chooseFinalists(pool, out.Initial, out.Selected, cfg.FinalistLimit)
		if len(out.Finalists) > 0 {
			out.Leader = out.Finalists[0]
		}
	}()
	stop := func(e error) error {
		if ctx.Err() != nil {
			return ctx.Err()
		}
		if errors.Is(e, context.DeadlineExceeded) || errors.Is(e, context.Canceled) {
			out.StopReason = "search_deadline"
			return nil
		}
		return e
	}
	var packages [4]domain.Package
	for i, w := range index.Wearers {
		packages[i] = domain.Package{Sets: w.SelectedSets}
	}
	captureStart := time.Now()
	handle, e := session.Resolve(runCtx, base, nil, nil)
	captureSeconds := time.Since(captureStart).Seconds()
	if e != nil {
		return out, e
	}
	panel, e := handle.SearchPanel()
	if e != nil {
		return out, e
	}
	index, e = index.ForPackages(packages, index.Incumbent, panel.Coordinates())
	if e != nil {
		return out, e
	}
	dense, e := index.DenseDeltas(index.Incumbent)
	if e != nil {
		return out, e
	}
	initialDPS, e := panel.EvaluateDPS(dense)
	if e != nil {
		return out, e
	}
	initial := Candidate{search.ScoredAssignment{Assignment: index.Incumbent, DPS: initialDPS, Source: "all_initial"}, base, handle, index, packages}
	out.Initial, out.Selected, out.Leader = initial, initial, initial
	pool = append(pool, initial)
	seen[base.Key()] = true
	catalog := []domain.SetCapability{}
	for _, s := range sources.Sets {
		catalog = append(catalog, domain.SetCapability{UID: s.Key, TwoPiece: true, FourPiece: s.FourPieceModeled})
	}
	refine := func(seed Candidate, lane string, captureSeconds float64) (Candidate, error) {
		remaining := cfg.MaxSearchExpansions - out.SearchExpansions
		sc := cfg.Search
		if sc.MaxCycles <= 0 {
			return seed, fmt.Errorf("invalid search cycles")
		}
		if allowed := remaining / (4 * sc.MaxCycles); allowed < sc.MaxExpandedPerActor {
			sc.MaxExpandedPerActor = allowed
		}
		if sc.MaxExpandedPerActor <= 0 {
			out.StopReason = "search_expansion_budget"
			return seed, nil
		}
		p, e := seed.Handle.SearchPanel()
		if e != nil {
			return seed, e
		}
		solver, e := search.New(seed.Index, p, sc)
		if e != nil {
			return seed, e
		}
		reserved := 4 * sc.MaxCycles * sc.MaxExpandedPerActor
		out.SearchExpansions += reserved // failed/cancelled work cannot silently refund its allowance
		start := time.Now()
		result, e := solver.Run(runCtx)
		elapsed := time.Since(start).Seconds()
		if e != nil {
			return seed, e
		}
		actual := 0
		for _, step := range result.Steps {
			actual += step.Expanded
		}
		if actual > reserved {
			return seed, fmt.Errorf("artifact solver exceeded reserved expansion budget")
		}
		out.SearchExpansions -= reserved - actual
		best := seed
		best.Score = result.Leader
		best.Index, e = seed.Index.ForPackages(seed.Packages, result.Leader.Assignment, p.Coordinates())
		if e != nil {
			return seed, e
		}
		for _, score := range result.Finalists {
			candidate := best
			candidate.Score = score
			pool = append(pool, candidate)
		}
		pool = append(pool, best)
		out.Work = append(out.Work, ContextWork{seed.Context.Key(), lane, best.Score.DPS, captureSeconds, elapsed, actual})
		return best, nil
	}
	selected, e := refine(initial, "selected", captureSeconds)
	if e != nil {
		return out, stop(e)
	}
	out.Selected, out.Leader = selected, selected
	if out.StopReason != "" {
		return out, nil
	}
	queue := func(anchor Candidate) error {
		begin := time.Now()
		guide, e := BuildGuide(runCtx, anchor.Index, anchor.Handle, sources)
		out.GuideSeconds += time.Since(begin).Seconds()
		if e != nil {
			return e
		}
		out.Guides++
		out.Boundaries = append(out.Boundaries, guide.Boundaries...)
		begin = time.Now()
		single, e := guide.Propose(runCtx, anchor.Index, anchor.Handle, catalog, cfg.SingleQueue)
		if e != nil {
			return e
		}
		joint, e := guide.ProposeTransfers(runCtx, anchor.Index, anchor.Handle, catalog, cfg.TransferQueue)
		out.ProposalSeconds += time.Since(begin).Seconds()
		if e != nil {
			return e
		}
		batch := []contextProposal{}
		for _, p := range single.Queue {
			packs := anchor.Packages
			packs[p.Wearer] = p.Package
			batch = append(batch, contextProposal{source: anchor, packages: packs, seed: p.Seed, lane: p.Lane, wearer: p.Wearer, hint: p.Hint})
		}
		for _, p := range joint.Queue {
			batch = append(batch, contextProposal{source: anchor, packages: p.Packages, seed: p.Seed, lane: "joint", wearer: -1})
		}
		out.Queued += len(batch)
		out.Unqueued += single.Unqueued + joint.Unqueued
		pending = append(batch, pending...)
		return nil
	}
	if e = queue(selected); e != nil {
		return out, stop(e)
	}
	cursor, wearer := 0, 0
	for {
		if e = runCtx.Err(); e != nil {
			return out, stop(e)
		}
		if len(seen) >= cfg.MaxContexts {
			out.StopReason = "context_budget"
			return out, nil
		}
		if out.SearchExpansions >= cfg.MaxSearchExpansions {
			out.StopReason = "search_expansion_budget"
			return out, nil
		}
		n := pickProposal(pending, &cursor, &wearer)
		if n < 0 {
			out.StopReason = "proposal_queue_exhausted"
			return out, nil
		}
		pending[n].consumed = true
		p := pending[n]
		view, e := p.source.Index.ForPackages(p.packages, p.seed, p.source.Index.Coordinates)
		if e != nil {
			return out, e
		}
		counts, e := view.SelectedSetCounts(p.seed)
		if e != nil {
			return out, e
		}
		changes := map[string][]setcontext.Set{}
		for actor, w := range view.Wearers {
			if p.packages[actor].Key() == p.source.Packages[actor].Key() {
				continue
			}
			for _, s := range counts[actor] {
				changes[w.WearerKey] = append(changes[w.WearerKey], setcontext.Set{UID: s.SetUID, Count: s.Count})
			}
		}
		target, e := p.source.Context.Replace(changes)
		if e != nil {
			return out, e
		}
		if seen[target.Key()] {
			out.SkippedDuplicate++
			continue
		}
		seen[target.Key()] = true
		begin := time.Now()
		h, e := session.Resolve(runCtx, target, p.source.Handle, nil)
		captureSeconds = time.Since(begin).Seconds()
		if e != nil {
			return out, stop(e)
		}
		panel, e := h.SearchPanel()
		if e != nil {
			return out, e
		}
		view, e = view.ForPackages(p.packages, p.seed, panel.Coordinates())
		if e != nil {
			return out, e
		}
		delta, e := view.DenseDeltas(p.seed)
		if e != nil {
			return out, e
		}
		dps, e := panel.EvaluateDPS(delta)
		if e != nil {
			return out, e
		}
		seed := Candidate{search.ScoredAssignment{Assignment: p.seed, DPS: dps, Source: "all_" + p.lane}, target, h, view, p.packages}
		pool = append(pool, seed)
		candidate, e := refine(seed, p.lane, captureSeconds)
		if e != nil {
			return out, stop(e)
		}
		if candidate.Score.DPS > out.Leader.Score.DPS {
			out.Leader = candidate
			if out.Guides < cfg.MaxGuides && len(seen) < cfg.MaxContexts && out.StopReason == "" {
				if e = queue(candidate); e != nil {
					return out, stop(e)
				}
			}
		}
		if out.StopReason != "" {
			return out, nil
		}
	}
}

// Fairness is shared across refreshes. Unknown/new-output opportunities are
// explicitly scheduled, not silently discarded by a raw-stat score threshold.
func pickProposal(pending []contextProposal, cursor, wearer *int) int {
	lanes := []string{"joint", "wearer", "wearer", "joint", "wearer", "wearer", "shared", "new_output", "unresolved", "rest"}
	for attempt := 0; attempt < len(lanes); attempt++ {
		lane := lanes[*cursor%len(lanes)]
		*cursor++
		for i, p := range pending {
			if p.consumed {
				continue
			}
			match := lane == "rest" || lane == "joint" && p.lane == "joint" || lane == "wearer" && p.wearer == *wearer || lane == "shared" && p.hint.Shared || lane == "new_output" && p.hint.NewOutput || lane == "unresolved" && p.hint.Unresolved
			if match {
				if lane == "wearer" {
					*wearer = (*wearer + 1) % 4
				}
				return i
			}
		}
		if lane == "wearer" {
			*wearer = (*wearer + 1) % 4
		}
	}
	return -1
}

func chooseFinalists(pool []Candidate, initial, selected Candidate, limit int) []Candidate {
	unique := map[domain.Assignment]Candidate{}
	for _, c := range pool {
		if c.Context == nil || math.IsNaN(c.Score.DPS) || math.IsInf(c.Score.DPS, 0) {
			continue
		}
		old, ok := unique[c.Score.Assignment]
		if !ok || c.Score.DPS > old.Score.DPS {
			unique[c.Score.Assignment] = c
		}
	}
	ordered := []Candidate{}
	for _, c := range unique {
		ordered = append(ordered, c)
	}
	sort.Slice(ordered, func(i, j int) bool {
		if ordered[i].Score.DPS != ordered[j].Score.DPS {
			return ordered[i].Score.DPS > ordered[j].Score.DPS
		}
		return fmt.Sprint(ordered[i].Score.Assignment) < fmt.Sprint(ordered[j].Score.Assignment)
	})
	result := []Candidate{}
	used := map[domain.Assignment]bool{}
	take := func(c Candidate) {
		if c.Context != nil && !used[c.Score.Assignment] && len(result) < limit {
			used[c.Score.Assignment] = true
			result = append(result, c)
		}
	}
	// Retain the two baseline anchors, then breadth across observed contexts,
	// then formula rank. No hint priority ever becomes a finalist's DPS.
	if len(ordered) > 0 {
		take(ordered[0])
	}
	take(selected)
	take(initial)
	contexts := map[string]bool{}
	for _, c := range result {
		contexts[c.Context.Key()] = true
	}
	for _, c := range ordered {
		if !contexts[c.Context.Key()] {
			take(c)
			contexts[c.Context.Key()] = true
		}
	}
	for _, c := range ordered {
		take(c)
	}
	sort.SliceStable(result, func(i, j int) bool { return result[i].Score.DPS > result[j].Score.DPS })
	return result
}

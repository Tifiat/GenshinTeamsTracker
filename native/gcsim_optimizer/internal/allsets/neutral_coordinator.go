package allsets

// Neutral-capable infinite-energy All Sets coordinator (trace handoff section 2).
// ONE neutral schedule panel supplies every ordinary package model. The product
// entrypoint retains the legacy route for finite energy and older engines.
// Unknown APIs/schedule changes are visible unmodeled work, never bonus zero.
// Finite-energy integration must bind effect inputs to its ledger separately;
// borrowing the neutral ledger as if it contained new ER bonuses is forbidden.
import (
	"container/heap"
	"context"
	"errors"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/searchcontrol"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
	"math"
	"sort"
	"strings"
	"time"
)

// Counts describe a coordinate pass, not proof of a global joint optimum.
// Prepared includes failed source models and reserved-ID conflicts; queued
// means a complete real candidates were scored; not a bound or optimality certificate.
type NeutralCycleCoverage struct {
	Cycle, Total, Prepared, ModelUnavailable, ReservationDeferred int
	Queued, Processed, NotPrepared, NotProcessed                  int
	// Explicit heuristic deferrals remain unresolved, NEVER proved dominated.
	ModelDeferred             int
	Sampled, HeuristicSkipped int
}

// scheduleContextRouter keeps source-approved neutral contexts on the reduced
// model and gives known or observed schedule changes an exact, run-local capture.
// The fresh cache is keyed by the complete setcontext identity, never by set UID.
type scheduleContextRouter struct {
	sources    *seteffects.SourceCatalog
	model      neutralContextResolver
	captures   *setcontext.Session
	maxMembers int
	attempts   map[string]scheduleCaptureOutcome
	onCapture  func(string)
}

type neutralContextResolver interface {
	Resolve(*setcontext.Context) (*setcontext.Handle, []string, error)
}

type scheduleCaptureOutcome struct {
	handle     *setcontext.Handle
	boundaries []string
}

func (r *scheduleContextRouter) Resolve(ctx context.Context, target *setcontext.Context) (*setcontext.Handle, []string, error) {
	key := target.Key()
	if prior, ok := r.attempts[key]; ok {
		if prior.handle != nil {
			handle, err := r.captures.Resolve(ctx, target, nil, nil)
			return handle, nil, err
		}
		return nil, append([]string(nil), prior.boundaries...), nil
	}
	potential, sourceReasons := r.sources.RequiresScheduleCapture(contextRuleChoices(target))
	if r.model == nil {
		if potential {
			return r.capture(ctx, target, sourceReasons)
		}
		return nil, []string{"neutral_model_unavailable"}, nil
	}
	handle, boundaries, err := r.model.Resolve(target)
	if err != nil || handle != nil || (!potential && !hasScheduleChangeBoundary(boundaries)) {
		return handle, boundaries, err
	}
	// Source metadata explains which selected rule contains a potential hazard.
	// A successful neutral resolution always wins; static potential is only a
	// fallback when no neutral handle can be produced. An observed active
	// schedule_change boundary also routes this complete context to fresh capture.
	reasons := append(append([]string(nil), boundaries...), sourceReasons...)
	return r.capture(ctx, target, reasons)
}

func (r *scheduleContextRouter) capture(ctx context.Context, target *setcontext.Context, reasons []string) (*setcontext.Handle, []string, error) {
	key := target.Key()
	if r.captures.AttemptedCaptureMembers()+len(target.Seeds()) > r.maxMembers {
		boundaries := append([]string(nil), reasons...)
		boundaries = append(boundaries, "schedule_capture_context_budget_exhausted:"+key)
		r.attempts[key] = scheduleCaptureOutcome{boundaries: boundaries}
		r.recordCaptureBoundaries(boundaries)
		return nil, boundaries, nil
	}
	handle, err := r.captures.Resolve(ctx, target, nil, nil)
	if err != nil {
		if ctx.Err() != nil {
			return nil, nil, ctx.Err()
		}
		failure := strings.NewReplacer("\r", " ", "\n", " ").Replace(strings.TrimSpace(err.Error()))
		boundaries := append(append([]string(nil), reasons...), "schedule_capture_failed:"+key+":"+failure)
		r.attempts[key] = scheduleCaptureOutcome{boundaries: boundaries}
		r.recordCaptureBoundaries(boundaries)
		return nil, boundaries, nil
	}
	boundaries := append(append([]string(nil), reasons...), "schedule_capture_changed_item_timing_unverified:"+key)
	r.attempts[key] = scheduleCaptureOutcome{handle: handle, boundaries: boundaries}
	r.recordCaptureBoundaries(boundaries)
	return handle, nil, nil
}

func (r *scheduleContextRouter) recordCaptureBoundaries(boundaries []string) {
	if r.onCapture == nil {
		return
	}
	for _, boundary := range boundaries {
		r.onCapture(boundary)
	}
}

func contextRuleChoices(target *setcontext.Context) []seteffects.RuleChoice {
	if target == nil {
		return nil
	}
	actors := target.Actors()
	choices := []seteffects.RuleChoice{}
	for owner, actor := range actors {
		for _, set := range target.Sets(actor) {
			choices = append(choices, seteffects.RuleChoice{Owner: owner, Key: set.UID, Pieces: set.Count})
		}
	}
	return choices
}

func hasScheduleChangeBoundary(boundaries []string) bool {
	for _, boundary := range boundaries {
		if strings.Contains(boundary, "schedule_change:") {
			return true
		}
	}
	return false
}

func scheduleCaptureContextLimit(configured int) int {
	if configured <= 0 {
		return 1
	}
	if configured > 64 {
		return 64
	}
	return configured
}

// Zero SearchTime is the product no-deadline policy. Caller cancellation,
// cooperative finish, configured cycles and work limits remain in force.
func RunNeutral(ctx context.Context, index *domain.Index, base *setcontext.Context, sources *seteffects.SourceCatalog, provider setcontext.CaptureProvider, cfg CoordinatorConfig) (out CoordinatorResult, err error) {
	if index == nil || base == nil || sources == nil || provider == nil || cfg.SearchTime < 0 || cfg.MaxSearchExpansions <= 0 || cfg.FinalistLimit < 3 || cfg.Search.MaxCycles < 1 {
		return out, fmt.Errorf("invalid neutral All Sets configuration")
	}
	infinite, err := setcontext.IgnoreBurstEnergy(base.Config())
	if err != nil {
		return out, err
	}
	if !infinite {
		return out, fmt.Errorf("neutral finite-energy effect/ledger binding is not implemented")
	}
	for _, w := range index.Wearers {
		for _, s := range base.Sets(w.WearerKey) {
			if strings.TrimSpace(s.Parameters) != "" {
				return out, fmt.Errorf("neutral source parameters are not yet bound: %s/%s", w.WearerKey, s.UID)
			}
		}
	}
	started := time.Now()
	runCtx, cancel := context.WithCancel(ctx)
	if cfg.SearchTime > 0 {
		cancel()
		runCtx, cancel = context.WithTimeout(ctx, cfg.SearchTime)
	}
	defer cancel()
	hydrateCtx := runCtx
	pool := []Candidate{}
	var packageTeams []Candidate
	var packageChoices [4][]packageChoice
	var stabilizedFinalists []Candidate
	archive := newResultArchive(max(1, cfg.ResultAlternatives))
	// Core stabilization uses each group's best scored representative. Keep it
	// independent of the result archive's display alternative count.
	coreArchive := newResultArchive(1)
	var hydrate func(Candidate) (Candidate, error)
	boundaries := map[string]bool{}
	neutralCaptureMembers := 0
	var scheduleCaptureSession *setcontext.Session
	var proposalStarted time.Time
	defer func() {
		if !proposalStarted.IsZero() {
			out.ProposalSeconds += time.Since(proposalStarted).Seconds()
		}
		out.TotalSeconds = time.Since(started).Seconds()
		out.Pending = 0
		for i := range out.NeutralCycles {
			coverage := &out.NeutralCycles[i]
			coverage.NotPrepared = coverage.Total - coverage.Prepared
			coverage.NotProcessed = coverage.Queued - coverage.Processed - coverage.ModelDeferred
			out.Pending += coverage.NotPrepared + coverage.NotProcessed + coverage.ModelDeferred
		}
		finalPool := pool
		if stabilizedFinalists != nil {
			finalPool = stabilizedFinalists
		}
		out.Finalists = chooseFinalists(finalPool, cfg.FinalistLimit)
		if cfg.ResultGroups > 0 {
			out.Finalists = archive.top(cfg.ResultGroups)
			if searchcontrol.Requested(ctx) {
				hydrateCtx = searchcontrol.FinalizationContext(ctx)
			}
			for i, c := range out.Finalists {
				if hydrate == nil {
					break
				}
				bound, e := hydrate(c)
				if e != nil {
					err = e
					out.Finalists = nil
					break
				}
				out.Finalists[i] = bound
			}
		}
		if len(out.Finalists) > 0 {
			out.Leader = out.Finalists[0]
		}
		for code := range boundaries {
			out.Boundaries = append(out.Boundaries, code)
		}
		sort.Strings(out.Boundaries)
		out.CaptureMembers = neutralCaptureMembers
		if scheduleCaptureSession != nil {
			out.CaptureMembers += scheduleCaptureSession.AttemptedCaptureMembers()
		}
		if errors.Is(err, context.DeadlineExceeded) && ctx.Err() == nil && out.Initial.Index != nil {
			out.StopReason = "search_deadline"
			err = nil
		}
	}()
	changes := map[string][]setcontext.Set{}
	for _, w := range index.Wearers {
		changes[w.WearerKey] = nil
	}
	neutral, err := base.Replace(changes)
	if err != nil {
		return out, err
	}
	session, err := setcontext.NewSession(provider, len(base.Seeds()))
	if err != nil {
		return out, err
	}
	captureStarted := time.Now()
	if cfg.Progress != nil {
		cfg.Progress("capturing_schedule", 0, len(base.Seeds()))
	}
	captured, err := session.Resolve(runCtx, neutral, nil, nil)
	neutralCaptureMembers = session.AttemptedCaptureMembers()
	if err != nil {
		return out, err
	}
	model, err := setcontext.NewNeutralModel(captured, sources)
	if err != nil {
		return out, err
	}
	captureContextsLimit := scheduleCaptureContextLimit(cfg.MaxContexts)
	scheduleCaptureBudgetMembers := captureContextsLimit * len(base.Seeds())
	scheduleCaptureSession, err = setcontext.NewSession(provider, scheduleCaptureBudgetMembers)
	if err != nil {
		return out, err
	}
	router := &scheduleContextRouter{
		sources: sources, model: model, captures: scheduleCaptureSession,
		maxMembers: scheduleCaptureBudgetMembers, attempts: map[string]scheduleCaptureOutcome{},
		onCapture: func(reason string) { boundaries[reason] = true },
	}
	type hydratedContext struct {
		handle      *setcontext.Handle
		coordinates []string
	}
	hydrated := map[string]hydratedContext{}
	hydrate = func(c Candidate) (Candidate, error) {
		key := c.Context.Key()
		cached, ok := hydrated[key]
		if !ok {
			h, codes, e := router.Resolve(hydrateCtx, c.Context)
			if e != nil {
				return c, e
			}
			if h == nil {
				return c, fmt.Errorf("retained package lost its model: %v", codes)
			}
			p, e := h.SearchPanel()
			if e != nil {
				return c, e
			}
			cached = hydratedContext{handle: h, coordinates: p.Coordinates()}
			hydrated[key] = cached
		}
		var e error
		c.Index, e = index.ForPackages(c.Packages, c.Score.Assignment, cached.coordinates)
		c.Handle = cached.handle
		return c, e
	}
	defer func() { out.NeutralModel = model.Stats() }()
	captureSeconds := time.Since(captureStarted).Seconds()
	catalog := []domain.SetCapability{}
	for _, set := range sources.Sets {
		catalog = append(catalog, domain.SetCapability{UID: set.Key, TwoPiece: true, FourPiece: set.FourPieceModeled})
	}

	bind := func(packs [4]domain.Package, seed domain.Assignment, lane string) (Candidate, bool, error) {
		if err := runCtx.Err(); err != nil {
			return Candidate{}, false, err
		}
		changes := map[string][]setcontext.Set{}
		for actor, w := range index.Wearers {
			changes[w.WearerKey] = nil
			for _, s := range packs[actor].Sets {
				changes[w.WearerKey] = append(changes[w.WearerKey], setcontext.Set{UID: s.SetUID, Count: s.Count})
			}
		}
		target, e := base.Replace(changes)
		if e != nil {
			return Candidate{}, false, e
		}
		h, codes, e := router.Resolve(runCtx, target)
		if e != nil {
			return Candidate{}, false, e
		}
		if h == nil {
			for _, code := range codes {
				boundaries[packageIdentity(packs)+": "+code] = true
			}
			out.Unqueued++
			return Candidate{}, false, nil
		}
		p, e := h.SearchPanel()
		if e != nil {
			return Candidate{}, false, e
		}
		view, e := index.ForPackages(packs, seed, p.Coordinates())
		if e != nil {
			return Candidate{}, false, e
		}
		dense, e := view.DenseDeltas(seed)
		if e != nil {
			return Candidate{}, false, e
		}
		dps, e := p.EvaluateDPS(dense)
		if e != nil {
			return Candidate{}, false, e
		}
		return Candidate{Score: search.ScoredAssignment{Assignment: seed, DPS: dps, Source: lane}, Context: target, Handle: h, Index: view, Packages: packs}, true, nil
	}
	var packs [4]domain.Package
	for actor, w := range index.Wearers {
		packs[actor] = domain.Package{Sets: w.SelectedSets}
	}
	initial, ok, err := bind(packs, index.Incumbent, "neutral_initial")
	if err != nil {
		return out, err
	}
	if !ok {
		codes := make([]string, 0, len(boundaries))
		for code := range boundaries {
			codes = append(codes, code)
		}
		sort.Strings(codes)
		return out, fmt.Errorf("initial package requires an unsupported rule/schedule route: %s", strings.Join(codes, "; "))
	}
	out.Initial, out.Selected, out.Leader = initial, initial, initial
	retain := func(c Candidate) {
		archive.offer(c)
		coreArchive.offer(c)
		packageTeams = offerPackageTeam(packageTeams, c)
		pool = append(pool, c)
		if len(pool) > 4*cfg.FinalistLimit {
			pool = chooseFinalists(pool, 2*cfg.FinalistLimit)
		}
		if betterCandidate(c, out.Leader) {
			out.Leader = c
		}
	}
	retain(initial)
	searchcontrol.Ready(runCtx)
	solverFor := func(c Candidate) (*search.Engine, error) {
		p, e := c.Handle.SearchPanel()
		if e != nil {
			return nil, e
		}
		solver, e := search.NewInventory(c.Index, p, cfg.Search)
		if e == nil {
			groupKey := packageIdentity(c.Packages)
			solver.ObserveCandidates(func(score search.ScoredAssignment) {
				row := c
				row.Score = score
				archive.offerGroup(groupKey, row)
				coreArchive.offerGroup(groupKey, row)
			})
		}
		return solver, e
	}

	// A cheap legal seed uses the NEW package's reduced gradient. A gradient is
	// only an ordering hint; no item or package is eliminated by it.
	screens := map[string]search.CandidateReport{}
	prepare := func(anchor Candidate, actor int, pack domain.Package) (Candidate, bool, error) {
		start := time.Now()
		defer func() { out.NeutralSeedSeconds += time.Since(start).Seconds() }()
		packs := anchor.Packages
		packs[actor] = pack
		seed, e := anchor.Index.PackageSeed(anchor.Score.Assignment, actor, pack, nil)
		if e != nil {
			var found bool
			seed, found = teamPackageSeed(anchor.Index, packs, [4]map[int64]float64{})
			if !found {
				out.ReservationDeferred++
				return Candidate{}, false, nil
			}
		}
		c, ok, e := bind(packs, seed, "neutral_package_seed")
		if e != nil || !ok {
			return c, ok, e
		}
		p, e := c.Handle.SearchPanel()
		if e != nil {
			return c, false, e
		}
		solver, e := solverFor(c)
		if e != nil {
			return c, false, e
		}
		screen, e := solver.ScreenCandidates(runCtx, seed, actor, cfg.MaxSearchExpansions-out.SearchExpansions)
		out.SearchExpansions += screen.Step.Expanded
		if len(screen.Step.Finalists) > 0 {
			c.Score = screen.Step.Finalists[0]
		}
		screen.High = math.Max(screen.High, c.Score.DPS)
		screens[fmt.Sprintf("%d:%s", actor, pack.Key())] = screen
		screenErr := e
		c.Index, e = c.Index.ForPackages(c.Packages, c.Score.Assignment, p.Coordinates())
		if e != nil {
			return c, false, e
		}
		if screenErr != nil {
			retain(c) // partial improvement owns its updated physical reference
			return c, false, screenErr
		}
		return c, true, nil
	}
	record := func(c Candidate, lane string, step search.ActorStep, seconds float64) {
		w := ContextWork{ContextSHA256: c.Context.Key(), Lane: lane, FormulaDPS: c.Score.DPS, Assignment: c.Score.Assignment, SearchSeconds: seconds, Expansions: step.Expanded, BoundEvaluations: step.BoundEvaluations, BoundPrunedBuilds: step.BoundPrunedBuilds, BudgetUnexpanded: step.BudgetUnexpanded, ReducedNodes: step.ReducedNodes}
		for actor, p := range c.Packages {
			w.Packages[actor] = p.Key()
		}
		out.Work = append(out.Work, w)
	}
	record(initial, "neutral_initial", search.ActorStep{}, 0)
	out.Work[0].CaptureSeconds = captureSeconds
	jointWorkLimit := errors.New("joint package global work limit")
	runPackageJoint := func() error {
		started := time.Now()
		stats := PackageJointStats{}
		defer func() {
			stats.Seconds = time.Since(started).Seconds()
			out.NeutralPackageJoint = append(out.NeutralPackageJoint, stats)
		}()
		// Snapshot roots: new complete teams are retained for the NEXT layer,
		// not recursively expanded with a renewed budget in this one.
		roots := append([]Candidate(nil), packageTeams...)
		priorities := map[domain.Assignment][4]map[int64]float64{}
		evaluate := func(anchor Candidate, move packagePairMove) ([]Candidate, error) {
			if out.SearchExpansions >= cfg.MaxSearchExpansions {
				return nil, jointWorkLimit
			}
			weights, found := priorities[anchor.Score.Assignment]
			if !found {
				p, e := anchor.Handle.SearchPanel()
				if e != nil {
					return nil, e
				}
				gradient, _, e := rawPriorities(runCtx, anchor.Index, p)
				if e != nil {
					return nil, e
				}
				for actor := range weights {
					weights[actor], e = anchor.Index.ArtifactLinearPriorities(actor, gradient)
					if e != nil {
						return nil, e
					}
				}
				priorities[anchor.Score.Assignment] = weights
			}
			seeds, e := packagePairSeeds(runCtx, anchor, move, weights)
			if e != nil {
				return nil, e
			}
			stats.Seeded += len(seeds)
			if len(seeds) == 0 {
				stats.AllocationDeferred++
				boundaries["joint_package_seed_allocation_deferred"] = true
			}
			var rows []Candidate
			for _, seed := range seeds {
				if out.SearchExpansions >= cfg.MaxSearchExpansions {
					return rows, jointWorkLimit
				}
				c, ok, e := bind(move.Packs, seed, "neutral_package_pair")
				if e != nil {
					return rows, e
				}
				if !ok {
					stats.Unavailable++
					continue
				}
				out.SearchExpansions++
				stats.Scored++
				// Recompute guides under the new JOINT bonuses; old gradients only
				// proposed a legal seed, never ranked the changed set effects.
				for _, actor := range move.Actors {
					remaining := cfg.MaxSearchExpansions - out.SearchExpansions
					if remaining <= 0 {
						return append(rows, c), jointWorkLimit
					}
					p, e := c.Handle.SearchPanel()
					if e != nil {
						return append(rows, c), e
					}
					solver, e := solverFor(c)
					if e != nil {
						return append(rows, c), e
					}
					result, stepErr := solver.ScreenCandidates(runCtx, c.Score.Assignment, actor, min(remaining, cfg.Search.MaxExpandedPerActor))
					out.SearchExpansions += result.Step.Expanded
					if len(result.Step.Finalists) > 0 {
						c.Score = result.Step.Finalists[0]
					}
					view, e := c.Index.ForPackages(c.Packages, c.Score.Assignment, p.Coordinates())
					if e != nil {
						return rows, e
					}
					c.Index = view
					if stepErr != nil {
						return append(rows, c), stepErr
					}
				}
				rows = append(rows, c)
			}
			return rows, nil
		}
		refine := func(c Candidate) (Candidate, error) {
			started, expanded := time.Now(), out.SearchExpansions
			defer func() {
				record(c, "neutral_package_pair:refined", search.ActorStep{Expanded: out.SearchExpansions - expanded}, time.Since(started).Seconds())
			}()
			for actor := 0; actor < 4; actor++ {
				remaining := cfg.MaxSearchExpansions - out.SearchExpansions
				if remaining <= 0 {
					return c, jointWorkLimit
				}
				p, e := c.Handle.SearchPanel()
				if e != nil {
					return c, e
				}
				solver, e := solverFor(c)
				if e != nil {
					return c, e
				}
				result, stepErr := solver.RefineCandidates(runCtx, c.Score.Assignment, actor, min(remaining, cfg.Search.MaxExpandedPerActor))
				out.SearchExpansions += result.Step.Expanded
				if len(result.Step.Finalists) > 0 {
					c.Score = result.Step.Finalists[0]
				}
				view, e := c.Index.ForPackages(c.Packages, c.Score.Assignment, p.Coordinates())
				if e != nil {
					return c, e
				}
				c.Index = view
				if stepErr != nil {
					return c, stepErr
				}
			}
			return c, nil
		}
		boundaries["joint_package_frontier_heuristic"] = true
		return explorePackagePairs(runCtx, roots, packageChoices, evaluate, refine, retain, &stats)
	}
	// Score joint transfers before deep per-package work, and again after it.
	runJoint := func() error {
		remaining := cfg.MaxSearchExpansions - out.SearchExpansions
		if remaining > 0 && runCtx.Err() == nil {
			c := out.Leader
			p, e := c.Handle.SearchPanel()
			if e != nil {
				return e
			}
			solver, e := solverFor(c)
			if e != nil {
				return e
			}
			out.NeutralJointRan = true
			jointStarted := time.Now()
			result, e := solver.RefineJoint(runCtx, c.Score.Assignment, remaining)
			out.NeutralJointSeconds += time.Since(jointStarted).Seconds()
			out.SearchExpansions += result.PairEvaluated
			for _, score := range result.Finalists {
				candidate := c
				candidate.Score = score
				candidate.Index, err = c.Index.ForPackages(c.Packages, score.Assignment, p.Coordinates())
				if err != nil {
					return err
				}
				retain(candidate)
			}
			if len(result.Finalists) > 0 {
				c.Score = result.Finalists[0]
			}
			record(c, "neutral_joint", search.ActorStep{Expanded: result.PairEvaluated}, out.NeutralJointSeconds)
			if result.PairBudgetExhausted {
				boundaries["joint_inventory_work_deferred"] = true
			}
			if e != nil {
				return e
			}
		}
		return nil
	}

	for cycle := 0; cycle < cfg.Search.MaxCycles; cycle++ {
		if err = runCtx.Err(); err != nil {
			return out, err
		}
		if out.StopReason != "" {
			break
		}
		before := out.Leader.Score.DPS
		beforeTeams := append([]Candidate(nil), packageTeams...)
		// Every feasible package receives complete real-build screens, not a bound.
		// Neither source tier nor a named bonus short list selects this queue.
		feasible, e := out.Leader.Index.FeasiblePackages(catalog, nil)
		if e != nil {
			return out, e
		}
		out.NeutralCycles = append(out.NeutralCycles, NeutralCycleCoverage{Cycle: cycle + 1, Total: 4 * len(feasible)})
		coverage := &out.NeutralCycles[len(out.NeutralCycles)-1]
		// Block-coordinate (Gauss-Seidel) updates: accept a wearer's complete
		// team result before evaluating the next wearer. Conditional best builds
		// from one stale team cannot be combined as independent contributions:
		// in particular, several wearers may all select the same shared bonus.
		// This changes scheduling, not the number of package screens/cycles.
		for actor := 0; actor < 4; actor++ {
			anchor := out.Leader
			packageChoices[actor] = nil // conditional scores share THIS block's team
			record(anchor, fmt.Sprintf("neutral_actor_%d:anchor", actor), search.ActorStep{}, 0)
			queue := &neutralProposalQueue{}
			proposalStarted = time.Now()
			for packIndex, pack := range feasible {
				if cfg.Progress != nil && packIndex%32 == 0 {
					cfg.Progress("searching", (cycle*4+actor)*1000+packIndex*500/max(1, len(feasible)), cfg.Search.MaxCycles*4000)
				}
				if err = runCtx.Err(); err != nil {
					return out, err
				}
				if out.SearchExpansions >= cfg.MaxSearchExpansions {
					out.StopReason = "search_expansion_budget"
					return out, nil
				}
				reservedBefore := out.ReservationDeferred
				c, ok, e := prepare(anchor, actor, pack)
				if e != nil {
					return out, e
				}
				coverage.Prepared++
				if !ok {
					if out.ReservationDeferred > reservedBefore {
						coverage.ReservationDeferred++
					} else {
						coverage.ModelUnavailable++
					}
					continue
				}
				retain(c)
				packageChoices[actor] = offerPackageChoice(packageChoices[actor], pack, c.Score.DPS)
				out.Queued++
				coverage.Queued++
				heap.Push(queue, &neutralProposal{actor: actor, pack: pack, seed: c.Score.Assignment, priority: c.Score.DPS,
					order: coverage.Queued, screen: screens[fmt.Sprintf("%d:%s", actor, pack.Key())]})
			}
			out.ProposalSeconds += time.Since(proposalStarted).Seconds()
			proposalStarted = time.Time{}
			// The fifth distinct complete TEAM result is a heuristic scheduling bar.
			// Mandatory comparison rows must not lower or duplicate this threshold.
			fifth := func() float64 {
				rows := append([]Candidate(nil), pool...)
				sort.SliceStable(rows, func(i, j int) bool { return candidateBefore(rows[i], rows[j]) })
				seen := map[domain.Assignment]bool{}
				n := 0
				for _, c := range rows {
					if !seen[c.Score.Assignment] {
						seen[c.Score.Assignment] = true
						n++
						if n == 5 {
							return c.Score.DPS
						}
					}
				}
				return math.Inf(-1)
			}
			queueSize := queue.Len()
			for queue.Len() > 0 {
				if cfg.Progress != nil && queue.Len()%32 == 0 {
					cfg.Progress("searching", (cycle*4+actor)*1000+500+(queueSize-queue.Len())*500/max(1, queueSize), cfg.Search.MaxCycles*4000)
				}
				if e := runCtx.Err(); e != nil {
					return out, e
				}
				remaining := cfg.MaxSearchExpansions - out.SearchExpansions
				if remaining <= 0 {
					out.StopReason = "search_expansion_budget"
					break
				}
				proposal := heap.Pop(queue).(*neutralProposal)
				if proposal.screen.DeferBelow(fifth()) {
					coverage.ModelDeferred++
					coverage.HeuristicSkipped++
					continue
				}
				packs := anchor.Packages
				packs[proposal.actor] = proposal.pack
				c, ok, e := bind(packs, proposal.seed, "neutral_real_candidate")
				if e != nil {
					return out, e
				}
				if !ok {
					return out, fmt.Errorf("screened package lost its source model")
				}
				p, e := c.Handle.SearchPanel()
				if e != nil {
					return out, e
				}
				solver, e := solverFor(c)
				if e != nil {
					return out, e
				}
				tick := time.Now()
				result, e := solver.RefineCandidates(runCtx, c.Score.Assignment, proposal.actor, min(remaining, cfg.Search.MaxExpandedPerActor))
				out.SearchExpansions += result.Step.Expanded
				for _, score := range result.Step.Finalists {
					candidate := c
					candidate.Score = score
					candidate.Index, err = c.Index.ForPackages(c.Packages, score.Assignment, p.Coordinates())
					if err != nil {
						return out, err
					}
					retain(candidate)
					packageChoices[actor] = offerPackageChoice(packageChoices[actor], proposal.pack, candidate.Score.DPS)
				}
				if len(result.Step.Finalists) > 0 {
					c.Score = result.Step.Finalists[0]
				}
				record(c, "neutral_real_candidate:"+result.Stop, result.Step, time.Since(tick).Seconds())
				coverage.Sampled++
				if result.Exhaustive {
					coverage.Processed++
				} else {
					coverage.ModelDeferred++
				}
				if e != nil {
					return out, e
				}
			}
			if out.StopReason != "" {
				break
			}
			record(out.Leader, fmt.Sprintf("neutral_actor_%d:complete", actor), search.ActorStep{}, 0)
		}
		out.Guides++
		if out.StopReason != "" {
			break
		}
		if e := runPackageJoint(); e != nil {
			if errors.Is(e, jointWorkLimit) {
				out.StopReason = "search_expansion_budget"
				break
			}
			return out, e
		}
		if e := runJoint(); e != nil {
			return out, e
		}

		joint, e := permutedPackages(runCtx, out.Leader)
		if e != nil {
			return out, e
		}
		for _, proposal := range joint {
			c, ok, e := bind(proposal.packages, proposal.seed, "neutral_package_exchange")
			if e != nil {
				return out, e
			}
			if !ok {
				continue
			}
			retain(c)
		}
		if out.Leader.Score.DPS <= before+1e-8*math.Max(1, math.Abs(before)) && samePackageTeams(beforeTeams, packageTeams) {
			out.StopReason = "neutral_sampled_coordinate_pass_stable"
			break
		}
	}
	if out.StopReason == "" {
		out.StopReason = "neutral_cycle_budget"
	}
	if e := runJoint(); e != nil {
		return out, e
	}
	// Stabilize a fixed panel of best scored package representatives. The
	// independent archive includes candidates observed inside search solvers,
	// even when the bounded working pool later drops them.
	stabilizedFinalists = neutralStabilizationFinalists(coreArchive, cfg.FinalistLimit)
	for finalistIndex, c := range stabilizedFinalists {
		if c.Handle == nil {
			c, err = hydrate(c)
			if err != nil {
				return out, err
			}
		}
		remaining := cfg.MaxSearchExpansions - out.SearchExpansions
		if remaining <= 0 || runCtx.Err() != nil {
			boundaries["finalist_stabilization_deferred"] = true
			break
		}
		p, e := c.Handle.SearchPanel()
		if e != nil {
			return out, e
		}
		solver, e := solverFor(c)
		if e != nil {
			return out, e
		}
		started := time.Now()
		polished, e := solver.Stabilize(runCtx, c.Score.Assignment, min(remaining, cfg.Search.MaxExpandedPerActor))
		out.SearchExpansions += polished.Evaluations
		c.Score = polished.Leader
		c.Index, err = c.Index.ForPackages(c.Packages, c.Score.Assignment, p.Coordinates())
		if err != nil {
			return out, err
		}
		retain(c)
		stabilizedFinalists[finalistIndex] = c
		out.NeutralStabilization = append(out.NeutralStabilization, polished)
		record(c, "neutral_finalist:"+polished.Stop, search.ActorStep{Expanded: polished.Evaluations}, time.Since(started).Seconds())
		if polished.Stop != "single_stationary_sampled_pairs_stable" {
			boundaries["finalist_stabilization_deferred"] = true
		}
		if e != nil {
			return out, e
		}
	}

	return out, nil
}

// neutralStabilizationFinalists is fixed by the search contract, not by the
// number of groups or alternatives requested for display.
func neutralStabilizationFinalists(archive *resultArchive, limit int) []Candidate {
	if archive == nil || limit <= 0 {
		return nil
	}
	return chooseFinalists(archive.top(limit), limit)
}

func packageIdentity(packs [4]domain.Package) string {
	keys := make([]string, 4)
	for i, p := range packs {
		keys[i] = p.Key()
	}
	return strings.Join(keys, "|")
}

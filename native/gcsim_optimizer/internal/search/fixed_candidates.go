package search

import (
	"context"
	"errors"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/searchcontrol"
)

// FixedResult records complete-build Selected work independently of the shared
// search Result. Product installation still requires the same-input gate.
type FixedResult struct {
	Algorithm     string               `json:"algorithm"`
	Search        Result               `json:"search"`
	Evaluations   int                  `json:"evaluations"`
	CandidateWork []FixedCandidateWork `json:"candidate_work"`
	Stabilization []Stabilization      `json:"stabilization"`
}

// FixedCandidateWork records which complete-candidate stage consumed work.
// Candidate reports are summarized here; region-bound counters stay zero.
type FixedCandidateWork struct {
	Cycle      int    `json:"cycle"`
	WearerKey  string `json:"wearer_key"`
	Stage      string `json:"stage"`
	Expanded   int    `json:"expanded"`
	Exhaustive bool   `json:"exhaustive"`
	Stop       string `json:"stop"`
}

const fixedCandidateAlgorithm = "fixed-package-screen-refine-stabilize-v1"

// RunFixedCandidates searches the request's existing fixed 4p/2+2 packages with
// complete legal builds, then stabilizes a small shortlist. The CLI's candidate
// route is separate from installed-product acceptance.
//
// Construct Engine with NewInventory to enable the existing candidate and
// stabilization APIs, but do not call Engine.Run: that method selects the
// separate region-bound inventory search. This route fails closed for finite
// ER because candidateRun and Stabilize do not yet support an energy model.
func (engine *Engine) RunFixedCandidates(ctx context.Context, workLimit, finalistLimit int, outputLimits ...int) (FixedResult, error) {
	if ctx != nil && ctx.Err() != nil {
		return FixedResult{Algorithm: fixedCandidateAlgorithm, Search: Result{StopReason: fixedStopForContext(ctx.Err())}}, ctx.Err()
	}
	if engine == nil || engine.domain == nil || engine.panel == nil || !engine.inventoryBounds {
		return FixedResult{}, fmt.Errorf("fixed-candidate search requires a NewInventory engine")
	}
	if engine.energy != nil {
		return FixedResult{}, fmt.Errorf("fixed-candidate search does not support finite energy")
	}
	if ctx == nil || workLimit < 0 || finalistLimit < 1 || finalistLimit > 7 {
		return FixedResult{}, fmt.Errorf("fixed-candidate search limits/context are invalid")
	}
	outputLimit := 0
	if len(outputLimits) > 1 {
		return FixedResult{}, fmt.Errorf("one output limit required")
	}
	if len(outputLimits) == 1 {
		outputLimit = outputLimits[0]
		if outputLimit < 1 || outputLimit > contracts.MaxResultBuildsPerGroup {
			return FixedResult{}, fmt.Errorf("invalid output limit")
		}
	}
	archive := []ScoredAssignment{}
	previousObserver := engine.observeCandidate
	defer func() { engine.observeCandidate = previousObserver }()
	if outputLimit > 0 {
		engine.ObserveCandidates(func(row ScoredAssignment) {
			if previousObserver != nil {
				previousObserver(row)
			}
			if len(archive) >= outputLimit {
				last := archive[len(archive)-1]
				if row.DPS < last.DPS || row.DPS == last.DPS && !assignmentLess(row.Assignment, last.Assignment) {
					return
				}
			}
			archive = engine.mergeFinalists(outputLimit, append(archive, row)...)
		})
	}
	if err := engine.domain.ValidateAssignment(engine.domain.Incumbent); err != nil {
		return FixedResult{}, fmt.Errorf("fixed-candidate incumbent is invalid: %w", err)
	}
	initialDPS, err := engine.score(engine.domain.Incumbent)
	if err != nil {
		return FixedResult{}, err
	}
	initial := ScoredAssignment{Assignment: engine.domain.Incumbent, DPS: initialDPS, Source: "fixed_candidates_initial"}
	engine.observed(initial)
	out := FixedResult{
		Algorithm: fixedCandidateAlgorithm,
		Search: Result{
			Initial: initial, Leader: initial,
			ResponseLedger:          engine.panel.ResponseLedger(),
			OpaqueReasons:           engine.panel.OpaqueReasons(),
			SaturationFrozenWearers: []string{},
		},
		CandidateWork: []FixedCandidateWork{},
		Stabilization: []Stabilization{},
	}
	searchcontrol.Ready(ctx)
	if err := ctx.Err(); err != nil {
		if searchcontrol.Requested(ctx) {
			out.Search.Finalists = []ScoredAssignment{initial}
		}
		out.Search.StopReason = fixedStopForContext(err)
		return out, err
	}

	// Keep a bounded set of full assignments from every screen/refinement.
	// The incumbent enters the pool but remains separately identified as Initial.
	poolLimit := max(finalistLimit, engine.config.PairFinalistLimit)
	pool := []ScoredAssignment{initial}
	searchLeader := initial
	searchShare := workLimit / 2
	searchStop := "fixed_candidates_cycle_budget"
	searchBudgetLimited := false
	var searchErr error

	consume := func(report CandidateReport, cycle, actor int, stage string) bool {
		step := report.Step
		step.Cycle = cycle
		before := searchLeader
		if len(step.Finalists) > 0 {
			pool = engine.mergeFinalists(poolLimit, append(pool, step.Finalists...)...)
			if len(pool) > 0 && engine.betterScored(pool[0], searchLeader) {
				searchLeader = pool[0]
				step.Accepted = true
			}
		}
		if step.Accepted && searchLeader.Assignment != before.Assignment {
			out.Search.AcceptedSteps++
		}
		// Pre-stabilization candidates stay in the private bounded pool. The
		// returned shared Search.Result must not expose them as old finalists.
		step.Finalists = nil
		out.Search.Steps = append(out.Search.Steps, step)
		out.CandidateWork = append(out.CandidateWork, FixedCandidateWork{
			Cycle: cycle, WearerKey: engine.domain.Wearers[actor].WearerKey,
			Stage: stage, Expanded: step.Expanded, Exhaustive: report.Exhaustive, Stop: report.Stop,
		})
		out.Evaluations += step.Expanded
		return searchLeader.Assignment != before.Assignment
	}

	for cycle := 1; cycle <= engine.config.MaxCycles; cycle++ {
		if err := ctx.Err(); err != nil {
			searchErr = err
			searchStop = fixedStopForContext(err)
			break
		}
		cycleAnchor := searchLeader.Assignment
		cycleImproved := false
		for actor := 0; actor < len(engine.domain.Wearers); actor++ {
			if err := ctx.Err(); err != nil {
				searchErr = err
				searchStop = fixedStopForContext(err)
				break
			}
			remaining := searchShare - out.Evaluations
			if remaining <= 0 {
				searchBudgetLimited = true
				searchStop = "fixed_candidates_search_budget"
				break
			}
			actorAllowance := min(engine.config.MaxExpandedPerActor, remaining)
			anchor := searchLeader.Assignment
			screen, screenErr := engine.ScreenCandidates(ctx, anchor, actor, actorAllowance)
			cycleImproved = consume(screen, cycle, actor, "screen") || cycleImproved
			if screenErr != nil {
				searchErr = screenErr
				if errors.Is(screenErr, context.Canceled) || errors.Is(screenErr, context.DeadlineExceeded) {
					searchStop = fixedStopForContext(screenErr)
				}
				break
			}
			refineAllowance := min(actorAllowance-screen.Step.Expanded, searchShare-out.Evaluations)
			if refineAllowance <= 0 {
				if searchShare-out.Evaluations <= 0 {
					searchBudgetLimited = true
					searchStop = "fixed_candidates_search_budget"
					break
				}
				continue
			}
			// The screen's best complete build becomes the next actor's immediate
			// anchor; refinement then starts from the newest complete team.
			anchor = searchLeader.Assignment
			refined, refineErr := engine.RefineCandidates(ctx, anchor, actor, refineAllowance)
			cycleImproved = consume(refined, cycle, actor, "refine") || cycleImproved
			if refineErr != nil {
				searchErr = refineErr
				if errors.Is(refineErr, context.Canceled) || errors.Is(refineErr, context.DeadlineExceeded) {
					searchStop = fixedStopForContext(refineErr)
				}
				break
			}
		}
		if searchErr != nil || searchBudgetLimited {
			break
		}
		out.Search.CompletedCycles++
		if !cycleImproved {
			searchStop = "fixed_candidates_sampled_coordinate_pass_stable"
			break
		}
		if cycle == engine.config.MaxCycles {
			searchStop = "fixed_candidates_cycle_budget"
		}
		if searchLeader.Assignment == cycleAnchor && cycle == engine.config.MaxCycles {
			searchStop = "fixed_candidates_sampled_coordinate_pass_stable"
		}
	}
	if searchErr != nil && !errors.Is(searchErr, context.Canceled) && !errors.Is(searchErr, context.DeadlineExceeded) {
		out.Search.StopReason = "fixed_candidates_error"
		return out, searchErr
	}

	// Only the best bounded complete assignments are polished. Unused screen /
	// refinement allowance flows into this shared cap; each remaining finalist
	// receives a fair share of what is left.
	shortlist := engine.mergeFinalists(finalistLimit, pool...)
	available := workLimit - out.Evaluations
	finalRows := []ScoredAssignment{}
	appendBudgetLimited := func(rows []ScoredAssignment, stop string) {
		for _, row := range rows {
			if len(out.Stabilization) >= finalistLimit {
				return
			}
			status := Stabilization{Leader: row, Stop: stop}
			out.Stabilization = append(out.Stabilization, status)
			finalRows = append(finalRows, row)
		}
	}
	for i, candidate := range shortlist {
		if err := ctx.Err(); err != nil {
			searchStop = fixedStopForContext(err)
			appendBudgetLimited(shortlist[i:], "stabilization_cancelled_before_check")
			if searchErr == nil {
				searchErr = err
			}
			break
		}
		remainingFinalists := len(shortlist) - i
		allowance := available / remainingFinalists
		polished, polishErr := engine.Stabilize(ctx, candidate.Assignment, allowance)
		out.Evaluations += polished.Evaluations
		available -= polished.Evaluations
		if polishErr != nil {
			if errors.Is(polishErr, context.Canceled) || errors.Is(polishErr, context.DeadlineExceeded) {
				polished.Stop = "stabilization_cancelled"
				out.Stabilization = append(out.Stabilization, polished)
				finalRows = append(finalRows, polished.Leader)
				searchStop = fixedStopForContext(polishErr)
				appendBudgetLimited(shortlist[i+1:], "stabilization_cancelled_before_check")
				if searchErr == nil {
					searchErr = polishErr
				}
				break
			}
			out.Search.StopReason = "fixed_candidates_stabilization_error"
			return out, polishErr
		}
		out.Stabilization = append(out.Stabilization, polished)
		finalRows = append(finalRows, polished.Leader)
	}

	if len(finalRows) > 0 {
		out.Search.Finalists = engine.mergeFinalists(finalistLimit, finalRows...)
		out.Search.Leader = out.Search.Finalists[0]
	} else {
		out.Search.Leader = initial
	}
	if outputLimit > 0 {
		out.Search.Finalists = engine.mergeFinalists(outputLimit, append(archive, finalRows...)...)
		if len(out.Search.Finalists) > 0 {
			out.Search.Leader = out.Search.Finalists[0]
		}
	}
	out.Search.StopReason = searchStop
	for _, status := range out.Stabilization {
		if status.Stop != "single_stationary_sampled_pairs_stable" {
			if out.Search.StopReason == "" {
				out.Search.StopReason = "fixed_candidates_stabilization_budget"
			} else if out.Search.StopReason == "fixed_candidates_sampled_coordinate_pass_stable" || out.Search.StopReason == "fixed_candidates_cycle_budget" {
				out.Search.StopReason += "+stabilization_budget"
			}
			break
		}
	}
	return out, searchErr
}

func fixedStopForContext(err error) string {
	if errors.Is(err, context.Canceled) {
		return "fixed_candidates_cancelled"
	}
	return "fixed_candidates_deadline"
}

package main

// Common research H. All numerical search and refinement remains owned by the
// hash-pinned v2 hybrid source. This file configures it and audits frozen output.
import (
	"fmt"
	"math"
	"os"
	"sort"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

type commonHConfig struct {
	Depth                                     string
	CatalogPasses, PolicySeconds              int
	FormulaLimit, GradientLimit, ResolveLimit int
}

func commonHConfiguration(depth string, catalog int) (commonHConfig, error) {
	if catalog <= 0 || (depth != "first" && depth != "full") {
		return commonHConfig{}, fmt.Errorf("common H requires first/full depth and a nonempty catalog")
	}
	passes := 1
	if depth == "full" {
		passes = 2
	}
	return commonHConfig{depth, passes, 180, 400000, 100000, 9 + 16*catalog + 64}, nil
}

func commonHPasses(h *hybridRun) int {
	if h.researchH == nil {
		return 2
	}
	return h.researchH.CatalogPasses
}

func commonHWorkStop(h *hybridRun) string {
	if h.researchH == nil {
		return ""
	}
	c := h.researchH
	if h.w.work.Formula >= c.FormulaLimit {
		return "formula_work_limit"
	}
	if h.w.work.Gradient >= c.GradientLimit {
		return "gradient_work_limit"
	}
	if h.w.extra.Requests >= c.ResolveLimit {
		return "resolve_work_limit"
	}
	return ""
}

func commonHWithinWork(h *hybridRun) bool { return commonHWorkStop(h) == "" }

// A full invocation publishes the refined first-pass checkpoint before the
// explicit second pass continues with the same pool, bank, model and clock.
// A first invocation returns there. Cross-process checkpoint resume is not an API.
func runCommonH(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, original [4]domain.Package, options []domain.Package, initial proto.State, cfg commonHConfig, global time.Time) *hybridRun {
	t.Helper()
	expected, configErr := commonHConfiguration(cfg.Depth, len(options))
	if configErr != nil || cfg != expected {
		t.Fatal("unsupported common H configuration", cfg, configErr)
	}
	at := time.Now()
	w, err := newR2World(factory, req, base, true)
	if err != nil {
		t.Fatal(err)
	}
	initial = proto.Seed(initial.Mains, [4][10]float64{}, 0, 45)
	h := newHybrid(w, initial, "H_common", true, global, cfg.PolicySeconds)
	h.started = at
	h.deadline = at.Add(time.Duration(cfg.PolicySeconds) * time.Second)
	if global.Before(h.deadline) {
		h.deadline = global
	}
	h.researchH = &cfg
	emitFeasible(map[string]any{"kind": "common_h_configuration", "configuration": cfg,
		"domain_units_per_wearer": 45, "initial_rows": 20, "upgrade_units": 25,
		"contexts_per_wearer": 2, "bank_limit": 6, "starts_per_family": 3,
		"short_iterations": 4, "refinement": "sweep winner; after each pass two leaders and one unrefined alternative",
		"grouping":               "source-validated exact bound-program family within this captured model",
		"numeric_solution_cache": false, "continuation_restarts_first_pass": false,
		"unknown_value": "unbounded/unavailable, never zero", "stopping_is_optimality_proof": false})
	err = h.search(original, options)
	hybridAcceptStop(t, err)
	rows := h.snapshot("H_common_" + cfg.Depth)
	if len(rows) == 0 {
		t.Fatal("common H found no full-budget legal candidate")
	}
	reason := commonHWorkStop(h)
	if reason == "" && err != nil {
		reason = "policy_or_global_wall_guard"
	}
	emitFeasible(map[string]any{"kind": "common_h_result", "depth": cfg.Depth,
		"best": h.w.row(rows[0]), "configured_passes_complete": h.refinedPasses == cfg.CatalogPasses,
		"planned_sweeps": 8 * cfg.CatalogPasses, "completed_sweeps": h.fullSweeps,
		"stop_reason": reason, "route_sha256": fmt.Sprintf("%x", h.w.route.Sum(nil)),
		"timing_scope": "cold policy model plus search; capture/source/input preparation reported separately",
		"source_upper": "unbounded", "outer_upper": "unbounded", "full_cartesian_covered": false})
	return h
}

type commonHAuditTarget struct {
	Packages [4]domain.Package
	Reason   string
	Actors   [2]int
	Ranks    [2]int
}

func commonHAuditPlan(pool map[string]feasibleCandidate, aliases map[string]map[string]bool, options []domain.Package) []commonHAuditTarget {
	rows := r2Sorted(pool)
	if len(rows) == 0 {
		return nil
	}
	out := []commonHAuditTarget{}
	seen := map[string]bool{}
	add := func(target commonHAuditTarget) {
		key := theoryteams.Key(target.Packages)
		if !seen[key] {
			seen[key] = true
			out = append(out, target)
		}
	}
	for i := 1; i < min(3, len(rows)); i++ {
		add(commonHAuditTarget{Packages: rows[i].packages, Reason: fmt.Sprintf("frozen_policy_rank_%d", i+1), Actors: [2]int{-1, -1}})
	}
	anchor := theoryteams.Key(rows[0].packages)
	pairs := map[[2]int]bool{}
	for _, candidate := range hybridPairPlan(pool, aliases, options) {
		if candidate.Anchor != anchor || pairs[candidate.Actors] {
			continue
		}
		pairs[candidate.Actors] = true
		add(commonHAuditTarget{candidate.Packages, "first_ranked_both_nonleader_pair_from_frozen_leader", candidate.Actors, candidate.Ranks})
	}
	return out
}

type commonHAuditGuard struct {
	guard               hybridGuard
	Formula, Gradient   int
	FormulaMax, GradMax int
}

func commonHAuditCanonicalSeed(state proto.State) proto.State {
	for actor := range state.Lines {
		for slot := range state.Lines[actor] {
			for i := 0; i < 4; i++ {
				for j := i + 1; j < 4; j++ {
					if state.Lines[actor][slot][j] < state.Lines[actor][slot][i] {
						state.Lines[actor][slot][i], state.Lines[actor][slot][j] = state.Lines[actor][slot][j], state.Lines[actor][slot][i]
						state.Upgrades[actor][slot][i], state.Upgrades[actor][slot][j] = state.Upgrades[actor][slot][j], state.Upgrades[actor][slot][i]
					}
				}
			}
		}
	}
	return state
}

func commonHAuditStarts(fresh []proto.State) []proto.State {
	out := []proto.State{}
	for _, i := range []int{0, 2, 1} {
		if i >= len(fresh) || !hybridLegal(fresh[i]) {
			continue
		}
		duplicate := false
		for _, state := range out {
			duplicate = duplicate || commonHAuditCanonicalSeed(state) == commonHAuditCanonicalSeed(fresh[i])
		}
		if !duplicate {
			out = append(out, fresh[i])
		}
		if len(out) == 2 {
			break
		}
	}
	return out
}

func (g *commonHAuditGuard) evaluate(s proto.State, gradient bool) (float64, [4][10]float64, error) {
	if g.Formula >= g.FormulaMax || (gradient && g.Gradient >= g.GradMax) {
		return 0, [4][10]float64{}, errProgressiveDeadline
	}
	g.Formula++
	if gradient {
		g.Gradient++
	}
	return g.guard.evaluate(s, gradient)
}

func commonHAudit(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, initial proto.State, plan []commonHAuditTarget, policy []feasibleCandidate, global time.Time) (*r2World, []feasibleCandidate) {
	t.Helper()
	at := time.Now()
	deadline := at.Add(45 * time.Second)
	if global.Before(deadline) {
		deadline = global
	}
	w, err := newR2World(factory, req, base, true)
	if err != nil {
		t.Fatal(err)
	}
	w.feasibleWorld.numericReuse = false
	pool := map[string]feasibleCandidate{}
	formula, gradient, completed, started, unavailable := 0, 0, 0, 0, 0
	stages, stageCalls, duplicateSlots := 0, 0, 0
	emitFeasible(map[string]any{"kind": "common_h_audit_plan", "targets": plan,
		"target_limit": 8, "starts_per_available_target": 2, "stage_limit": 48,
		"formula_limit": 120000, "gradient_limit": 40000, "seconds_limit": 45,
		"selection":             "frozen ranks2/3 and one both-nonleader move per actor pair; no old controls",
		"starts":                "independent request-main seed and current-formula gradient/main seed; no warm bank",
		"policy_already_frozen": true})
	for i, target := range plan {
		if !time.Now().Before(deadline) || formula >= 120000 || gradient >= 40000 {
			break
		}
		e, resolveErr := w.get(target.Packages)
		if resolveErr != nil {
			t.Fatal(resolveErr)
		}
		if e == nil {
			unavailable++
			emitFeasible(map[string]any{"kind": "common_h_audit_unavailable", "target": i, "codes": w.metadata[theoryteams.Key(target.Packages)]})
			continue
		}
		if !time.Now().Before(deadline) {
			break
		}
		_, grad, gradientErr := w.objective(e)(initial, true)
		if gradientErr != nil {
			t.Fatal(gradientErr)
		}
		formula++
		gradient++
		fresh := hybridFresh(initial, grad)
		seeds := commonHAuditStarts(fresh)
		duplicateSlots += 2 - len(seeds)
		if len(seeds) < 2 {
			emitFeasible(map[string]any{"kind": "common_h_audit_duplicate_seed", "target": i, "skipped_slots": 2 - len(seeds), "reason": "independent generated starts coincide; no duplicate attempt counted"})
		}
		for seed, state := range seeds {
			if !time.Now().Before(deadline) || formula >= 120000 || gradient >= 40000 {
				break
			}
			started++
			pointAt := time.Now()
			guard := commonHAuditGuard{guard: hybridGuard{objective: w.objective(e), deadline: deadline}, FormulaMax: 120000 - formula, GradMax: 40000 - gradient}
			attemptStages := 0
			stageCalls++
			first, stop := proto.FastWhole(guard.evaluate, state, basicConfig(80), proto.FastConfig{Passes: 1, InnerIterations: 8})
			if stop == nil {
				attemptStages++
				stageCalls++
				line, next := proto.SlotLines(guard.evaluate, first.State, basicConfig(80), proto.SlotLineConfig{Passes: 1, InnerIterations: 8})
				stop = next
				if stop == nil {
					attemptStages++
					stageCalls++
					_, stop = proto.FastWhole(guard.evaluate, line.State, basicConfig(100), proto.FastConfig{Passes: 1, InnerIterations: 12, MainPairs: true})
					if stop == nil {
						attemptStages++
					}
				}
			}
			hybridAcceptStop(t, stop)
			formula += guard.Formula
			gradient += guard.Gradient
			stages += attemptStages
			if attemptStages == 3 {
				completed++
			}
			var candidate any
			if guard.guard.hasBest {
				c := feasibleCandidate{target.Packages, guard.guard.best, guard.guard.value, e.family}
				hybridOffer(pool, c)
				candidate = w.row(c)
			}
			emitFeasible(map[string]any{"kind": "common_h_audit_attempt", "target": i, "seed": seed,
				"distinct_seed_count": len(seeds), "completed_stages": attemptStages, "candidate": candidate,
				"seconds": time.Since(pointAt).Seconds(), "formula": guard.Formula, "gradient": guard.Gradient})
		}
	}
	rows := r2Sorted(pool)
	var best any
	gain := 0.0
	if len(rows) > 0 {
		best = w.row(rows[0])
		gain = rows[0].value - policy[0].value
	}
	emitFeasible(map[string]any{"kind": "common_h_audit_summary", "seconds": time.Since(at).Seconds(),
		"model_seconds": w.modelSeconds, "work": w.work, "formula_guard_count": formula, "gradient_guard_count": gradient,
		"planned_targets": len(plan), "unavailable_targets": unavailable, "planned_attempts": 2 * len(plan),
		"started_attempts": started, "completed_attempts": completed, "not_completed_slots": 2*len(plan) - completed,
		"pending_attempts": 2*(len(plan)-unavailable) - completed - duplicateSlots, "unavailable_attempts": 2 * unavailable,
		"duplicate_seed_slots_skipped": duplicateSlots,
		"stage_calls":                  stageCalls, "completed_stage_calls": stages, "best": best, "signed_difference_from_policy": gain,
		"rescue_gain": math.Max(0, gain), "credited_to_policy": false, "is_oracle": false})
	return w, rows
}

func runCommonHStudy(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, original [4]domain.Package, options []domain.Package, initial proto.State) {
	at := time.Now()
	global := at.Add(300 * time.Second)
	cfg, err := commonHConfiguration(os.Getenv("GTT_COMMON_H_DEPTH"), len(options))
	if err != nil {
		t.Fatal(err)
	}
	initial = proto.Seed(initial.Mains, [4][10]float64{}, 0, 45)
	h := runCommonH(t, factory, req, base, original, options, initial, cfg, global)
	policy := r2Sorted(h.pool)
	first := h.firstPass
	plan := commonHAuditPlan(h.pool, h.aliases, options)
	if len(plan) > 8 {
		t.Fatal("small audit plan exceeded declared limit")
	}
	firstValue := 0.0
	if len(first) > 0 {
		firstValue = first[0].value
	}
	cause := "first_refinement_not_completed"
	if len(first) > 0 {
		cause = "same_first_full_leader_value"
		if policy[0].value > firstValue+1e-9*math.Max(1, math.Abs(firstValue)) {
			cause = "continuation_improved_allocation_or_existing_family"
			found := false
			for _, row := range first {
				found = found || row.family == policy[0].family
			}
			if !found {
				cause = "continuation_discovered_new_winning_family"
			}
		}
	}
	emitFeasible(map[string]any{"kind": "common_h_first_full_comparison", "first_lower": firstValue,
		"full_lower": policy[0].value, "diagnosis": cause, "same_captured_universe": true,
		"continuation_changes_route_after_refinement":   true,
		"general_fallback":                              "explicit second-pass continuation, already measured; no character-specific repair",
		"declared_material_diagnostic_trigger_fraction": 0.005,
		"material_trigger_fired":                        len(first) > 0 && policy[0].value-firstValue > 0.005*math.Abs(firstValue),
		"trigger_is_acceptable_loss_or_safe_stop":       false})
	policyBefore := hybridCopy(h.pool)
	w, audited := commonHAudit(t, factory, req, base, initial, plan, policy, global)
	for family, before := range policyBefore {
		after := h.pool[family]
		if after.state != before.state || after.value != before.value || after.family != before.family || theoryteams.Key(after.packages) != theoryteams.Key(before.packages) {
			t.Fatal("independent audit changed frozen policy")
		}
	}
	// Old tuples/states are deserialized only now, after both policy and audit.
	knownAt := time.Now()
	before := w.work
	knownDeadline := time.Now().Add(30 * time.Second)
	if global.Before(knownDeadline) {
		knownDeadline = global
	}
	// The legacy point checker expects every selected family to be in policy.
	// New audit-only families remain separate, without an invented policy value.
	progressiveKnown(t, w, policy, policy, knownDeadline)
	emitFeasible(map[string]any{"kind": "common_h_post_selection_known_cost", "seconds": time.Since(knownAt).Seconds(), "work": difference(w.work, before),
		"selected_formula_scope": "frozen policy leader/runner only", "separate_audit_family_count": len(audited)})
	for _, checkpoint := range []struct {
		name string
		rows []feasibleCandidate
	}{{"first", first}, {"full", policy}} {
		if len(checkpoint.rows) == 0 || !time.Now().Before(global) {
			emitFeasible(map[string]any{"kind": "common_h_replay_pending", "checkpoint": checkpoint.name})
			continue
		}
		c := checkpoint.rows[0]
		e, err := w.get(c.packages)
		if err != nil || e == nil {
			t.Fatal("frozen leader replay unavailable", err)
		}
		value, gradient, err := w.objective(e)(c.state, true)
		if err != nil || math.Abs(value-c.value) > 1e-9*math.Max(1, math.Abs(value)) {
			t.Fatal("frozen leader replay differs", value, c.value, err)
		}
		emitFeasible(map[string]any{"kind": "common_h_leader_replay", "checkpoint": checkpoint.name,
			"candidate": w.row(c), "replayed_dps": value, "gradient": gradient})
	}
	boundaries, opaque := []string{}, []string{}
	for code := range h.w.boundaries {
		boundaries = append(boundaries, code)
	}
	for code := range h.w.opaque {
		opaque = append(opaque, code)
	}
	sort.Strings(boundaries)
	sort.Strings(opaque)
	emitFeasible(map[string]any{"kind": "common_h_study_summary", "seconds": time.Since(at).Seconds(),
		"first_lower": firstValue, "full_lower": policy[0].value, "policy_boundaries": boundaries, "policy_opaque_reasons": opaque,
		"offline_guard_seconds": 300, "fresh_capture_calls_inside_study": 0, "ordinary_finalists": 0,
		"source_upper": "unbounded", "outer_upper": "unbounded", "installed": false})
}

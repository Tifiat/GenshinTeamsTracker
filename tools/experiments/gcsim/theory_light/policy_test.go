package main

// Research only. The adapter leaves the pinned numerical core intact and
// switches only the two pass-boundary deep bundles. No character-specific rule.
import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math"
	"sort"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

const lightOverallSeconds = 360
const lightAuditSeconds = 29 // cold audit model plus four independent 7s slots
const lightChecksSeconds = 12
const lightTargetSeconds = 7
const lightAttemptSeconds = 3
const lightTargetFormula = 30000
const lightTargetGradient = 7500

type lightObservation struct {
	SkipDeep bool
	Seconds  float64
	Count    int
}

func lightDeepEnabled(h *hybridRun) bool {
	return h.researchLight == nil || !h.researchLight.SkipDeep
}

// Explicitly serialize numerical state, not candidate structs' unexported
// fields. Clock-only observation accounting is intentionally outside this hash.
func lightFingerprint(h *hybridRun) [32]byte {
	candidates := func(rows []feasibleCandidate) []any {
		out := []any{}
		for _, c := range rows {
			out = append(out, []any{c.packages, c.state, c.value, c.family})
		}
		return out
	}
	var route []byte
	if h.w.route != nil {
		route = h.w.route.Sum(nil)
	}
	raw, err := json.Marshal([]any{candidates(r2Sorted(h.pool)), candidates(h.bank), h.initial,
		h.refined, h.screened, h.visited, h.aliases, h.unavailable, h.curve, h.sweeps,
		h.stages, h.w.work, h.w.extra, route, h.phase, fmt.Sprint(h.best),
		h.fullSweeps, h.attemptedSweeps, h.transferred, h.independent,
		h.completedPasses, h.refinedPasses, h.aliasHits})
	if err != nil {
		panic(err)
	}
	return sha256.Sum256(raw)
}

func lightObserve(h *hybridRun, label string, observer func(string) []feasibleCandidate) []feasibleCandidate {
	at := time.Now()
	before := lightFingerprint(h)
	rows := observer(label)
	if lightFingerprint(h) != before {
		panic("pre-deep observer mutated search state")
	}
	if h.researchLight != nil {
		h.researchLight.Seconds += time.Since(at).Seconds()
		h.researchLight.Count++
	}
	return rows
}

func lightPassRefinement(h *hybridRun, prefix string) error {
	if h.researchLight != nil {
		lightObserve(h, h.name+"_pre_deep_"+prefix, h.snapshot)
		if !h.alive() {
			return errProgressiveDeadline
		}
	}
	if !lightDeepEnabled(h) {
		return nil
	}
	return h.finalRefinement(prefix)
}

func lightPolicyStopReason(h *hybridRun, err error) string {
	if reason := commonHWorkStop(h); reason != "" {
		return reason
	}
	if !time.Now().Before(h.deadline) {
		return "policy_or_global_wall_guard_including_observations"
	}
	if err != nil {
		return "policy_or_global_wall_guard"
	}
	return ""
}

func runLightPolicy(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, original [4]domain.Package, options []domain.Package, initial proto.State, skip bool, global time.Time) *hybridRun {
	t.Helper()
	at := time.Now()
	cfg, err := commonHConfiguration("full", len(options))
	if err != nil {
		t.Fatal(err)
	}
	name, seconds := "H_baseline", 180
	if skip {
		name, seconds = "H_light", 135
	}
	w, err := newR2World(factory, req, base, true)
	if err != nil {
		t.Fatal(err)
	}
	initial = proto.Seed(initial.Mains, [4][10]float64{}, 0, 45)
	h := newHybrid(w, initial, name, true, global, seconds)
	h.started = at
	h.deadline = at.Add(time.Duration(seconds) * time.Second)
	if global.Before(h.deadline) {
		h.deadline = global
	}
	h.researchH = &cfg
	h.researchLight = &lightObservation{SkipDeep: skip}
	emitFeasible(map[string]any{"kind": "light_policy_configuration", "variant": name,
		"wall_seconds_limit": seconds, "common_configuration": cfg, "skip_pass_deep_bundles": skip,
		"shallow_starts_and_sweep_winners_unchanged": true, "cold_model_and_context_caches": true,
		"numeric_solution_cache": false, "policy_inputs": "same request mains, generated starts and catalog; no history or other policy state"})
	err = h.search(original, options)
	searchSeconds := time.Since(at).Seconds()
	hybridAcceptStop(t, err)
	rows := lightObserve(h, name, h.snapshot)
	if len(rows) == 0 {
		t.Fatal("policy found no legal full-budget candidate")
	}
	reason := lightPolicyStopReason(h, err)
	complete := reason == "" && h.completedPasses == 2 && (skip || h.refinedPasses == 2)
	emitFeasible(map[string]any{"kind": "light_policy_result", "variant": name, "seconds": time.Since(at).Seconds(),
		"search_seconds": searchSeconds, "observation_seconds": h.researchLight.Seconds, "observation_count": h.researchLight.Count,
		"policy_guard_seconds": seconds, "best": w.row(rows[0]), "stop_reason": reason,
		"complete": complete, "wall_guard_hit": !time.Now().Before(h.deadline),
		"completed_catalog_passes": h.completedPasses, "completed_deep_passes": h.refinedPasses,
		"planned_sweeps": 16, "completed_sweeps": h.fullSweeps,
		"route_sha256": fmt.Sprintf("%x", w.route.Sum(nil)), "source_upper": "unbounded", "outer_upper": "unbounded"})
	return h
}

type lightAuditTarget struct {
	Packages                [4]domain.Package
	Reason                  string
	Actors, Ranks           [2]int
	BaselineFamily          string
	ExpectedFamily          string
	BaselineLower           *float64
	LightLower              *float64
	BaselineRank, LightRank int
}

// Selection is frozen after both policies, before any audit resolve. Family IDs
// are exact bound-program identities in the one shared captured universe.
// Absence has no invented zero value; aliases do not create a missing family.
func lightAuditPlan(light, baseline *hybridRun, options []domain.Package, reference float64) []lightAuditTarget {
	out := []lightAuditTarget{}
	seen := map[string]bool{}
	add := func(target lightAuditTarget) bool {
		key := theoryteams.Key(target.Packages)
		if seen[key] {
			return false
		}
		for _, h := range []*hybridRun{light, baseline} {
			if family := h.visited[key]; family != "" {
				if target.ExpectedFamily != "" && target.ExpectedFamily != family {
					panic("cold policy tuple family identities disagree")
				}
				target.ExpectedFamily = family
			}
		}
		seen[key] = true
		out = append(out, target)
		return true
	}
	lr, br := r2Sorted(light.pool), r2Sorted(baseline.pool)
	if len(lr) == 0 || len(br) == 0 {
		return out
	}
	anchor := theoryteams.Key(lr[0].packages)
	for _, p := range hybridPairPlan(light.pool, light.aliases, options) {
		if p.Anchor == anchor {
			add(lightAuditTarget{Packages: p.Packages, Reason: "reserved_both_nonleader_from_frozen_light_leader", Actors: p.Actors, Ranks: p.Ranks})
			break
		}
	}
	lrank, brank := map[string]int{}, map[string]int{}
	for i, c := range lr {
		lrank[c.family] = i + 1
	}
	for i, c := range br {
		brank[c.family] = i + 1
	}
	target := func(c feasibleCandidate, reason string) lightAuditTarget {
		value := c.value
		x := lightAuditTarget{Packages: c.packages, Reason: reason, Actors: [2]int{-1, -1}, BaselineFamily: c.family,
			ExpectedFamily: c.family, BaselineLower: &value, BaselineRank: brank[c.family], LightRank: lrank[c.family]}
		if old, ok := light.pool[c.family]; ok {
			v := old.value
			x.LightLower = &v
		}
		return x
	}
	// Every category gets at most one slot. A missing direction is not padded by
	// repeats; fallback uses the next distinct baseline tuple and is labeled.
	selectOne := func(rows []feasibleCandidate, reason string) {
		for _, c := range rows {
			if add(target(c, reason)) {
				return
			}
		}
		for _, c := range br {
			if add(target(c, reason+"_fallback_next_baseline_tuple")) {
				return
			}
		}
	}
	missing, shared := []feasibleCandidate{}, []feasibleCandidate{}
	for _, c := range br {
		if _, ok := light.pool[c.family]; !ok {
			missing = append(missing, c)
		} else {
			shared = append(shared, c)
		}
	}
	selectOne(missing, "strongest_baseline_family_unseen_by_light")
	sort.Slice(shared, func(i, j int) bool {
		di, dj := shared[i].value-light.pool[shared[i].family].value, shared[j].value-light.pool[shared[j].family].value
		if di != dj {
			return di > dj
		}
		return shared[i].family < shared[j].family
	})
	underestimated := []feasibleCandidate{}
	for _, c := range shared {
		if c.value > light.pool[c.family].value {
			underestimated = append(underestimated, c)
		}
	}
	selectOne(underestimated, "largest_shared_family_lower_bound_underestimate")
	shifted := []feasibleCandidate{}
	for _, c := range shared {
		if math.Max(c.value, light.pool[c.family].value) >= 0.97*reference && lrank[c.family] != brank[c.family] {
			shifted = append(shifted, c)
		}
	}
	sort.Slice(shifted, func(i, j int) bool {
		di, dj := math.Abs(float64(lrank[shifted[i].family]-brank[shifted[i].family])), math.Abs(float64(lrank[shifted[j].family]-brank[shifted[j].family]))
		if di != dj {
			return di > dj
		}
		return shifted[i].family < shifted[j].family
	})
	selectOne(shifted, "largest_rank_displacement_in_shared_practical_group")
	return out
}

func lightMinDeadline(a, b time.Time) time.Time {
	if a.Before(b) {
		return a
	}
	return b
}

func lightAudit(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, initial proto.State, plan []lightAuditTarget, reference float64, global time.Time) (*r2World, []feasibleCandidate) {
	t.Helper()
	at := time.Now()
	deadline := lightMinDeadline(at.Add(lightAuditSeconds*time.Second), global)
	w, err := newR2World(factory, req, base, true)
	if err != nil {
		t.Fatal(err)
	}
	w.numericReuse = false
	pool := map[string]feasibleCandidate{}
	completed, started, unavailable, pending := 0, 0, 0, 0
	targetWallHits := 0
	for i, target := range plan {
		targetAt := time.Now()
		targetDeadline := lightMinDeadline(targetAt.Add(lightTargetSeconds*time.Second), deadline)
		if !targetAt.Before(deadline) {
			pending++
			emitFeasible(map[string]any{"kind": "light_audit_pending", "target": i, "reason": "audit_or_global_wall_guard"})
			continue
		}
		resolveAt := time.Now()
		e, err := w.get(target.Packages)
		resolveSeconds := time.Since(resolveAt).Seconds()
		if err != nil {
			t.Fatal(err)
		}
		if !time.Now().Before(targetDeadline) {
			pending++
			emitFeasible(map[string]any{"kind": "light_audit_pending", "target": i, "reason": "target_or_audit_wall_guard_during_resolve", "resolve_seconds": resolveSeconds, "seconds": time.Since(targetAt).Seconds(), "availability_not_classified_after_deadline": true})
			continue
		}
		if e == nil {
			if target.ExpectedFamily != "" {
				t.Fatal("cold audit expected family became unavailable", i, target.ExpectedFamily)
			}
			unavailable++
			emitFeasible(map[string]any{"kind": "light_audit_unavailable", "target": i, "codes": w.metadata[theoryteams.Key(target.Packages)], "resolve_seconds": resolveSeconds})
			continue
		}
		if target.ExpectedFamily != "" && e.family != target.ExpectedFamily {
			t.Fatal("cold audit family identity differs", i, e.family, target.ExpectedFamily)
		}
		bootstrap := commonHAuditGuard{FormulaMax: 1, GradMax: 1, guard: hybridGuard{objective: w.objective(e), deadline: targetDeadline}}
		_, gradient, stop := bootstrap.evaluate(initial, true)
		hybridAcceptStop(t, stop)
		if stop != nil {
			pending++
			emitFeasible(map[string]any{"kind": "light_audit_pending", "target": i, "reason": "target_wall_guard_during_bootstrap"})
			continue
		}
		formula, grad := bootstrap.Formula, bootstrap.Gradient
		// Independent request-main and current-formula gradient/main starts. Never a
		// selected allocation, even when the target was selected from baseline output.
		seeds := commonHAuditStarts(hybridFresh(initial, gradient))
		if len(seeds) < 2 {
			emitFeasible(map[string]any{"kind": "light_audit_duplicate_start", "target": i, "distinct_starts": len(seeds)})
		}
		for s, state := range seeds {
			started++
			attemptAt := time.Now()
			guard := commonHAuditGuard{FormulaMax: min(15000, lightTargetFormula-formula), GradMax: min(3750, lightTargetGradient-grad),
				guard: hybridGuard{objective: w.objective(e), deadline: lightMinDeadline(attemptAt.Add(lightAttemptSeconds*time.Second), targetDeadline)}}
			stages := 0
			first, stop := proto.FastWhole(guard.evaluate, state, basicConfig(40), proto.FastConfig{Passes: 1, InnerIterations: 4})
			if stop == nil {
				stages++
				line, next := proto.SlotLines(guard.evaluate, first.State, basicConfig(40), proto.SlotLineConfig{Passes: 1, InnerIterations: 4})
				stop = next
				if stop == nil {
					stages++
					_, stop = proto.FastWhole(guard.evaluate, line.State, basicConfig(60), proto.FastConfig{Passes: 1, InnerIterations: 6, MainPairs: true})
					if stop == nil {
						stages++
					}
				}
			}
			hybridAcceptStop(t, stop)
			formula += guard.Formula
			grad += guard.Gradient
			reason := ""
			if stop != nil {
				reason = "attempt_or_target_or_global_wall_guard"
				if guard.Formula >= guard.FormulaMax {
					reason = "per_attempt_formula_quota"
				} else if guard.Gradient >= guard.GradMax {
					reason = "per_attempt_gradient_quota"
				}
			}
			if reason == "" && !time.Now().Before(guard.guard.deadline) {
				reason = "attempt_or_target_or_global_wall_guard_after_last_call"
			}
			if stages == 3 && reason == "" {
				completed++
			}
			var candidate any
			if guard.guard.hasBest {
				c := feasibleCandidate{target.Packages, guard.guard.best, guard.guard.value, e.family}
				hybridOffer(pool, c)
				candidate = w.row(c)
			}
			emitFeasible(map[string]any{"kind": "light_audit_attempt", "target": i, "seed": s, "start": state, "candidate": candidate,
				"completed_stages": stages, "stop_reason": reason, "seconds": time.Since(attemptAt).Seconds(), "formula": guard.Formula, "gradient": guard.Gradient})
		}
		targetWallHit := !time.Now().Before(targetDeadline)
		if targetWallHit {
			targetWallHits++
		}
		emitFeasible(map[string]any{"kind": "light_audit_target_result", "target": i, "seconds": time.Since(targetAt).Seconds(),
			"resolve_seconds": resolveSeconds, "wall_guard_hit": targetWallHit,
			"formula": formula, "gradient": grad, "distinct_starts": len(seeds), "tuple_quota_formula": lightTargetFormula, "tuple_quota_gradient": lightTargetGradient})
	}
	rows := r2Sorted(pool)
	var best any
	if len(rows) > 0 {
		best = w.row(rows[0])
	}
	emitFeasible(map[string]any{"kind": "light_audit_summary", "seconds": time.Since(at).Seconds(), "model_seconds": w.modelSeconds,
		"complete":       completed == 2*len(plan) && unavailable == 0 && pending == 0 && targetWallHits == 0 && time.Now().Before(deadline),
		"wall_guard_hit": !time.Now().Before(deadline), "target_wall_guard_hits": targetWallHits,
		"planned_targets": len(plan), "unavailable_targets": unavailable, "pending_targets": pending, "started_attempts": started, "completed_attempts": completed,
		"best": best, "frozen_reference": reference, "work": w.work, "policy_rescue": false, "is_oracle": false, "complete_exclusion_proof": false})
	return w, rows
}

func runLightStudy(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, original [4]domain.Package, options []domain.Package, initial proto.State) {
	at := time.Now()
	global := at.Add(lightOverallSeconds * time.Second)
	// A separate hard watchdog covers even an unexpectedly slow in-flight resolve.
	// Partial records are flushed as emitted and the Python owner cleans on error.
	watchdog := time.AfterFunc(lightOverallSeconds*time.Second, func() {
		emitFeasible(map[string]any{"kind": "light_study_hard_stop", "reason": "overall_offline_360s_guard", "seconds": time.Since(at).Seconds()})
		panic("research overall offline 360s guard")
	})
	defer watchdog.Stop()
	initial = proto.Seed(initial.Mains, [4][10]float64{}, 0, 45)
	light := runLightPolicy(t, factory, req, base, original, options, initial, true, global)
	baseline := runLightPolicy(t, factory, req, base, original, options, initial, false, global)
	lightBefore, baselineBefore := lightFingerprint(light), lightFingerprint(baseline)
	lr, br := r2Sorted(light.pool), r2Sorted(baseline.pool)
	reference := math.Max(lr[0].value, br[0].value)
	plan := lightAuditPlan(light, baseline, options, reference)
	if len(plan) > 4 {
		t.Fatal("audit target cap exceeded")
	}
	pairCoverage := "missing_no_available_pair_in_frozen_plan"
	if len(plan) > 0 && plan[0].Reason == "reserved_both_nonleader_from_frozen_light_leader" {
		pairCoverage = "reserved_first_target"
	}
	emitFeasible(map[string]any{"kind": "light_audit_plan", "targets": plan, "frozen_reference": reference, "bands": []float64{0.02, 0.03},
		"both_nonleader_coverage": pairCoverage,
		"target_limit":            4, "per_tuple_seconds": lightTargetSeconds, "per_tuple_formula": lightTargetFormula, "per_tuple_gradient": lightTargetGradient,
		"per_start_seconds": lightAttemptSeconds, "per_start_formula_max": 15000, "per_start_gradient_max": 3750, "starts_per_available_tuple_max": 2,
		"audit_seconds": lightAuditSeconds, "selection_provenance": "frozen H-light pair preferences and baseline comparison; neither history nor allocation seeds",
		"shared_group_reference_never_rebased_after_audit": true, "no_quota_transfer": true})
	w, audited := lightAudit(t, factory, req, base, initial, plan, reference, global)
	checksAt := time.Now()
	checksDeadline := lightMinDeadline(checksAt.Add(lightChecksSeconds*time.Second), global)
	replayed := 0
	for _, p := range []struct {
		name string
		c    feasibleCandidate
	}{{"H_light", lr[0]}, {"H_baseline", br[0]}} {
		if !time.Now().Before(checksDeadline) {
			emitFeasible(map[string]any{"kind": "light_replay_pending", "variant": p.name})
			continue
		}
		resolveAt := time.Now()
		e, err := w.get(p.c.packages)
		resolveSeconds := time.Since(resolveAt).Seconds()
		if !time.Now().Before(checksDeadline) {
			emitFeasible(map[string]any{"kind": "light_replay_pending", "variant": p.name, "reason": "checks_wall_guard_during_resolve", "resolve_seconds": resolveSeconds})
			continue
		}
		if err != nil || e == nil {
			t.Fatal("frozen leader replay unavailable", err)
		}
		if e.family != p.c.family {
			t.Fatal("cold replay family identity differs", p.name, e.family, p.c.family)
		}
		guard := hybridGuard{objective: w.objective(e), deadline: checksDeadline}
		value, gradient, err := guard.evaluate(p.c.state, true)
		if err == errProgressiveDeadline || !time.Now().Before(checksDeadline) {
			emitFeasible(map[string]any{"kind": "light_replay_pending", "variant": p.name, "reason": "checks_wall_guard_during_evaluation"})
			continue
		}
		if err != nil || math.Abs(value-p.c.value) > 1e-9*math.Max(1, math.Abs(value)) {
			t.Fatal("frozen leader replay differs", value, p.c.value, err)
		}
		for _, actor := range gradient {
			for _, v := range actor {
				if math.IsNaN(v) || math.IsInf(v, 0) {
					t.Fatal("nonfinite replay gradient")
				}
			}
		}
		replayed++
		emitFeasible(map[string]any{"kind": "light_leader_replay", "variant": p.name, "candidate": w.row(p.c), "replayed_dps": value, "gradient": gradient})
	}
	if lightFingerprint(light) != lightBefore || lightFingerprint(baseline) != baselineBefore {
		t.Fatal("audit changed frozen policy")
	}
	emitFeasible(map[string]any{"kind": "light_study_summary", "seconds": time.Since(at).Seconds(), "checks_seconds": time.Since(checksAt).Seconds(),
		"checks_guard_hit":      !time.Now().Before(checksDeadline),
		"offline_guard_seconds": lightOverallSeconds, "light_lower": lr[0].value, "baseline_lower": br[0].value, "frozen_reference": reference,
		"leader_replays_completed": replayed, "audit_families": len(audited), "policy_unchanged_after_audit": true,
		"fresh_capture_calls_inside_study": 0, "ordinary_finalists": 0, "source_upper": "unbounded", "outer_upper": "unbounded", "installed": false})
}

package main

// Separate standalone policy, extra reference effort, and known point checks.
// This harness never asks for an additional capture or a finalist simulation.
import (
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"sort"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	proto "genshinteamstracker/native/gcsim_optimizer/internal/theoryprototype"
	"genshinteamstracker/native/gcsim_optimizer/internal/theoryteams"
)

func progressiveRanks(n int) []int {
	seen := map[int]bool{}
	out := []int{}
	for _, i := range []int{4, 5, n / 2, 3 * n / 4} {
		if i >= 0 && i < n && !seen[i] {
			seen[i] = true
			out = append(out, i)
		}
	}
	return out
}

func progressiveReason(codes []string) string {
	unique := map[string]bool{}
	for _, s := range codes {
		if s != "" {
			unique[s] = true
		}
	}
	keys := []string{}
	for s := range unique {
		keys = append(keys, s)
	}
	sort.Strings(keys)
	if len(keys) == 0 {
		return "unavailable_without_reported_reason"
	}
	return strings.Join(keys, " | ")
}

var errProgressiveDeadline = errors.New("reference research budget exhausted")

type progressiveGuard struct {
	objective proto.Objective
	deadline  time.Time
	now       func() time.Time
	best      proto.State
	value     float64
	hasBest   bool
}

func (b *progressiveGuard) evaluate(s proto.State, gradient bool) (float64, [4][10]float64, error) {
	if !b.now().Before(b.deadline) {
		return 0, [4][10]float64{}, errProgressiveDeadline
	}
	v, g, err := b.objective(s, gradient)
	if err == nil && !math.IsNaN(v) && !math.IsInf(v, 0) && (!b.hasBest || v > b.value) && s.Validate(45, true) == nil {
		b.best, b.value, b.hasBest = s, v, true
	}
	return v, g, err
}

func progressiveReference(w *r2World, e *feasibleEntry, start proto.State, deadline time.Time) (proto.State, float64, bool, int, error) {
	guard := progressiveGuard{objective: w.objective(e), deadline: deadline, now: time.Now}
	state := start
	stages := 0
	first, err := proto.FastWhole(guard.evaluate, state, basicConfig(120), proto.FastConfig{Passes: 2, InnerIterations: 8})
	if err == nil {
		state = first.State
		stages++
		lines, lineErr := proto.SlotLines(guard.evaluate, state, basicConfig(140), proto.SlotLineConfig{Passes: 2, InnerIterations: 8})
		err = lineErr
		if err == nil {
			state = lines.State
			stages++
			_, err = proto.FastWhole(guard.evaluate, state, basicConfig(160), proto.FastConfig{Passes: 2, InnerIterations: 16, MainPairs: true})
			if err == nil {
				stages++
			}
		}
	}
	if err != nil && !errors.Is(err, errProgressiveDeadline) {
		return guard.best, guard.value, guard.hasBest, stages, err
	}
	return guard.best, guard.value, guard.hasBest, stages, nil
}

func progressiveRanking(w *r2World, rows []feasibleCandidate) []any {
	out := []any{}
	for i, c := range rows {
		out = append(out, map[string]any{"rank": i + 1, "candidate": w.row(c)})
	}
	return out
}

func progressiveKnown(t *testing.T, w *r2World, policy, audited []feasibleCandidate, deadline ...time.Time) {
	expired := func(stage string, remaining int) bool {
		if len(deadline) == 0 || time.Now().Before(deadline[0]) {
			return false
		}
		emitFeasible(map[string]any{"kind": "progressive_known_pending", "stage": stage, "remaining_in_stage": remaining, "reason": "whole-study research deadline; checks are incomplete"})
		return true
	}
	if expired("load_known_points", -1) {
		return
	}
	path := os.Getenv("GTT_PROGRESSIVE_KNOWN")
	if path == "" {
		t.Fatal("known point comparisons require explicit provenance")
	}
	var known []struct {
		Label     string `json:"label"`
		Candidate struct {
			State    proto.State `json:"feasibility_witness"`
			Value    float64     `json:"formula_dps"`
			Family   string      `json:"formula_family"`
			Packages []struct {
				WearerKey string                     `json:"wearer_key"`
				Sets      []contracts.SetRequirement `json:"sets"`
			} `json:"packages"`
		} `json:"candidate"`
	}
	raw, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(raw, &known); err != nil {
		t.Fatal(err)
	}
	type point struct {
		label    string
		state    proto.State
		packages [4]domain.Package
		value    float64
		family   string
	}
	points := []point{}
	for _, row := range known {
		if len(row.Candidate.Packages) != 4 {
			t.Fatal("known point wearer count")
		}
		p := point{label: row.Label, value: row.Candidate.Value, family: row.Candidate.Family}
		for a, wearer := range w.req.Wearers {
			found := -1
			for j, old := range row.Candidate.Packages {
				if old.WearerKey == wearer.WearerKey {
					found = j
					p.packages[a] = domain.Package{Sets: old.Sets}
				}
			}
			if found < 0 {
				t.Fatal("known point wearer missing")
			}
			p.state.Mains[a] = row.Candidate.State.Mains[found]
			p.state.Lines[a] = row.Candidate.State.Lines[found]
			p.state.Upgrades[a] = row.Candidate.State.Upgrades[found]
		}
		if err = p.state.Validate(45, true); err != nil {
			t.Fatal(err)
		}
		points = append(points, p)
	}
	selected := map[string]feasibleCandidate{}
	for _, rows := range [][]feasibleCandidate{policy, audited} {
		for i := 0; i < min(2, len(rows)); i++ {
			selected[rows[i].family] = rows[i]
		}
	}
	keys := []string{}
	for key := range selected {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	for k, key := range keys {
		if expired("selected_leader_formulas", len(keys)-k) {
			return
		}
		leader := selected[key]
		e, err := w.get(leader.packages)
		if err != nil || e == nil {
			t.Fatal("leader formula unavailable", err)
		}
		best := leader
		label := "current_measured_candidate"
		sourceFamily := ""
		for i, p := range points {
			if expired("points_on_current_leader", len(points)-i) {
				return
			}
			v, _, err := w.objective(e)(p.state, false)
			if err != nil {
				t.Fatal(err)
			}
			if v > best.value {
				best.state, best.value = p.state, v
				label, sourceFamily = p.label, p.family
			}
		}
		policyValue := math.Inf(-1)
		for _, c := range policy {
			if c.family == key {
				policyValue = c.value
			}
		}
		emitFeasible(map[string]any{"kind": "progressive_known_on_leader", "known_point_count": len(points), "candidate": w.row(best), "policy_lower": policyValue, "improvement_over_policy_family": best.value - policyValue, "known_label": label, "known_source_family": sourceFamily, "same_saved_formula_family": sourceFamily == key, "role": "post-selection legal allocation point re-evaluated on leader formula; not a seed or oracle"})
	}
	for i, p := range points {
		if expired("known_package_controls", len(points)-i) {
			return
		}
		e, err := w.get(p.packages)
		if err != nil {
			t.Fatal(err)
		}
		if e == nil {
			emitFeasible(map[string]any{"kind": "progressive_known_control", "label": p.label, "available": false, "package_key": theoryteams.Key(p.packages)})
			continue
		}
		if expired("known_control_point_after_resolve", len(points)-i) {
			return
		}
		v, _, err := w.objective(e)(p.state, false)
		if err != nil {
			t.Fatal(err)
		}
		within := false
		for _, c := range policy {
			if c.family == e.family {
				within = true
			}
		}
		emitFeasible(map[string]any{"kind": "progressive_known_control", "label": p.label, "available": true, "candidate": w.row(feasibleCandidate{p.packages, p.state, v, e.family}), "saved_value": p.value, "same_saved_formula_family": p.family == e.family, "numeric_family_in_policy_neighborhood": within, "role": "comparison only; package tuple may be outside fixed-input neighborhood"})
	}
}

func runTheoryProgressive(t *testing.T, factory func() (*setcontext.NeutralModel, error), req contracts.OptimizerRequest, base *setcontext.Context, original [4]domain.Package, options []domain.Package, initial proto.State) {
	started := time.Now()
	w, err := newR2World(factory, req, base, true)
	if err != nil {
		t.Fatal(err)
	}
	// Contexts/families share source work; complete numerical solve caching is OFF.
	w.feasibleWorld.numericReuse = false
	actorName := map[string]string{"chiori_lunar_crystallize": "chiori", "bountiful_core": "nilou"}[os.Getenv("GTT_BOUNDS_CASE")]
	actor := -1
	for a, v := range req.Wearers {
		if v.WearerKey == actorName {
			actor = a
		}
	}
	if actor < 0 {
		t.Fatal("declared contrast wearer missing")
	}
	families := map[string]feasibleCandidate{}
	aliases := map[string][]string{}
	unavailable := map[string][]string{}
	seeds := map[string][]proto.State{}
	resolveSeconds, screenSeconds := 0.0, 0.0
	for _, option := range options {
		p := original
		p[actor] = option
		at := time.Now()
		e, err := w.get(p)
		resolveSeconds += time.Since(at).Seconds()
		if err != nil {
			t.Fatal(err)
		}
		key := theoryteams.Key(p)
		if e == nil {
			reason := progressiveReason(w.metadata[key])
			unavailable[reason] = append(unavailable[reason], key)
			continue
		}
		aliases[e.family] = append(aliases[e.family], key)
		if _, ok := families[e.family]; ok {
			continue
		}
		at = time.Now()
		seeds[e.family] = slackSeeds(w, e, initial)
		best := feasibleCandidate{packages: p, family: e.family, value: math.Inf(-1)}
		for _, s := range seeds[e.family] {
			r, err := proto.Optimize(w.objective(e), s, basicConfig(8))
			if err != nil {
				t.Fatal(err)
			}
			if r.Value > best.value {
				best.state, best.value = r.State, r.Value
			}
		}
		families[e.family] = best
		screenSeconds += time.Since(at).Seconds()
	}
	screenRows := r2Sorted(families)
	if len(screenRows) == 0 {
		t.Fatal("no resolved family in declared neighborhood")
	}
	screenElapsed := time.Since(started).Seconds()
	emitFeasible(map[string]any{"kind": "progressive_screen", "wearer": actorName, "input_anchor_key": theoryteams.Key(original), "anchor_origin": "fresh prepared request; saved winning control never substituted", "packages": len(options), "unique_families": len(screenRows), "aliases_by_family": aliases, "unavailable_by_reason": unavailable, "resolve_seconds": resolveSeconds, "screen_seconds": screenSeconds, "seconds": screenElapsed, "model_seconds": w.modelSeconds, "ranking": progressiveRanking(w, screenRows), "work": w.work, "reuse": w.extra, "final_solution_cache_enabled": false, "source_upper": "unbounded", "outer_upper": "unbounded"})
	mainStarted := time.Now()
	beforeMains := w.work
	for i := 0; i < min(4, len(screenRows)); i++ {
		old := screenRows[i]
		e, err := w.get(old.packages)
		if err != nil || e == nil {
			t.Fatal(err)
		}
		r, err := w.fast(e, old.state)
		if err != nil {
			t.Fatal(err)
		}
		if r.Value > old.value {
			old.state, old.value = r.State, r.Value
		}
		families[old.family] = old
	}
	mainSeconds := time.Since(mainStarted).Seconds()
	mainWork := difference(w.work, beforeMains)
	mainRows := r2Sorted(families)
	lineStarted := time.Now()
	beforeLines := w.work
	for i := 0; i < min(2, len(mainRows)); i++ {
		old := mainRows[i]
		e, err := w.get(old.packages)
		if err != nil || e == nil {
			t.Fatal(err)
		}
		r, err := w.alternating(e, old.state)
		if err != nil {
			t.Fatal(err)
		}
		if r.Value > old.value {
			old.state, old.value = r.State, r.Value
		}
		families[old.family] = old
	}
	lineSeconds := time.Since(lineStarted).Seconds()
	lineWork := difference(w.work, beforeLines)
	policyRows := r2Sorted(families)
	policySeconds := time.Since(started).Seconds()
	policyWork := w.work
	for _, c := range policyRows {
		if err = c.state.Validate(45, true); err != nil {
			t.Fatal(err)
		}
	}
	if w.extra.FastHits != 0 || w.extra.AlternatingHits != 0 || len(w.numericCache) != 0 {
		t.Fatal("completed solve cache must stay off")
	}
	emitFeasible(map[string]any{"kind": "progressive_policy", "ranking": progressiveRanking(w, policyRows), "best": w.row(policyRows[0]), "seconds": policySeconds, "screen_elapsed_seconds": screenElapsed, "mains_seconds": mainSeconds, "lines_seconds": lineSeconds, "mains_work": mainWork, "lines_work": lineWork, "work": policyWork, "reuse": w.extra, "mains_families": min(4, len(screenRows)), "deep_families": min(2, len(mainRows)), "final_solution_cache_enabled": false, "additional_audits_included": false, "scope": "standalone heuristic; one input-anchored wearer neighborhood, four-actor allocation; no global/top-K guarantee"})
	// The original policy map/rows remain frozen. Only this independent map is updated.
	audited := map[string]feasibleCandidate{}
	for k, c := range families {
		audited[k] = c
	}
	type auditItem struct {
		Rank   int    `json:"screen_rank"`
		Family string `json:"family"`
		Seed   int    `json:"fresh_seed"`
	}
	plan := []auditItem{}
	for _, i := range progressiveRanks(len(screenRows)) {
		for _, seed := range []int{1, 2} {
			plan = append(plan, auditItem{i + 1, screenRows[i].family, seed})
		}
	}
	emitFeasible(map[string]any{"kind": "progressive_reference_plan", "items": plan, "budget_seconds": 60, "ranking_origin": "frozen screen ranks before policy refinement", "starts_origin": "fresh generated initial states, no completed policy or saved-control state"})
	auditStart := time.Now()
	deadline := auditStart.Add(60 * time.Second)
	beforeAudit := w.work
	completed := 0
	pending := []auditItem{}
	for i, item := range plan {
		if !time.Now().Before(deadline) {
			pending = append(pending, plan[i:]...)
			break
		}
		old := screenRows[item.Rank-1]
		e, err := w.get(old.packages)
		if err != nil || e == nil {
			t.Fatal(err)
		}
		at := time.Now()
		before := w.work
		state, value, hasBest, stages, err := progressiveReference(w, e, seeds[item.Family][item.Seed], deadline)
		if err != nil {
			t.Fatal(err)
		}
		var candidate any
		if hasBest {
			c := old
			c.state, c.value = state, value
			candidate = w.row(c)
			if c.value > audited[c.family].value {
				audited[c.family] = c
			}
		}
		if stages == 3 {
			completed++
		} else {
			pending = append(pending, item)
		}
		emitFeasible(map[string]any{"kind": "progressive_reference_attempt", "item": item, "completed": stages == 3, "completed_stages": stages, "candidate": candidate, "seconds": time.Since(at).Seconds(), "work": difference(w.work, before), "budget_elapsed_seconds": time.Since(auditStart).Seconds()})
	}
	auditSeconds := time.Since(auditStart).Seconds()
	auditWork := difference(w.work, beforeAudit)
	auditRows := r2Sorted(audited)
	changes := []any{}
	for i, c := range auditRows {
		for j, p := range policyRows {
			if p.family == c.family && (i != j || c.value != p.value) {
				changes = append(changes, map[string]any{"family": c.family, "policy_rank": j + 1, "audited_rank": i + 1, "policy_lower": p.value, "audited_lower": c.value})
			}
		}
	}
	emitFeasible(map[string]any{"kind": "progressive_reference_summary", "best": w.row(auditRows[0]), "policy_best": w.row(policyRows[0]), "rescue_gain": auditRows[0].value - policyRows[0].value, "winner_family_changed": auditRows[0].family != policyRows[0].family, "ranking_changes": changes, "ranking": progressiveRanking(w, auditRows), "seconds": auditSeconds, "work": auditWork, "planned_attempts": len(plan), "completed_attempts": completed, "pending_attempts": pending, "budget_seconds": 60, "is_oracle": false})
	knownStart := time.Now()
	beforeKnown := w.work
	progressiveKnown(t, w, policyRows, auditRows)
	knownSeconds := time.Since(knownStart).Seconds()
	unavailableCount := 0
	for _, keys := range unavailable {
		unavailableCount += len(keys)
	}
	emitFeasible(map[string]any{"kind": "progressive_summary", "case": os.Getenv("GTT_BOUNDS_CASE"), "wearer": actorName, "packages": len(options), "available_aliases": len(options) - unavailableCount, "unique_families": len(screenRows), "unavailable": unavailableCount, "policy_lower": policyRows[0].value, "reference_lower": auditRows[0].value, "rescue_gain": auditRows[0].value - policyRows[0].value, "policy_seconds": policySeconds, "reference_seconds": auditSeconds, "known_point_seconds": knownSeconds, "known_point_work": difference(w.work, beforeKnown), "seconds": time.Since(started).Seconds(), "work": w.work, "reuse": w.extra, "source_upper": "unbounded", "outer_upper": "unbounded", "final_solution_cache_enabled": false, "fresh_capture_calls_inside_study": 0, "finalist_calls": 0, "full_cartesian_covered": false})
}

func TestProgressiveAuditRanks(t *testing.T) {
	for _, c := range []struct {
		n    int
		want string
	}{{0, "[]"}, {1, "[0]"}, {2, "[1]"}, {5, "[4 2 3]"}, {42, "[4 5 21 31]"}} {
		if got := fmt.Sprint(progressiveRanks(c.n)); got != c.want {
			t.Fatal(c.n, got, c.want)
		}
	}
	if progressiveReason([]string{"b", "a", "a"}) != "a | b" || progressiveReason(nil) != "unavailable_without_reported_reason" {
		t.Fatal("reason partition")
	}
}
func TestProgressiveDeadlineKeepsLegalProgress(t *testing.T) {
	start := proto.Seed(initialMains(), [4][10]float64{}, 0, 45)
	now := time.Unix(0, 0)
	calls := 0
	guard := progressiveGuard{now: func() time.Time { return now }, deadline: now.Add(time.Second), objective: func(s proto.State, g bool) (float64, [4][10]float64, error) {
		calls++
		return float64(calls), [4][10]float64{}, nil
	}}
	if _, _, err := guard.evaluate(start, false); err != nil || !guard.hasBest {
		t.Fatal("legal progress not saved", err)
	}
	illegal := start
	illegal.Upgrades[0][0][0] = 1000
	_, _, _ = guard.evaluate(illegal, false)
	if guard.best != start || guard.value != 1 {
		t.Fatal("illegal transient replaced witness")
	}
	now = guard.deadline
	if _, _, err := guard.evaluate(start, false); !errors.Is(err, errProgressiveDeadline) || calls != 2 || guard.best != start {
		t.Fatal("deadline must stop evaluation and retain witness", err, calls)
	}
}

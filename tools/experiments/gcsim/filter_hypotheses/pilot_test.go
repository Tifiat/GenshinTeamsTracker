package main

// Research-only overlay. All generated captures belong to managed scratch.
import (
	"context"
	"encoding/json"
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/allsets"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
	"math"
	"os"
	"path/filepath"
	"sort"
	"testing"
	"time"
)

type filterRow struct {
	Artifacts []struct {
		Wearer string `json:"wearer_key"`
		Slot   string `json:"slot"`
		ID     int64  `json:"artifact_id"`
	} `json:"artifacts"`
	DPS   float64 `json:"formula_dps,string"`
	Group string  `json:"set_group_key"`
	Rank  int     `json:"alternative_rank"`
}
type filterPoint struct {
	IDs [5]int64
	DPS float64
}
type filterStudy struct {
	Group, Wearer, Scope                                                           string
	Slots                                                                          [2]int
	PoolSizes                                                                      [2]int
	Nodes, Coordinates, K, LegalPoints, BoundCalls, BoundSkipped, DominanceSkipped int
	BoundScored, BoundSkippedLegal, SupportedBounds                                int
	BaselineSeconds, BoundSeconds, SignSeconds, DominanceSeconds                   float64
	Unresolved                                                                     bool
	BoundParity, DominanceParity                                                   bool
	Increasing, Decreasing                                                         []string
	BoundScope                                                                     string
	FamilyPairs, LegalFamilyPairs, LegalityScored                                  int
	LegalitySeconds                                                                float64
	LegalityParity                                                                 bool
}

func filterRead(path string, target any) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	return json.Unmarshal(b, target)
}
func filterLess(a, b filterPoint) bool {
	if a.DPS != b.DPS {
		return a.DPS > b.DPS
	}
	for i := range a.IDs {
		if a.IDs[i] != b.IDs[i] {
			return a.IDs[i] < b.IDs[i]
		}
	}
	return false
}
func filterKeep(points []filterPoint, row filterPoint, k int) []filterPoint {
	points = append(points, row)
	sort.Slice(points, func(i, j int) bool { return filterLess(points[i], points[j]) })
	if len(points) > k {
		points = points[:k]
	}
	return points
}
func filterSame(a, b []filterPoint) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i].IDs != b[i].IDs || math.Abs(a[i].DPS-b[i].DPS) > 1e-8 {
			return false
		}
	}
	return true
}
func filterDelta(ids [5]int64, vectors map[int64][]float64, ref []float64) []float64 {
	x := make([]float64, len(ref))
	for j, v := range ref {
		x[j] = -v
	}
	for _, id := range ids {
		for j, v := range vectors[id] {
			x[j] += v
		}
	}
	return x
}
func filterBox(ids [5]int64, slot int, pool []int64, vectors map[int64][]float64, ref []float64) ([]float64, []float64) {
	lo, hi := make([]float64, len(ref)), make([]float64, len(ref))
	for j, v := range ref {
		lo[j], hi[j] = -v, -v
	}
	for s, id := range ids {
		if s != slot {
			for j, v := range vectors[id] {
				lo[j] += v
				hi[j] += v
			}
			continue
		}
		for j := range ref {
			l, h := math.Inf(1), math.Inf(-1)
			for _, other := range pool {
				v := vectors[other][j]
				l = math.Min(l, v)
				h = math.Max(h, v)
			}
			lo[j] += l
			hi[j] += h
		}
	}
	for j := range lo {
		guard := 1e-12 * (1 + math.Max(math.Abs(lo[j]), math.Abs(hi[j])))
		lo[j] -= guard
		hi[j] += guard
	}
	return lo, hi
}
func filterWholeBox(ids [5]int64, slots [2]int, pools [2][]int64, vectors map[int64][]float64, ref []float64) ([]float64, []float64) {
	lo, hi := filterBox(ids, slots[1], pools[1], vectors, ref)
	for j := range ref {
		l, h := math.Inf(1), math.Inf(-1)
		for _, id := range pools[0] {
			v := vectors[id][j]
			l = math.Min(l, v)
			h = math.Max(h, v)
		}
		lo[j] += l - vectors[ids[slots[0]]][j]
		hi[j] += h - vectors[ids[slots[0]]][j]
	}
	return lo, hi
}
func filterDominated(pool []int64, vectors map[int64][]float64, inc, dec []bool, index *domain.Index, k int) map[int64]bool {
	removed := map[int64]bool{}
	for _, b := range pool {
		count := 0
		family, _ := index.ArtifactSetUID(b)
		for _, a := range pool {
			// Lower IDs also win ties. Do not claim strict improvement when a
			// capped coordinate merely permits a non-decreasing response.
			if a >= b {
				continue
			}
			other, _ := index.ArtifactSetUID(a)
			if family != other {
				continue
			}
			ok := true
			for j, v := range vectors[a] {
				if v > vectors[b][j] && !inc[j] || v < vectors[b][j] && !dec[j] {
					ok = false
					break
				}
			}
			if ok {
				count++
			}
			if count >= k {
				removed[b] = true
				break
			}
		}
	}
	return removed
}

// Build a same-bonus compatibility table from real representatives. Every pool
// item is already in its correct slot and is not owned by another fixed wearer;
// distinct slots cannot contain duplicate IDs. Thus legality depends only on
// the two set families, not on stats or the response-completeness flag. We still
// run the real validator on surviving leaves, not an approximate set rule.
func filterLegalPools(index *domain.Index, anchor [5]int64, slots [2]int, pools [2][]int64, valid func([5]int64) error) ([][]int64, int, int) {
	var families [2]map[string]int64
	for n, pool := range pools {
		families[n] = map[string]int64{}
		for _, id := range pool {
			uid, _ := index.ArtifactSetUID(id)
			families[n][uid] = id
		}
	}
	allowed := map[[2]string]bool{}
	legalPairs := 0
	for a, idA := range families[0] {
		for b, idB := range families[1] {
			ids := anchor
			ids[slots[0]], ids[slots[1]] = idA, idB
			if valid(ids) == nil {
				allowed[[2]string{a, b}] = true
				legalPairs++
			}
		}
	}
	byFamily := map[string][]int64{}
	for a := range families[0] {
		for _, b := range pools[1] {
			uid, _ := index.ArtifactSetUID(b)
			if allowed[[2]string{a, uid}] {
				byFamily[a] = append(byFamily[a], b)
			}
		}
	}
	result := make([][]int64, len(pools[0]))
	for n, id := range pools[0] {
		uid, _ := index.ArtifactSetUID(id)
		result[n] = byFamily[uid]
	}
	return result, len(families[0]) * len(families[1]), legalPairs
}

func filterPilot(t *testing.T, group string, index *domain.Index, p *formula.ArtifactProgram, anchor domain.Assignment, actor int, slots [2]int, pools [2][]int64, k int, scope string) filterStudy {
	t.Helper()
	vectors, ref, err := index.ArtifactVectors(actor, p.Coordinates())
	if err != nil {
		t.Fatal(err)
	}
	validator, err := index.PrepareLocalAssignmentValidator(anchor, actor)
	if err != nil {
		t.Fatal(err)
	}
	out := filterStudy{Group: group, Wearer: index.Wearers[actor].WearerKey, Scope: scope, Slots: slots, PoolSizes: [2]int{len(pools[0]), len(pools[1])}, Nodes: p.NodeCount(), Coordinates: len(ref), K: k, Unresolved: p.HasUnresolvedDependencies()}
	modelOnly := os.Getenv("GTT_FILTER_MODEL_SCOPE") == "1"
	out.BoundScope = "engine_response_guarded"
	if modelOnly {
		out.BoundScope = "compiled_arithmetic_only_not_engine_response"
	}
	// Same priority/order for every method; no oracle scores initialize pruning.
	_, weights, _, err := p.ValueGradient(filterDelta(anchor[actor], vectors, ref))
	if err != nil {
		t.Fatal(err)
	}
	for n := range pools {
		pools[n] = append([]int64(nil), pools[n]...)
		priority := func(id int64) float64 {
			v := 0.0
			for j, w := range weights {
				v += w * vectors[id][j]
			}
			return v
		}
		sort.SliceStable(pools[n], func(i, j int) bool {
			a, b := priority(pools[n][i]), priority(pools[n][j])
			if a != b {
				return a > b
			}
			return pools[n][i] < pools[n][j]
		})
	}
	lo, hi := filterWholeBox(anchor[actor], slots, pools, vectors, ref)
	start := time.Now()
	signs := p.HypothesisBoxBounds(lo, hi)
	if modelOnly {
		signs = p.HypothesisModelBoxBounds(lo, hi)
	}
	out.SignSeconds = time.Since(start).Seconds()
	for j, key := range p.Coordinates() {
		if signs.Increasing[j] {
			out.Increasing = append(out.Increasing, key)
		}
		if signs.Decreasing[j] {
			out.Decreasing = append(out.Decreasing, key)
		}
	}
	// Every removed item has K distinct, available, same-set replacements.
	// This is conditional on three fixed wearers, not global inventory deletion.
	start = time.Now()
	eliminated := [2]map[int64]bool{filterDominated(pools[0], vectors, signs.Increasing, signs.Decreasing, index, k), filterDominated(pools[1], vectors, signs.Increasing, signs.Decreasing, index, k)}
	dominancePrep := time.Since(start).Seconds()
	start = time.Now()
	legalPools, pairs, legalPairs := filterLegalPools(index, anchor[actor], slots, pools, validator.Validate)
	legalityPrep := time.Since(start).Seconds()
	out.FamilyPairs, out.LegalFamilyPairs = pairs, legalPairs
	supportedBounds := 0
	evaluate := func(useBound, useDominance, useLegality bool) ([]filterPoint, int, int, int) {
		var best []filterPoint
		evaluated, pruned, bounds := 0, 0, 0
		for position, a := range pools[0] {
			if useDominance && eliminated[0][a] {
				continue
			}
			ids := anchor[actor]
			ids[slots[0]] = a
			if useBound && len(best) >= k {
				l, h := filterBox(ids, slots[1], pools[1], vectors, ref)
				_, upper, supported := p.HypothesisBoxRange(l, h)
				if modelOnly {
					_, upper, supported = p.HypothesisModelBoxRange(l, h)
				}
				bounds++
				if supported {
					supportedBounds++
				}
				if supported && upper+1e-8*(1+math.Abs(upper)) < best[k-1].DPS {
					pruned += len(pools[1])
					continue
				}
			}
			remaining := pools[1]
			if useLegality {
				remaining = legalPools[position]
			}
			for _, b := range remaining {
				if useDominance && eliminated[1][b] {
					continue
				}
				ids[slots[1]] = b
				if validator.Validate(ids) != nil {
					continue
				}
				dps, e := p.Evaluate(filterDelta(ids, vectors, ref))
				if e != nil {
					t.Fatal(e)
				}
				evaluated++
				best = filterKeep(best, filterPoint{ids, dps}, k)
			}
		}
		return best, evaluated, pruned, bounds
	}
	// Repeated kernel timings reduce timer jitter; compilation/capture not hidden.
	var baseline, bounded, dominated, legal []filterPoint
	for n := 0; n < 3; n++ {
		start = time.Now()
		var count int
		baseline, count, _, _ = evaluate(false, false, false)
		out.BaselineSeconds += time.Since(start).Seconds() / 3
		out.LegalPoints = count
		start = time.Now()
		var skipped, calls int
		supportedBounds = 0
		bounded, count, skipped, calls = evaluate(true, false, false)
		out.BoundSeconds += time.Since(start).Seconds() / 3
		out.BoundSkipped = skipped
		out.BoundCalls = calls
		out.BoundScored, out.BoundSkippedLegal, out.SupportedBounds = count, out.LegalPoints-count, supportedBounds
		start = time.Now()
		dominated, count, _, _ = evaluate(false, true, false)
		out.DominanceSeconds += time.Since(start).Seconds() / 3
		out.DominanceSkipped = out.LegalPoints - count
		start = time.Now()
		legal, count, _, _ = evaluate(false, false, true)
		out.LegalitySeconds += time.Since(start).Seconds() / 3
		out.LegalityScored = count
	}
	out.DominanceSeconds += dominancePrep + out.SignSeconds
	out.LegalitySeconds += legalityPrep
	out.BoundParity = filterSame(baseline, bounded)
	out.DominanceParity = filterSame(baseline, dominated)
	out.LegalityParity = filterSame(baseline, legal)
	if !out.BoundParity || !out.DominanceParity || !out.LegalityParity {
		t.Errorf("pilot parity failure: %+v", out)
	}
	return out
}

func TestHypothesisActualFilters(t *testing.T) {
	root, run := os.Getenv("GTT_SCRATCH_DIR"), os.Getenv("GTT_FILTER_RUN")
	if root == "" || run == "" {
		t.Fatal("managed scope required")
	}
	req, sources, err := readSetSources(filepath.Join(run, "request.json"), filepath.Join(run, "set-sources.json"))
	if err != nil {
		t.Fatal(err)
	}
	sha, err := contracts.CanonicalSHA256(req)
	if err != nil {
		t.Fatal(err)
	}
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: sources.CatalogSHA256, ReferenceStatsSHA256: sha, Seeds: req.Stochastic.Seeds}
	base, err := setcontext.New(binding, req.Context.PreparedConfig.Text)
	if err != nil {
		t.Fatal(err)
	}
	index, err := domain.Build(req, nil)
	if err != nil {
		t.Fatal(err)
	}
	_, index, base, err = allsets.CanonicalReference(req, index, base, binding)
	if err != nil {
		t.Fatal(err)
	}
	changes := map[string][]setcontext.Set{}
	for _, w := range index.Wearers {
		changes[w.WearerKey] = nil
	}
	neutral, err := base.Replace(changes)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.Mkdir(filepath.Join(root, "capture"), 0700); err != nil {
		t.Fatal(err)
	}
	provider, err := setcontext.NewEffectEngineProvider(binding, filepath.Join(root, "capture"))
	if err != nil {
		t.Fatal(err)
	}
	defer func() {
		if err := provider.Close(); err != nil {
			t.Errorf("capture cleanup: %v", err)
		}
	}()
	start := time.Now()
	capture, err := provider.Capture(context.Background(), neutral)
	if err != nil {
		t.Fatal(err)
	}
	session, err := setcontext.NewSession(func(context.Context, *setcontext.Context) (setcontext.Capture, error) { return capture, nil }, len(binding.Seeds))
	if err != nil {
		t.Fatal(err)
	}
	handle, err := session.Resolve(context.Background(), neutral, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	captureSeconds := time.Since(start).Seconds()
	var replay *seteffects.HypothesisReplayStudyResult
	if os.Getenv("GTT_FILTER_MODEL_SCOPE") != "1" {
		value, e := seteffects.HypothesisReplayStudy(sources, capture.Effects)
		if e != nil {
			t.Fatal(e)
		}
		replay = &value
		if len(replay.Mismatches) > 0 {
			t.Errorf("replay gate mismatches: %v", replay.Mismatches)
		}
	}
	neutralPanel, err := handle.SearchPanel()
	if err != nil {
		t.Fatal(err)
	}
	neutralProgram, err := neutralPanel.ArtifactProgram(make([]float64, len(neutralPanel.Coordinates())), 0)
	if err != nil {
		t.Fatal(err)
	}
	model, err := setcontext.NewNeutralModel(handle, sources)
	if err != nil {
		t.Fatal(err)
	}
	var saved struct {
		Product struct {
			Rows []filterRow `json:"candidates"`
		} `json:"product_result"`
	}
	if err = filterRead(filepath.Join(run, "optimizer-output.json"), &saved); err != nil {
		t.Fatal(err)
	}
	var studies []filterStudy
	checked := 0
	maxResidual := 0.0
	groupHandles := map[string]*setcontext.Handle{}
	coverage := map[string][]string{}
	for _, row := range saved.Product.Rows {
		var entries []struct {
			Wearer  string `json:"wearer_key"`
			Bonuses []struct {
				UID    string `json:"set_uid"`
				Pieces int    `json:"pieces"`
			} `json:"bonuses"`
		}
		if err = json.Unmarshal([]byte(row.Group), &entries); err != nil {
			t.Fatal(err)
		}
		var packs [4]domain.Package
		changes = map[string][]setcontext.Set{}
		var assignment domain.Assignment
		for actor, w := range index.Wearers {
			changes[w.WearerKey] = nil
			for _, entry := range entries {
				if entry.Wearer == w.WearerKey {
					for _, bonus := range entry.Bonuses {
						packs[actor].Sets = append(packs[actor].Sets, contracts.SetRequirement{SetUID: bonus.UID, Count: bonus.Pieces})
						changes[w.WearerKey] = append(changes[w.WearerKey], setcontext.Set{UID: bonus.UID, Count: bonus.Pieces})
					}
				}
			}
			for _, item := range row.Artifacts {
				if item.Wearer == w.WearerKey {
					for slot, key := range []string{"flower", "plume", "sands", "goblet", "circlet"} {
						if key == item.Slot {
							assignment[actor][slot] = item.ID
						}
					}
				}
			}
		}
		h := groupHandles[row.Group]
		if h == nil {
			target, e := base.Replace(changes)
			if e != nil {
				t.Fatal(e)
			}
			var reasons []string
			h, reasons, err = model.Resolve(target)
			if err != nil || h == nil {
				t.Fatal(err, reasons)
			}
			groupHandles[row.Group] = h
		}
		panel, e := h.SearchPanel()
		if e != nil {
			t.Fatal(e)
		}
		coverage[row.Group] = filterReasonSample(panel.OpaqueReasons())
		view, e := index.ForPackages(packs, assignment, panel.Coordinates())
		if e != nil {
			t.Fatal(e)
		}
		dense, e := view.DenseDeltas(assignment)
		if e != nil {
			t.Fatal(e)
		}
		value, e := panel.EvaluateDPS(dense)
		if e != nil {
			t.Fatal(e)
		}
		residual := math.Abs(value - row.DPS)
		maxResidual = math.Max(maxResidual, residual)
		if residual > 1e-7*(1+math.Abs(row.DPS)) {
			t.Errorf("saved row changed: %g vs %g", value, row.DPS)
		}
		checked++
		if row.Rank != 1 || len(studies) >= 16 {
			continue
		}
		used := map[int64]bool{}
		for _, ids := range assignment {
			for _, id := range ids {
				used[id] = true
			}
		}
		for actor := 0; actor < 4; actor++ {
			var all [5][]int64
			for slot, pool := range view.CandidateIDsBySlot {
				for _, id := range pool {
					if !used[id] || id == assignment[actor][slot] {
						all[slot] = append(all[slot], id)
					}
				}
			}
			// Plume/circlet tradeoffs include attack, crit balance and ER. Keep
			// the entire inventory in wide pools; legality is checked separately.
			slots := [2]int{1, 4}
			pools := [2][]int64{all[1], all[4]}
			program, e := panel.ArtifactProgram(dense, actor)
			if e != nil {
				t.Fatal(e)
			}
			tiny := [2][]int64{}
			for n, pool := range pools {
				tiny[n] = []int64{assignment[actor][slots[n]]}
				for _, id := range pool {
					if id != tiny[n][0] && len(tiny[n]) < 4 {
						tiny[n] = append(tiny[n], id)
					}
				}
			}
			studies = append(studies, filterPilot(t, row.Group, view, program, assignment, actor, slots, tiny, 1, "tiny"))
			studies = append(studies, filterPilot(t, row.Group, view, program, assignment, actor, slots, pools, 7, "wide_top7"))
		}
	}
	output := map[string]any{"capture_seconds": captureSeconds, "saved_rows_checked": checked, "saved_row_max_abs_residual": maxResidual, "filter_studies": studies, "replay_gate": replay, "neutral_model": model.Stats(), "status": "pilot_complete", "neutral_program_unresolved": neutralProgram.HasUnresolvedDependencies(), "neutral_opaque_reasons": filterReasonSample(neutralPanel.OpaqueReasons()), "group_opaque_reasons": coverage}
	b, err := json.MarshalIndent(output, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(os.Getenv("GTT_FILTER_OUTPUT"), b, 0600); err != nil {
		t.Fatal(err)
	}
	fmt.Printf("FILTER PILOT rows=%d studies=%d residual=%g capture=%.3fs\n", checked, len(studies), maxResidual, captureSeconds)
}

func filterReasonSample(reasons []string) []string {
	unique := map[string]bool{}
	var result []string
	for _, reason := range reasons {
		if len(reason) > 200 {
			reason = reason[:200]
		}
		if !unique[reason] && len(result) < 12 {
			unique[reason] = true
			result = append(result, reason)
		}
	}
	return result
}

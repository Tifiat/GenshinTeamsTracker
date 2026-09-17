// Package search implements the clean Go Formula-Guided Build Search (FGBS).
// It is a bounded candidate generator, never a proof of global optimality.
package search

import (
	"context"
	"encoding/binary"
	"fmt"
	"math"
	"slices"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

type Config struct {
	FirstFrontierWidth   int
	RecheckFrontierWidth int
	MaxExpandedPerActor  int
	FinalistLimit        int
	MaxCycles            int
	PairFinalistLimit    int
}

func DefaultConfig() Config {
	return Config{32, 8, 20000, 8, 2, 24}
}

type ScoredAssignment struct {
	Assignment domain.Assignment `json:"assignment"`
	DPS        float64           `json:"dps"`
	Source     string            `json:"source"`
}

type ActorStep struct {
	Cycle               int                `json:"cycle"`
	WearerKey           string             `json:"wearer_key"`
	Accepted            bool               `json:"accepted"`
	AnchorDPS           float64            `json:"anchor_dps"`
	ProposalDPS         float64            `json:"proposal_dps"`
	RawPhysicalBuilds   int64              `json:"raw_physical_builds"`
	Expanded            int                `json:"expanded"`
	GuideEvaluations    int                `json:"guide_evaluations"`
	CompleteEvaluations int                `json:"complete_evaluations"`
	FrontierDiscarded   int                `json:"frontier_discarded"`
	BudgetUnexpanded    int64              `json:"budget_unexpanded"`
	FrontierWidth       int                `json:"frontier_width"`
	Finalists           []ScoredAssignment `json:"finalists"`
}

type Result struct {
	Initial                 ScoredAssignment                `json:"initial"`
	Leader                  ScoredAssignment                `json:"leader"`
	Finalists               []ScoredAssignment              `json:"finalists"`
	Steps                   []ActorStep                     `json:"steps"`
	CompletedCycles         int                             `json:"completed_cycles"`
	AcceptedSteps           int                             `json:"accepted_steps"`
	PairGenerated           int                             `json:"pair_generated"`
	PairEvaluated           int                             `json:"pair_evaluated"`
	PairInvalid             int                             `json:"pair_invalid"`
	PairDuplicates          int                             `json:"pair_duplicates"`
	PairActorKeys           [][2]string                     `json:"pair_actor_keys"`
	ResponseLedger          []evaluator.ResponseLedgerEntry `json:"response_ledger"`
	OpaqueReasons           []string                        `json:"opaque_reasons"`
	SaturationFrozenWearers []string                        `json:"saturation_frozen_wearers"`
	StopReason              string                          `json:"stop_reason"`
}

type Engine struct {
	domain *domain.Index
	panel  *evaluator.Panel
	config Config
}

func New(artifactDomain *domain.Index, panel *evaluator.Panel, config Config) (*Engine, error) {
	if artifactDomain == nil || panel == nil {
		return nil, fmt.Errorf("search domain and panel are required")
	}
	if !slices.Equal(artifactDomain.Coordinates, panel.Coordinates()) {
		return nil, fmt.Errorf("search coordinate order mismatch")
	}
	for i, key := range panel.ActorKeys() {
		if artifactDomain.Wearers[i].WearerKey != key {
			return nil, fmt.Errorf("search wearer order mismatch")
		}
	}
	if config.FirstFrontierWidth <= 0 || config.RecheckFrontierWidth <= 0 || config.MaxExpandedPerActor <= 0 || config.FinalistLimit < 2 || config.MaxCycles <= 0 || config.PairFinalistLimit < 2 {
		return nil, fmt.Errorf("search config is invalid")
	}
	return &Engine{artifactDomain, panel, config}, nil
}

// RefineWearer exposes one existing bounded FGBS step for All Sets orchestration.
// It does not run a whole Selected pipeline or grant an additional simulation
// budget. The caller owns the shared context/queue/deadline across these steps.
func (engine *Engine) RefineWearer(ctx context.Context, anchor domain.Assignment, wearerIndex int) (ActorStep, error) {
	if wearerIndex < 0 || wearerIndex >= 4 {
		return ActorStep{}, fmt.Errorf("wearer index outside team")
	}
	if err := ctx.Err(); err != nil {
		return ActorStep{}, err
	}
	if err := engine.domain.ValidateAssignment(anchor); err != nil {
		return ActorStep{}, err
	}
	return engine.searchActor(ctx, anchor, wearerIndex, 1, engine.config.FirstFrontierWidth)
}

func (engine *Engine) Run(ctx context.Context) (Result, error) {
	initialDPS, err := engine.score(engine.domain.Incumbent)
	if err != nil {
		return Result{}, err
	}
	initial := ScoredAssignment{engine.domain.Incumbent, initialDPS, "incumbent"}
	result := Result{
		Initial: initial, Leader: initial, Finalists: []ScoredAssignment{initial},
		ResponseLedger: engine.panel.ResponseLedger(), OpaqueReasons: engine.panel.OpaqueReasons(),
		SaturationFrozenWearers: []string{},
	}
	anchor := initial
	candidatePool := []ScoredAssignment{initial}
	lastFinalists := make([][]ScoredAssignment, 4)
	for cycle := 1; cycle <= engine.config.MaxCycles; cycle++ {
		improved := false
		width := engine.config.FirstFrontierWidth
		if cycle > 1 {
			width = engine.config.RecheckFrontierWidth
		}
		for wearerIndex := 0; wearerIndex < 4; wearerIndex++ {
			if err := ctx.Err(); err != nil {
				return result, err
			}
			before := anchor
			step, err := engine.searchActor(ctx, anchor.Assignment, wearerIndex, cycle, width)
			if err != nil {
				return result, err
			}
			lastFinalists[wearerIndex] = step.Finalists
			candidatePool = append(candidatePool, step.Finalists...)
			proposal := step.Finalists[0]
			step.AnchorDPS = before.DPS
			step.ProposalDPS = proposal.DPS
			if proposal.DPS > before.DPS+1e-9 {
				step.Accepted = true
				anchor = proposal
				result.AcceptedSteps++
				improved = true
			}
			result.Steps = append(result.Steps, step)
		}
		result.CompletedCycles = cycle
		if !improved {
			result.StopReason = "provisional_stable"
			break
		}
	}
	if result.StopReason == "" {
		result.StopReason = "max_cycles"
	}
	paired, pairRows, pairKeys, generated, evaluated, invalid, duplicates, err := engine.refinePairs(ctx, anchor, lastFinalists)
	if err != nil {
		return result, err
	}
	result.PairGenerated, result.PairEvaluated, result.PairInvalid, result.PairDuplicates = generated, evaluated, invalid, duplicates
	result.PairActorKeys = pairKeys
	candidatePool = append(candidatePool, pairRows...)
	if paired.DPS > anchor.DPS+1e-9 {
		anchor = paired
		result.StopReason += "+pair_improved"
	}
	result.Leader = anchor
	candidatePool = append(candidatePool, anchor, paired)
	result.Finalists = mergeFinalists(engine.config.PairFinalistLimit, candidatePool...)
	return result, nil
}

type partial struct {
	ids           [5]int64
	chosen        [5]bool
	proxy         domain.Assignment
	deltas        []float64
	score         float64
	physicalCount int64
}

type lane struct {
	pools [5][]int64
	raw   int64
}

func (engine *Engine) searchActor(ctx context.Context, anchor domain.Assignment, wearerIndex, cycle, width int) (ActorStep, error) {
	step := ActorStep{Cycle: cycle, WearerKey: engine.domain.Wearers[wearerIndex].WearerKey, FrontierWidth: width}
	anchorDPS, err := engine.score(anchor)
	if err != nil {
		return step, err
	}
	byAssignment := map[domain.Assignment]ScoredAssignment{anchor: {anchor, anchorDPS, "anchor"}}
	remaining := engine.config.MaxExpandedPerActor
	lanes := engine.lanes(anchor, wearerIndex)
	pairedSets := len(engine.domain.Wearers[wearerIndex].SelectedSets) == 2
	for laneIndex, currentLane := range lanes {
		step.RawPhysicalBuilds = saturatingAdd(step.RawPhysicalBuilds, currentLane.raw)
		if remaining <= 0 {
			step.BudgetUnexpanded = saturatingAdd(step.BudgetUnexpanded, currentLane.raw)
			continue
		}
		fallback, guideCount, err := engine.laneFallback(anchor, wearerIndex, currentLane)
		if err != nil {
			return step, err
		}
		step.GuideEvaluations += guideCount
		allowance := remaining
		if pairedSets {
			// Fifty possible slot patterns must share the existing actor budget;
			// an early pattern must not consume it before others are considered.
			allowance = remaining / (len(lanes) - laneIndex)
			trial := anchor
			trial[wearerIndex] = fallback
			dps, err := engine.scoreActor(trial, wearerIndex)
			if err != nil {
				return step, err
			}
			step.CompleteEvaluations++
			byAssignment[trial] = ScoredAssignment{trial, dps, fmt.Sprintf("actor_%d_lane_%d_anchor", wearerIndex, laneIndex)}
		}
		order := []int{0, 1, 2, 3, 4}
		sort.SliceStable(order, func(i, j int) bool {
			if len(currentLane.pools[order[i]]) != len(currentLane.pools[order[j]]) {
				return len(currentLane.pools[order[i]]) < len(currentLane.pools[order[j]])
			}
			return order[i] < order[j]
		})
		frontier := []partial{{physicalCount: 1}}
		for depth, slotIndex := range order {
			projected := len(frontier) * len(currentLane.pools[slotIndex])
			take := projected
			if take > allowance {
				take = allowance
				step.BudgetUnexpanded = saturatingAdd(step.BudgetUnexpanded, int64(projected-take))
			}
			builders := make(map[string]partial, take)
			emitted := 0
			for _, parent := range frontier {
				for _, artifactID := range currentLane.pools[slotIndex] {
					if emitted >= take {
						break
					}
					emitted++
					candidate := parent
					candidate.ids[slotIndex], candidate.chosen[slotIndex] = artifactID, true
					proxy := anchor
					for slot := 0; slot < 5; slot++ {
						if candidate.chosen[slot] {
							proxy[wearerIndex][slot] = candidate.ids[slot]
						} else {
							proxy[wearerIndex][slot] = fallback[slot]
						}
					}
					deltas, err := engine.domain.DenseDeltas(proxy)
					if err != nil {
						return step, err
					}
					dps, err := engine.panel.EvaluateDPSForActor(deltas, wearerIndex)
					if err != nil {
						return step, err
					}
					candidate.proxy, candidate.deltas, candidate.score = proxy, deltas, dps
					key := vectorKey(deltas)
					old, exists := builders[key]
					if !exists || idsLess(candidate.ids, old.ids) {
						if exists {
							candidate.physicalCount += old.physicalCount
						}
						builders[key] = candidate
					} else {
						old.physicalCount += candidate.physicalCount
						builders[key] = old
					}
				}
				if emitted >= take {
					break
				}
			}
			remaining -= emitted
			allowance -= emitted
			step.Expanded += emitted
			step.GuideEvaluations += emitted
			step.FrontierDiscarded += emitted - len(builders)
			next := make([]partial, 0, len(builders))
			for _, row := range builders {
				next = append(next, row)
			}
			sort.Slice(next, func(i, j int) bool {
				if next[i].score != next[j].score {
					return next[i].score > next[j].score
				}
				return idsLess(next[i].ids, next[j].ids)
			})
			if len(next) > width {
				kept := diverse(next, width)
				step.FrontierDiscarded += len(next) - len(kept)
				next = kept
			}
			frontier = next
			if len(frontier) == 0 || emitted < projected {
				if depth < 4 && allowance <= 0 {
					break
				}
			}
		}
		for _, row := range frontier {
			complete := true
			for _, chosen := range row.chosen {
				if !chosen {
					complete = false
					break
				}
			}
			if !complete {
				continue
			}
			dps, err := engine.scoreActor(row.proxy, wearerIndex)
			if err != nil {
				return step, err
			}
			step.CompleteEvaluations++
			scored := ScoredAssignment{row.proxy, dps, fmt.Sprintf("actor_%d_lane_%d", wearerIndex, laneIndex)}
			if old, ok := byAssignment[row.proxy]; !ok || scored.DPS > old.DPS {
				byAssignment[row.proxy] = scored
			}
		}
	}
	ordered := make([]ScoredAssignment, 0, len(byAssignment))
	for _, row := range byAssignment {
		ordered = append(ordered, row)
	}
	sortScored(ordered)
	if len(ordered) > engine.config.FinalistLimit {
		ordered = ordered[:engine.config.FinalistLimit]
	}
	if !containsAssignment(ordered, anchor) {
		if len(ordered) == engine.config.FinalistLimit {
			ordered[len(ordered)-1] = byAssignment[anchor]
		} else {
			ordered = append(ordered, byAssignment[anchor])
		}
		sortScored(ordered)
	}
	step.Finalists = ordered
	return step, nil
}

func (engine *Engine) lanes(anchor domain.Assignment, wearerIndex int) []lane {
	occupied := make(map[int64]struct{}, 15)
	for actor := 0; actor < 4; actor++ {
		if actor == wearerIndex {
			continue
		}
		for _, id := range anchor[actor] {
			occupied[id] = struct{}{}
		}
	}
	sets := engine.domain.Wearers[wearerIndex].SelectedSets
	if len(sets) == 2 {
		return engine.pairedSetLanes(occupied, sets[0].SetUID, sets[1].SetUID)
	}
	target := sets[0].SetUID
	makeLane := func(offSlot int) lane {
		var output lane
		output.raw = 1
		for slot := 0; slot < 5; slot++ {
			for _, id := range engine.domain.CandidateIDsBySlot[slot] {
				if _, used := occupied[id]; used {
					continue
				}
				set, _ := engine.domain.ArtifactSetUID(id)
				if (slot == offSlot && set != target) || (offSlot < 0 && set == target) || (offSlot >= 0 && slot != offSlot && set == target) {
					output.pools[slot] = append(output.pools[slot], id)
				}
			}
			output.raw = saturatingMultiply(output.raw, int64(len(output.pools[slot])))
		}
		return output
	}
	output := []lane{makeLane(-1)}
	for slot := 0; slot < 5; slot++ {
		output = append(output, makeLane(slot))
	}
	valid := output[:0]
	for _, row := range output {
		ok := true
		for _, pool := range row.pools {
			if len(pool) == 0 {
				ok = false
				break
			}
		}
		if ok {
			valid = append(valid, row)
		}
	}
	return valid
}

func (engine *Engine) laneFallback(anchor domain.Assignment, wearerIndex int, current lane) ([5]int64, int, error) {
	var ids [5]int64
	for slot, pool := range current.pools {
		ids[slot] = pool[0]
		for _, id := range pool {
			if id == anchor[wearerIndex][slot] {
				ids[slot] = id
				break
			}
		}
	}
	evaluations := 0
	for slot, pool := range current.pools {
		best := ids[slot]
		bestDPS := -math.MaxFloat64
		for _, id := range pool {
			trial := anchor
			trial[wearerIndex] = ids
			trial[wearerIndex][slot] = id
			dps, err := engine.scoreActor(trial, wearerIndex)
			if err != nil {
				return ids, evaluations, err
			}
			evaluations++
			if dps > bestDPS+1e-9 || (math.Abs(dps-bestDPS) <= 1e-9 && id < best) {
				best, bestDPS = id, dps
			}
		}
		ids[slot] = best
	}
	return ids, evaluations, nil
}

func (engine *Engine) refinePairs(ctx context.Context, anchor ScoredAssignment, finalists [][]ScoredAssignment) (ScoredAssignment, []ScoredAssignment, [][2]string, int, int, int, int, error) {
	best := anchor
	generated, evaluated, invalid, duplicates := 0, 0, 0, 0
	seen := map[domain.Assignment]struct{}{anchor.Assignment: {}}
	rows := []ScoredAssignment{anchor}
	pairs := engine.refinementPairs(finalists)
	for _, pair := range pairs {
		left, right := engine.wearerIndex(pair[0]), engine.wearerIndex(pair[1])
		leftRows := finalists[left]
		rightRows := finalists[right]
		if len(leftRows) == 0 {
			leftRows = []ScoredAssignment{anchor}
		}
		if len(rightRows) == 0 {
			rightRows = []ScoredAssignment{anchor}
		}
		for _, a := range leftRows {
			for _, b := range rightRows {
				if err := ctx.Err(); err != nil {
					return best, rows, pairs, generated, evaluated, invalid, duplicates, err
				}
				generated++
				trial := anchor.Assignment
				trial[left] = a.Assignment[left]
				trial[right] = b.Assignment[right]
				if _, ok := seen[trial]; ok {
					duplicates++
					continue
				}
				seen[trial] = struct{}{}
				if err := engine.domain.ValidateAssignment(trial); err != nil {
					invalid++
					continue
				}
				dps, err := engine.score(trial)
				if err != nil {
					return best, rows, pairs, generated, evaluated, invalid, duplicates, err
				}
				evaluated++
				scored := ScoredAssignment{trial, dps, "pair_refinement"}
				rows = append(rows, scored)
				if dps > best.DPS+1e-9 {
					best = scored
				}
			}
		}
	}
	rows = mergeFinalists(engine.config.PairFinalistLimit, rows...)
	return best, rows, pairs, generated, evaluated, invalid, duplicates, nil
}

func (engine *Engine) refinementPairs(finalists [][]ScoredAssignment) [][2]string {
	needed := make(map[[2]int]struct{})
	for _, row := range engine.panel.ResponseLedger() {
		provider := engine.wearerIndex(row.ProviderActor)
		if provider < 0 {
			continue
		}
		for _, consumerKey := range row.ConsumerActors {
			consumer := engine.wearerIndex(consumerKey)
			if consumer < 0 || consumer == provider {
				continue
			}
			left, right := provider, consumer
			if left > right {
				left, right = right, left
			}
			needed[[2]int{left, right}] = struct{}{}
		}
	}
	for left := 0; left < 4; left++ {
		leftIDs := finalistArtifactIDs(finalists[left], left)
		for right := left + 1; right < 4; right++ {
			for id := range finalistArtifactIDs(finalists[right], right) {
				if _, ok := leftIDs[id]; ok {
					needed[[2]int{left, right}] = struct{}{}
					break
				}
			}
		}
	}
	indices := make([][2]int, 0, len(needed))
	for pair := range needed {
		indices = append(indices, pair)
	}
	sort.Slice(indices, func(i, j int) bool {
		if indices[i][0] != indices[j][0] {
			return indices[i][0] < indices[j][0]
		}
		return indices[i][1] < indices[j][1]
	})
	output := make([][2]string, len(indices))
	for index, pair := range indices {
		output[index] = [2]string{engine.domain.Wearers[pair[0]].WearerKey, engine.domain.Wearers[pair[1]].WearerKey}
	}
	return output
}

func (engine *Engine) wearerIndex(key string) int {
	for index, wearer := range engine.domain.Wearers {
		if wearer.WearerKey == key {
			return index
		}
	}
	return -1
}

func finalistArtifactIDs(rows []ScoredAssignment, wearerIndex int) map[int64]struct{} {
	output := make(map[int64]struct{})
	for _, row := range rows {
		for _, id := range row.Assignment[wearerIndex] {
			output[id] = struct{}{}
		}
	}
	return output
}

func (engine *Engine) score(assignment domain.Assignment) (float64, error) {
	deltas, err := engine.domain.DenseDeltas(assignment)
	if err != nil {
		return 0, err
	}
	return engine.panel.EvaluateDPS(deltas)
}

func (engine *Engine) scoreActor(assignment domain.Assignment, wearerIndex int) (float64, error) {
	deltas, err := engine.domain.DenseDeltas(assignment)
	if err != nil {
		return 0, err
	}
	return engine.panel.EvaluateDPSForActor(deltas, wearerIndex)
}

func diverse(rows []partial, width int) []partial {
	if len(rows) <= width {
		return rows
	}
	keep := make([]partial, 0, width)
	used := make(map[[5]int64]struct{})
	base := (width + 1) / 2
	for _, row := range rows[:base] {
		keep = append(keep, row)
		used[row.ids] = struct{}{}
	}
	coordinates := len(rows[0].deltas)
	for coordinate := 0; coordinate < coordinates && len(keep) < width; coordinate++ {
		best := -1
		for index, row := range rows {
			if _, ok := used[row.ids]; ok {
				continue
			}
			if best < 0 || row.deltas[coordinate] > rows[best].deltas[coordinate] || (row.deltas[coordinate] == rows[best].deltas[coordinate] && row.score > rows[best].score) {
				best = index
			}
		}
		if best >= 0 {
			keep = append(keep, rows[best])
			used[rows[best].ids] = struct{}{}
		}
	}
	for _, row := range rows {
		if len(keep) >= width {
			break
		}
		if _, ok := used[row.ids]; !ok {
			keep = append(keep, row)
			used[row.ids] = struct{}{}
		}
	}
	sort.Slice(keep, func(i, j int) bool {
		if keep[i].score != keep[j].score {
			return keep[i].score > keep[j].score
		}
		return idsLess(keep[i].ids, keep[j].ids)
	})
	return keep
}
func vectorKey(values []float64) string {
	data := make([]byte, len(values)*8)
	for i, v := range values {
		binary.LittleEndian.PutUint64(data[i*8:], math.Float64bits(v))
	}
	return string(data)
}
func idsLess(a, b [5]int64) bool {
	for i := 0; i < 5; i++ {
		if a[i] != b[i] {
			return a[i] < b[i]
		}
	}
	return false
}
func sortScored(rows []ScoredAssignment) {
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].DPS != rows[j].DPS {
			return rows[i].DPS > rows[j].DPS
		}
		return assignmentLess(rows[i].Assignment, rows[j].Assignment)
	})
}
func assignmentLess(a, b domain.Assignment) bool {
	for i := 0; i < 4; i++ {
		if idsLess(a[i], b[i]) {
			return true
		}
		if idsLess(b[i], a[i]) {
			return false
		}
	}
	return false
}
func containsAssignment(rows []ScoredAssignment, value domain.Assignment) bool {
	for _, row := range rows {
		if row.Assignment == value {
			return true
		}
	}
	return false
}
func mergeFinalists(limit int, rows ...ScoredAssignment) []ScoredAssignment {
	by := make(map[domain.Assignment]ScoredAssignment)
	for _, row := range rows {
		if old, ok := by[row.Assignment]; !ok || row.DPS > old.DPS {
			by[row.Assignment] = row
		}
	}
	out := make([]ScoredAssignment, 0, len(by))
	for _, row := range by {
		out = append(out, row)
	}
	sortScored(out)
	if len(out) > limit {
		out = out[:limit]
	}
	return out
}
func saturatingMultiply(a, b int64) int64 {
	if a == 0 || b == 0 {
		return 0
	}
	if a > math.MaxInt64/b {
		return math.MaxInt64
	}
	return a * b
}
func saturatingAdd(a, b int64) int64 {
	if b > math.MaxInt64-a {
		return math.MaxInt64
	}
	return a + b
}

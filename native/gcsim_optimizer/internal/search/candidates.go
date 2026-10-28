package search

// Source-only real-build policy approved 2026-09-20. Scores/gradients order
// candidates; neither a small observed spread nor local stationarity proves an
// upper bound. Five screening exclusions and five paired exclusions are the
// initial, explicitly heuristic policy. Tiny domains are evaluated exhaustively.
// Selected keeps its existing route until the single-team product gate.
import (
	"context"
	"fmt"
	"math"
	"sort"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

type CandidateReport struct {
	Step                 ActorStep
	Samples, PairSamples int
	Low, High            float64
	Exhaustive           bool
	Stop                 string
}

// DeferBelow uses a safety margin twice the observed spread. It is an explicit
// heuristic, not a statistical confidence interval or a dominance certificate.
func (r CandidateReport) DeferBelow(fifth float64) bool {
	return r.Samples >= 5 && r.PairSamples > 0 && isFiniteCandidate(fifth) &&
		r.High+2*(r.High-r.Low)+1e-7*(1+math.Abs(fifth)) < fifth
}

func isFiniteCandidate(x float64) bool { return !math.IsNaN(x) && !math.IsInf(x, 0) }

type candidateRun struct {
	engine           *Engine
	ctx              context.Context
	anchor           domain.Assignment
	actor, allowance int
	program          *formula.ArtifactProgram
	vectors          map[int64][]float64
	ref, x           []float64
	used             map[int64]bool
	localValidator   *domain.LocalAssignmentValidator
	seen             map[[5]int64]bool
	rows             []ScoredAssignment
	best             ScoredAssignment
	report           CandidateReport
}

func (engine *Engine) candidateRun(ctx context.Context, anchor domain.Assignment, actor, allowance int) (*candidateRun, error) {
	if actor < 0 || actor >= 4 || allowance < 0 || engine.energy != nil {
		return nil, fmt.Errorf("invalid/incomplete candidate-search domain")
	}
	localValidator, err := engine.domain.PrepareLocalAssignmentValidator(anchor, actor)
	if err != nil {
		return nil, err
	}
	dense, err := engine.domain.DenseDeltas(anchor)
	if err != nil {
		return nil, err
	}
	p, err := engine.panel.ArtifactProgram(dense, actor)
	if err != nil {
		return nil, err
	}
	vectors, ref, err := engine.domain.ArtifactVectors(actor, p.Coordinates())
	if err != nil {
		return nil, err
	}
	r := &candidateRun{engine: engine, ctx: ctx, anchor: anchor, actor: actor, allowance: allowance,
		program: p, vectors: vectors, ref: ref, x: make([]float64, len(ref)), used: map[int64]bool{},
		localValidator: localValidator, seen: map[[5]int64]bool{}}
	for a, ids := range anchor {
		if a != actor {
			for _, id := range ids {
				r.used[id] = true
			}
		}
	}
	r.setPoint(anchor[actor])
	v, err := p.Evaluate(r.x)
	if err != nil {
		return nil, err
	}
	r.best = ScoredAssignment{anchor, v, "candidate_anchor"}
	r.rows = []ScoredAssignment{r.best}
	r.report.Step = ActorStep{WearerKey: engine.domain.Wearers[actor].WearerKey, AnchorDPS: v, ReducedNodes: p.NodeCount()}
	r.report.Low, r.report.High = math.Inf(1), math.Inf(-1)
	return r, nil
}

func (r *candidateRun) setPoint(ids [5]int64) {
	for j, v := range r.ref {
		r.x[j] = -v
	}
	for _, id := range ids {
		for j, v := range r.vectors[id] {
			r.x[j] += v
		}
	}
}

func (r *candidateRun) point(ids [5]int64, sample, pair bool) error {
	if err := r.ctx.Err(); err != nil {
		return err
	}
	if r.seen[ids] || r.report.Step.Expanded >= r.allowance {
		return nil
	}
	r.seen[ids] = true
	trial := r.anchor
	trial[r.actor] = ids
	if r.localValidator.Validate(ids) != nil {
		r.report.Step.InvalidAssignments++
		return nil
	}
	r.setPoint(ids)
	v, err := r.program.Evaluate(r.x)
	if err != nil {
		return err
	}
	r.report.Step.Expanded++
	r.report.Step.CompleteEvaluations++
	row := ScoredAssignment{trial, v, "real_candidate"}
	r.engine.observed(row)
	if sample {
		r.report.Samples++
		if pair {
			r.report.PairSamples++
		}
		r.report.Low, r.report.High = math.Min(r.report.Low, v), math.Max(r.report.High, v)
	}
	if r.engine.betterScored(row, r.best) {
		r.best = row
	}
	r.rows = append(r.rows, row)
	if len(r.rows) > 2*r.engine.config.FinalistLimit {
		r.rows = r.engine.mergeFinalists(r.engine.config.FinalistLimit, r.rows...)
	}
	return nil
}

func (r *candidateRun) priorities(ids [5]int64) (map[int64]float64, error) {
	r.setPoint(ids)
	_, weights, _, err := r.program.ValueGradient(r.x)
	if err != nil {
		return nil, err
	}
	r.report.Step.GuideEvaluations++
	priority := make(map[int64]float64, len(r.vectors))
	for id, v := range r.vectors {
		for j, w := range weights {
			priority[id] += w * v[j]
		}
	}
	return priority, nil
}

func (r *candidateRun) linear(priority map[int64]float64, exclude ...int64) ([5]int64, bool, error) {
	used := make(map[int64]bool, len(r.used)+len(exclude))
	for id := range r.used {
		used[id] = true
	}
	for _, id := range exclude {
		used[id] = true
	}
	p := domain.Package{Sets: r.engine.domain.Wearers[r.actor].SelectedSets}
	ids, _, err := r.engine.domain.PackageLinearAssignment(p, priority, used)
	if err != nil && strings.HasPrefix(err.Error(), "no legal completion") {
		return ids, false, nil
	}
	return ids, err == nil, err
}

func (r *candidateRun) screen() error {
	w, err := r.priorities(r.anchor[r.actor])
	if err != nil {
		return err
	}
	plan, err := r.engine.domain.PreparePackageLinear(domain.Package{Sets: r.engine.domain.Wearers[r.actor].SelectedSets}, w, r.used)
	if err != nil {
		return err
	}
	linear := func(excluded ...int64) ([5]int64, bool, error) {
		ids, _, e := plan.Assignment(excluded...)
		if e != nil && strings.HasPrefix(e.Error(), "no legal completion") {
			return ids, false, nil
		}
		return ids, e == nil, e
	}
	ids, ok, err := linear()
	if err != nil || !ok {
		return err
	}
	if err = r.point(ids, true, false); err != nil {
		return err
	}
	// Complete legal alternatives, not scores of partially assembled artifacts.
	// Pair exclusions permit a different main-stat/crit balance in two slots.
	for n := 1; n <= 2; n++ {
		for slot := 0; slot < 5 && r.report.Step.Expanded < r.allowance; slot++ {
			excluded := []int64{ids[slot]}
			if n == 2 {
				excluded = append(excluded, ids[(slot+1)%5])
			}
			next, found, e := linear(excluded...)
			if e != nil {
				return e
			}
			if found {
				if e = r.point(next, true, n == 2); e != nil {
					return e
				}
			}
		}
	}
	return nil
}

func (r *candidateRun) finish(err error) (CandidateReport, error) {
	r.rows = r.engine.mergeFinalists(r.engine.config.FinalistLimit, append(r.rows, r.best)...)
	for i, row := range r.rows {
		v, e := r.engine.score(row.Assignment)
		if e != nil {
			return r.report, e
		}
		if math.Abs(v-row.DPS) > 1e-7*(1+math.Abs(v)) {
			return r.report, fmt.Errorf("real-candidate reduced score mismatch")
		}
		r.rows[i].DPS = v
	}
	r.report.Step.Finalists = r.rows
	r.report.Step.ProposalDPS = r.best.DPS
	r.report.Step.Accepted = r.best.DPS > r.report.Step.AnchorDPS
	if r.report.Samples == 0 {
		r.report.Low, r.report.High = r.best.DPS, r.best.DPS
	}
	if !r.report.Exhaustive {
		r.report.Step.BudgetUnexpanded = 1
	} // unresolved region, NOT a cardinality estimate
	return r.report, err
}

func (engine *Engine) ScreenCandidates(ctx context.Context, anchor domain.Assignment, actor, allowance int) (CandidateReport, error) {
	r, err := engine.candidateRun(ctx, anchor, actor, allowance)
	if err != nil {
		return CandidateReport{}, err
	}
	err = r.screen()
	r.report.Stop = "screen_only"
	return r.finish(err)
}

func (engine *Engine) RefineCandidates(ctx context.Context, anchor domain.Assignment, actor, allowance int) (CandidateReport, error) {
	r, err := engine.candidateRun(ctx, anchor, actor, allowance)
	if err != nil {
		return CandidateReport{}, err
	}
	// Full evaluation is cheapest on tiny domains and supplies a useful oracle
	// crossover. No interval/affine bounds or nonlinear region construction.
	var free [5][]int64
	size := int64(1)
	for slot, pool := range engine.domain.CandidateIDsBySlot {
		for _, id := range pool {
			if !r.used[id] {
				free[slot] = append(free[slot], id)
			}
		}
		size = saturatingMultiply(size, int64(len(free[slot])))
	}
	if size <= int64(min(4096, allowance)) {
		var visit func(int, [5]int64) error
		visit = func(slot int, ids [5]int64) error {
			if slot == 5 {
				return r.point(ids, false, false)
			}
			for _, id := range free[slot] {
				ids[slot] = id
				if e := visit(slot+1, ids); e != nil {
					return e
				}
			}
			return nil
		}
		err = visit(0, [5]int64{})
		r.report.Exhaustive = err == nil
		r.report.Stop = "small_domain_complete"
		return r.finish(err)
	}
	for round := 0; round < 5 && r.report.Step.Expanded < allowance; round++ {
		before := r.best
		weights, e := r.priorities(before.Assignment[actor])
		if e != nil {
			return r.finish(e)
		}
		ids, found, e := r.linear(weights)
		if e != nil {
			return r.finish(e)
		}
		if found {
			if e = r.point(ids, false, false); e != nil {
				return r.finish(e)
			}
		}
		var pools [5][]int64
		sets := engine.domain.Wearers[actor].SelectedSets
		for slot, pool := range free {
			ordered := append([]int64(nil), pool...)
			sort.SliceStable(ordered, func(i, j int) bool {
				if weights[ordered[i]] != weights[ordered[j]] {
					return weights[ordered[i]] > weights[ordered[j]]
				}
				return ordered[i] < ordered[j]
			})
			counts := map[string]int{}
			for _, id := range ordered {
				uid, _ := engine.domain.ArtifactSetUID(id)
				category := "off"
				for _, s := range sets {
					if s.SetUID == uid {
						category = uid
					}
				}
				if counts[category] < engine.config.RecheckFrontierWidth {
					pools[slot] = append(pools[slot], id)
					counts[category]++
				}
			}
		}
		// Inspect pairs even when every single replacement was worse.
		base := r.best.Assignment[actor]
		for a := 0; a < 5; a++ {
			for _, x := range pools[a] {
				trial := base
				trial[a] = x
				if e = r.point(trial, false, false); e != nil {
					return r.finish(e)
				}
				for b := a + 1; b < 5; b++ {
					for _, y := range pools[b] {
						if r.report.Step.Expanded >= allowance {
							break
						}
						trial[b] = y
						if e = r.point(trial, false, false); e != nil {
							return r.finish(e)
						}
					}
					trial[b] = base[b]
				}
				if r.report.Step.Expanded >= allowance {
					break
				}
			}
			if r.report.Step.Expanded >= allowance {
				break
			}
		}
		if r.best.DPS <= before.DPS+1e-9*(1+math.Abs(before.DPS)) {
			r.report.Stop = "sampled_neighborhood_stable"
			break
		}
	}
	if r.report.Stop == "" {
		r.report.Stop = "candidate_work_or_round_limit"
	}
	return r.finish(nil)
}

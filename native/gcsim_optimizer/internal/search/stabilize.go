package search

// Variable-neighborhood descent on COMPLETE legal team assignments. Gradients
// remain proposals, never bounds. A changed incumbent invalidates every earlier
// neighborhood check. Only a full final N1 sweep certifies single-item stability;
// pair neighborhoods are sampled and do not certify a global optimum.
import (
	"context"
	"fmt"
	"math"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

type Stabilization struct {
	Leader           ScoredAssignment `json:"leader"`
	Evaluations      int              `json:"evaluations"`
	Accepted         int              `json:"accepted"`
	SingleStationary bool             `json:"single_stationary"`
	Stop             string           `json:"stop"`
}

func improvesDPS(a, b float64) bool { return a > b+1e-9*(1+math.Abs(b)) }

// RefineSingles enumerates ALL free single-slot substitutions for one wearer.
// Set counts/physical uniqueness are validated before scoring. This does not
// discard low-gradient items and works with caps, thresholds and negative slopes.
func (engine *Engine) RefineSingles(ctx context.Context, anchor domain.Assignment, actor, allowance int) (CandidateReport, error) {
	r, err := engine.candidateRun(ctx, anchor, actor, allowance)
	if err != nil {
		return CandidateReport{}, err
	}
	r.report.Stop = "single_neighborhood_complete"
	for slot, pool := range engine.domain.CandidateIDsBySlot {
		for _, id := range pool {
			if id == anchor[actor][slot] || r.used[id] {
				continue
			}
			trial := anchor[actor]
			trial[slot] = id
			if r.report.Step.Expanded >= allowance {
				r.report.Stop = "single_neighborhood_budget"
				return r.finish(ctx.Err())
			}
			if err := r.point(trial, false, false); err != nil {
				return r.finish(err)
			}
		}
	}
	return r.finish(ctx.Err())
}

func (engine *Engine) Stabilize(ctx context.Context, anchor domain.Assignment, allowance int) (out Stabilization, err error) {
	if !engine.inventoryBounds || engine.energy != nil || allowance < 0 {
		return out, fmt.Errorf("invalid stabilization domain")
	}
	dps, err := engine.score(anchor)
	if err != nil {
		return out, err
	}
	out.Leader = ScoredAssignment{anchor, dps, "stabilization_anchor"}
	out.Stop = "stabilization_budget"
	accept := func(row ScoredAssignment) bool {
		if !improvesDPS(row.DPS, out.Leader.DPS) {
			return false
		}
		out.Leader = row
		out.Accepted++
		out.SingleStationary = false
		return true
	}
	for out.Evaluations < allowance {
		if err = ctx.Err(); err != nil {
			return out, err
		}
		changed := false
		// Cheap complete neighborhood first. Revisit all owners after ANY gain,
		// since another character's artifact may change this character's buff.
		for actor := 0; actor < 4; actor++ {
			r, e := engine.RefineSingles(ctx, out.Leader.Assignment, actor, allowance-out.Evaluations)
			out.Evaluations += r.Step.Expanded
			if len(r.Step.Finalists) > 0 {
				changed = accept(r.Step.Finalists[0]) || changed
			}
			if e != nil {
				return out, e
			}
			if r.Stop != "single_neighborhood_complete" {
				return out, nil
			}
		}
		if changed {
			continue
		}
		out.SingleStationary = true
		// Broader within-wearer pairs/linear starts, then inter-wearer exchanges.
		// Restart from N1 immediately on improvement, not from stale gradients.
		for actor := 0; actor < 4 && !changed; actor++ {
			r, e := engine.RefineCandidates(ctx, out.Leader.Assignment, actor, allowance-out.Evaluations)
			out.Evaluations += r.Step.Expanded
			if len(r.Step.Finalists) > 0 {
				changed = accept(r.Step.Finalists[0])
			}
			if e != nil {
				return out, e
			}
			if out.Evaluations >= allowance {
				return out, nil
			}
		}
		if changed {
			continue
		}
		joint, e := engine.RefineJoint(ctx, out.Leader.Assignment, allowance-out.Evaluations)
		out.Evaluations += joint.PairEvaluated
		changed = accept(joint.Leader)
		if e != nil {
			return out, e
		}
		if joint.PairBudgetExhausted {
			return out, nil
		}
		if changed {
			continue
		}
		out.Stop = "single_stationary_sampled_pairs_stable"
		return out, nil
	}
	return out, nil
}

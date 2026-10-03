package search

// Genuine bounded inventory exchanges for the All Sets foundation. Both wearers
// are released while the other ten IDs stay fixed. This adds legal linear joint
// seeds and occupied-item transfers with a newly chosen donor replacement;
// it is NOT exhaustive joint nonlinear optimization of all ten slots. The full
// parametric package/region coordinator remains a later gate in the handoff.
import (
	"context"
	"fmt"
	"math"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

// RefineJoint is the pair stage only. The neutral coordinator already schedules
// one-wearer regions; running Engine.Run here repeated four atomic searches
// before donor replacement could even begin. The caller supplies the remaining
// shared allowance, including zero, and receives partial legal results on expiry.
func (engine *Engine) RefineJoint(ctx context.Context, assignment domain.Assignment, allowance int) (result Result, err error) {
	if !engine.inventoryBounds || allowance < 0 {
		return result, fmt.Errorf("invalid joint inventory allowance")
	}
	if err := engine.domain.ValidateAssignment(assignment); err != nil {
		return result, err
	}
	dps, err := engine.score(assignment)
	if err != nil {
		return result, err
	}
	anchor := ScoredAssignment{assignment, dps, "inventory_joint_anchor"}
	result.Initial, result.Leader = anchor, anchor
	result.Finalists = []ScoredAssignment{anchor}
	engine.pairWorkLimit, engine.pairBudgetExhausted = allowance, false
	best, rows, keys, generated, evaluated, invalid, duplicates, err := engine.refineInventoryPairs(ctx, anchor, make([][]ScoredAssignment, 4))
	result.Leader, result.Finalists, result.PairActorKeys = best, rows, keys
	result.PairGenerated, result.PairEvaluated, result.PairInvalid, result.PairDuplicates = generated, evaluated, invalid, duplicates
	result.PairBudgetExhausted = engine.pairBudgetExhausted
	return result, err
}

func (engine *Engine) refineInventoryPairs(ctx context.Context, anchor ScoredAssignment, finalists [][]ScoredAssignment) (ScoredAssignment, []ScoredAssignment, [][2]string, int, int, int, int, error) {
	best := anchor
	rows := []ScoredAssignment{anchor}
	seen := map[domain.Assignment]bool{anchor.Assignment: true}
	generated, evaluated, invalid, duplicates := 0, 0, 0, 0
	pairs := [][2]string{}
	for a := 0; a < 4; a++ {
		for b := a + 1; b < 4; b++ {
			pairs = append(pairs, [2]string{engine.domain.Wearers[a].WearerKey, engine.domain.Wearers[b].WearerKey})
		}
	}
	finish := func(err error) (ScoredAssignment, []ScoredAssignment, [][2]string, int, int, int, int, error) {
		rows = engine.mergeFinalists(engine.config.PairFinalistLimit, append(rows, best)...)
		for i, row := range rows {
			v, e := engine.score(row.Assignment)
			if e != nil {
				err = e
				break
			}
			if math.Abs(v-row.DPS) > 1e-7*(1+math.Abs(v)) {
				err = fmt.Errorf("joint finalist formula parity mismatch")
				break
			}
			rows[i].DPS = v
		}
		return best, rows, pairs, generated, evaluated, invalid, duplicates, err
	}
	dense, err := engine.domain.DenseDeltas(anchor.Assignment)
	if err != nil {
		return finish(err)
	}
	for _, keys := range pairs {
		if err := ctx.Err(); err != nil {
			return finish(err)
		}
		if evaluated >= engine.pairWorkLimit {
			engine.pairBudgetExhausted = true
			break
		}
		actors := [2]int{engine.wearerIndex(keys[0]), engine.wearerIndex(keys[1])}
		program, err := engine.panel.ArtifactProgramForActors(dense, actors[0], actors[1])
		if err != nil {
			return finish(err)
		}
		coords := program.Coordinates()
		positions := make([]int, len(coords))
		local := make([]float64, len(coords))
		for i, key := range coords {
			for j, all := range engine.panel.Coordinates() {
				if key == all {
					positions[i] = j
					local[i] = dense[j]
					break
				}
			}
		}
		score := func(trial domain.Assignment, source string) error {
			if err := ctx.Err(); err != nil {
				return err
			}
			generated++
			if seen[trial] {
				duplicates++
				return nil
			}
			seen[trial] = true
			if engine.domain.ValidateAssignment(trial) != nil {
				invalid++
				return nil
			}
			if evaluated >= engine.pairWorkLimit {
				engine.pairBudgetExhausted = true
				return nil
			}
			d, err := engine.domain.DenseDeltas(trial)
			if err != nil {
				return err
			}
			for i, j := range positions {
				local[i] = d[j]
			}
			v, err := program.Evaluate(local)
			if err != nil {
				return err
			}
			evaluated++
			r := ScoredAssignment{trial, v, source}
			engine.observed(r)
			rows = append(rows, r)
			if len(rows) > 2*engine.config.PairFinalistLimit {
				rows = engine.mergeFinalists(engine.config.PairFinalistLimit, rows...)
			}
			if engine.betterScored(r, best) {
				// Recheck improvements against the unreduced source arithmetic.
				original, err := engine.score(trial)
				if err != nil {
					return err
				}
				if math.Abs(original-v) > 1e-7*(1+math.Abs(original)) {
					return fmt.Errorf("joint reduced formula parity mismatch")
				}
				r.DPS = original
				best = r
			}
			return nil
		}
		// A complete legal linear joint seed can reassign several slots at once.
		// Its real nonlinear score, not the slope, determines acceptance.
		var packages [2]domain.Package
		var priorities [2]map[int64]float64
		for i, j := range positions {
			local[i] = dense[j]
		}
		_, gradient, _, err := program.ValueGradient(local)
		if err != nil {
			return finish(err)
		}
		seedSupported := true
		for side, actor := range actors {
			packages[side] = domain.Package{Sets: engine.domain.Wearers[actor].SelectedSets}
			sets := packages[side].Sets
			seedSupported = seedSupported && (len(sets) == 2 || len(sets) == 1 && sets[0].Count == 4)
			ownCoords := []string{}
			ownWeights := []float64{}
			for j, key := range coords {
				if strings.HasPrefix(key, keys[side]+".") {
					ownCoords = append(ownCoords, key)
					ownWeights = append(ownWeights, gradient[j])
				}
			}
			vectors, _, err := engine.domain.ArtifactVectors(actor, ownCoords)
			if err != nil {
				return finish(err)
			}
			priorities[side] = map[int64]float64{}
			for id, vector := range vectors {
				for j, v := range vector {
					priorities[side][id] += v * ownWeights[j]
				}
			}
		}
		if seedSupported {
			seed, err := engine.domain.PairPackageSeed(anchor.Assignment, actors, packages, priorities)
			if err != nil {
				return finish(err)
			}
			if err := score(seed, "joint_inventory_seed"); err != nil {
				return finish(err)
			}
		}
		// Transfers are not restricted to previously retained per-wearer rows.
		// The donor can choose any free replacement, including the receiver's
		// old piece. Legality is checked BEFORE consuming the scoring allowance.
		for slot, pool := range engine.domain.CandidateIDsBySlot {
			for direction := 0; direction < 2; direction++ {
				donor, receiver := actors[direction], actors[1-direction]
				for _, replacement := range pool {
					if evaluated >= engine.pairWorkLimit {
						engine.pairBudgetExhausted = true
						break
					}
					trial := anchor.Assignment
					trial[receiver][slot] = anchor.Assignment[donor][slot]
					trial[donor][slot] = replacement
					if err := score(trial, "joint_inventory_transfer"); err != nil {
						return finish(err)
					}
				}
				if engine.pairBudgetExhausted {
					break
				}
			}
			if engine.pairBudgetExhausted {
				break
			}
		}
		if engine.pairBudgetExhausted {
			break
		}
		// Retain the old useful paired combinations as an additional lane.
		leftRows, rightRows := finalists[actors[0]], finalists[actors[1]]
		if len(leftRows) == 0 {
			leftRows = []ScoredAssignment{anchor}
		}
		if len(rightRows) == 0 {
			rightRows = []ScoredAssignment{anchor}
		}
		for _, a := range leftRows {
			for _, b := range rightRows {
				if evaluated >= engine.pairWorkLimit {
					engine.pairBudgetExhausted = true
					break
				}
				trial := anchor.Assignment
				trial[actors[0]], trial[actors[1]] = a.Assignment[actors[0]], b.Assignment[actors[1]]
				if err := score(trial, "joint_inventory_retained"); err != nil {
					return finish(err)
				}
			}
			if engine.pairBudgetExhausted {
				break
			}
		}
	}
	return finish(nil)
}

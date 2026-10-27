package finalists

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

type StagedVerification struct {
	Policy                 string                    `json:"policy"`
	Status                 string                    `json:"status"`
	IterationPolicy        string                    `json:"iteration_policy"`
	PilotIterations        int                       `json:"pilot_iterations"`
	ConfirmationIterations int                       `json:"confirmation_iterations"`
	InputCandidates        int                       `json:"input_candidates"`
	Stages                 []StagedVerificationStage `json:"stages"`
	Decisions              []StagedPromotionDecision `json:"decisions"`
	ElapsedMS              float64                   `json:"elapsed_ms"`
	Error                  string                    `json:"error,omitempty"`
}
type StagedVerificationStage struct {
	Name       string             `json:"name"`
	Iterations int                `json:"iterations"`
	Attempted  []string           `json:"attempted_sha256"`
	Result     VerificationResult `json:"result"`
	Error      string             `json:"error,omitempty"`
}
type StagedPromotionDecision struct {
	Stage            string  `json:"stage"`
	AssignmentSHA256 string  `json:"assignment_sha256"`
	LeaderSHA256     string  `json:"leader_sha256"`
	LeaderIterations int     `json:"leader_iterations"`
	Gap              float64 `json:"gap"`
	Threshold        float64 `json:"threshold"`
	Promoted         bool    `json:"promoted"`
}

// VerifyStagedWavesWithRenderer changes only the final common-fidelity stage.
// The four-SE rule is an experimental promotion heuristic, never a pruning proof.
func VerifyStagedWavesWithRenderer(ctx context.Context, request contracts.OptimizerRequest, candidates []search.ScoredAssignment, render CandidateRenderer, runRoot string, maxParallelism, cpuBudget int) (VerificationResult, error) {
	return verifyStagedWithRunner(ctx, request, candidates, render, runRoot, maxParallelism, cpuBudget, nil)
}

func verifyStagedWithRunner(ctx context.Context, request contracts.OptimizerRequest, candidates []search.ScoredAssignment, render CandidateRenderer, runRoot string, maxParallelism, cpuBudget int, runner OrdinaryRunner) (output VerificationResult, err error) {
	started := time.Now()
	if ctx == nil || render == nil || len(candidates) == 0 || len(candidates) > 9 {
		return output, fmt.Errorf("invalid staged finalist input")
	}
	if _, err = PlanDynamicWaves(len(candidates), maxParallelism, cpuBudget); err != nil {
		return
	}
	all, originals, err := prepareInventoryCandidates(request, candidates)
	if err != nil {
		return output, err
	}
	if err = os.Mkdir(runRoot, 0700); err != nil {
		return
	}
	receipt := &StagedVerification{Policy: "r2_n100_n500_four_se_v1", Status: "running", IterationPolicy: "per_candidate", PilotIterations: 100, ConfirmationIterations: 500, InputCandidates: len(candidates)}
	output.Staged = receipt
	latest := map[domain.Assignment]MeasuredCandidate{}
	pilots := map[domain.Assignment]MeasuredCandidate{}
	rejected := map[string]bool{}
	confirmed := map[domain.Assignment]bool{}
	admitted := map[domain.Assignment]bool{}
	save := func() error {
		raw, e := json.MarshalIndent(receipt, "", "  ")
		if e != nil {
			return e
		}
		return os.WriteFile(filepath.Join(runRoot, "verification-stages.json"), raw, 0600)
	}
	defer func() {
		output.TotalElapsedMS = float64(time.Since(started)) / float64(time.Millisecond)
		receipt.ElapsedMS = output.TotalElapsedMS
		receipt.Status = "completed"
		if err != nil {
			receipt.Status = "failed"
			receipt.Error = err.Error()
		}
		if e := save(); e != nil && err == nil {
			err = fmt.Errorf("save staged verification: %w", e)
		}
	}()
	// Production keeps nil runner, so each existing full-build stage retains
	// every engine/config/measurement guard. A nonnil runner is only a test seam.
	stage := func(name string, subset []search.ScoredAssignment, n int) error {
		prepared, _, e := prepareInventoryCandidates(request, subset)
		if e != nil {
			return e
		}
		full, runErr := VerifyFullBuildsWithRenderer(ctx, request, prepared, inventoryCandidateRenderer(render), filepath.Join(runRoot, name), n, maxParallelism, cpuBudget, runner)
		adapted, adaptErr := adaptInventoryVerification(full, request, all, originals, n, 0, 0, true)
		result := StagedVerificationStage{Name: name, Iterations: n, Attempted: append([]string(nil), full.AttemptedSHA256...), Result: adapted}
		for _, key := range adapted.EnergyRejectedSHA256 {
			rejected[key] = true
		}
		for _, row := range adapted.Candidates {
			latest[row.Assignment] = row
			if n == 100 {
				pilots[row.Assignment] = row
			} else {
				confirmed[row.Assignment] = true
			}
		}
		for assignment, row := range latest {
			if rejected[row.AssignmentSHA256] {
				delete(latest, assignment)
			}
		}
		if runErr != nil {
			result.Error = runErr.Error()
		}
		receipt.Stages = append(receipt.Stages, result)
		if e = save(); e != nil {
			return e
		}
		if adaptErr != nil {
			return adaptErr
		}
		if runErr != nil {
			if noEnergy, ok := asNoEnergyFullBuild(runErr); ok {
				if n == 500 && len(latest) > 0 {
					return nil
				}
				ids, mapErr := assignmentIdentitiesForFullKeys(request, prepared, originals, noEnergy.CandidateSHA256)
				if mapErr != nil {
					return mapErr
				}
				return &NoEnergyFeasibleFinalistError{AssignmentSHA256: ids, MaximumShortage: noEnergy.MaximumShortage, ElapsedMS: noEnergy.ElapsedMS}
			}
			return runErr
		}
		return nil
	}
	if err = stage("pilot-n100", candidates, 100); err != nil {
		return
	}
	order := make([]MeasuredCandidate, 0, len(pilots))
	for _, row := range pilots {
		order = append(order, row)
	}
	sort.Slice(order, func(i, j int) bool {
		if order[i].MeasuredDPS != order[j].MeasuredDPS {
			return order[i].MeasuredDPS > order[j].MeasuredDPS
		}
		return order[i].AssignmentSHA256 < order[j].AssignmentSHA256
	})
	if len(order) == 0 {
		return output, fmt.Errorf("staged pilot has no feasible candidate")
	}
	promote := func(leader MeasuredCandidate, label string) error {
		for _, pilot := range order {
			if confirmed[pilot.Assignment] || rejected[pilot.AssignmentSHA256] || admitted[pilot.Assignment] {
				continue
			}
			gap := leader.MeasuredDPS - pilot.MeasuredDPS
			threshold := 4 * math.Hypot(leader.StandardError, pilot.StandardError)
			if math.IsInf(threshold, 0) || math.IsNaN(threshold) {
				return fmt.Errorf("staged promotion arithmetic is not finite")
			}
			yes := gap <= threshold
			receipt.Decisions = append(receipt.Decisions, StagedPromotionDecision{Stage: label, AssignmentSHA256: pilot.AssignmentSHA256, LeaderSHA256: leader.AssignmentSHA256, LeaderIterations: leader.Iterations, Gap: gap, Threshold: threshold, Promoted: yes})
			if yes {
				admitted[pilot.Assignment] = true
			}
		}
		return nil
	}
	if err = promote(order[0], "pilot_leader"); err != nil {
		return
	}
	admitted[order[0].Assignment] = true
	bestConfirmed := func() (MeasuredCandidate, bool) {
		var best MeasuredCandidate
		found := false
		for _, row := range latest {
			if row.Iterations != 500 {
				continue
			}
			if !found || row.MeasuredDPS > best.MeasuredDPS || row.MeasuredDPS == best.MeasuredDPS && row.AssignmentSHA256 < best.AssignmentSHA256 {
				best = row
				found = true
			}
		}
		return best, found
	}
	for wave := 1; wave <= len(candidates); wave++ {
		subset := make([]search.ScoredAssignment, 0, minInt(maxParallelism, cpuBudget))
		for _, pilot := range order {
			if admitted[pilot.Assignment] && !confirmed[pilot.Assignment] && !rejected[pilot.AssignmentSHA256] {
				subset = append(subset, originals[pilot.Assignment].candidate)
				if len(subset) == minInt(maxParallelism, cpuBudget) {
					break
				}
			}
		}
		if len(subset) == 0 {
			break
		}
		if err = stage(fmt.Sprintf("confirmation-%02d-n500", wave), subset, 500); err != nil {
			return
		}
		best, ok := bestConfirmed()
		if !ok {
			// An energy-rejected pilot leader cannot remain the output champion.
			for _, pilot := range order {
				if !rejected[pilot.AssignmentSHA256] && !confirmed[pilot.Assignment] {
					admitted[pilot.Assignment] = true
					break
				}
			}
		} else {
			if err = promote(best, fmt.Sprintf("after_confirmation_%d", wave)); err != nil {
				return
			}
		}
	}
	best, ok := bestConfirmed()
	if !ok {
		return output, fmt.Errorf("staged verification has no confirmed n500 winner")
	}
	for _, row := range latest {
		if row.Iterations == 100 && best.MeasuredDPS-row.MeasuredDPS <= 4*math.Hypot(best.StandardError, row.StandardError) {
			return output, fmt.Errorf("staged promotion budget left an eligible pilot")
		}
		output.Candidates = append(output.Candidates, row)
	}
	sort.Slice(output.Candidates, func(i, j int) bool { return output.Candidates[i].Rank < output.Candidates[j].Rank })
	output.Winner = best
	// A zero global count explicitly means mixed/per-candidate; product rows carry
	// their actual100 or500. The stages retain every independent measurement.
	output.Iterations = 0
	for key := range rejected {
		output.EnergyRejectedSHA256 = append(output.EnergyRejectedSHA256, key)
	}
	sort.Strings(output.EnergyRejectedSHA256)
	return output, nil
}

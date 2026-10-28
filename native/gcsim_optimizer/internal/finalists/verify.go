package finalists

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

type MeasuredCandidate struct {
	Rank               int               `json:"rank"`
	Source             string            `json:"source"`
	Assignment         domain.Assignment `json:"assignment"`
	AssignmentSHA256   string            `json:"assignment_sha256"`
	FormulaDPS         float64           `json:"formula_dps"`
	MeasuredDPS        float64           `json:"measured_dps"`
	StandardDeviation  float64           `json:"standard_deviation"`
	StandardError      float64           `json:"standard_error"`
	FormulaResidualDPS float64           `json:"formula_residual_dps"`
	Iterations         int               `json:"iterations"`
	ElapsedMS          float64           `json:"elapsed_ms"`
	ConfigSHA256       string            `json:"config_sha256"`
	EngineResultSHA256 string            `json:"engine_result_sha256"`
}

type VerificationResult struct {
	Candidates           []MeasuredCandidate   `json:"candidates"`
	Winner               MeasuredCandidate     `json:"winner"`
	Iterations           int                   `json:"iterations"`
	Workers              int                   `json:"workers,omitempty"`
	Parallelism          int                   `json:"parallelism,omitempty"`
	Waves                []VerificationWave    `json:"waves,omitempty"`
	Adaptive             *AdaptiveVerification `json:"adaptive,omitempty"`
	EnergyRejectedSHA256 []string              `json:"energy_rejected_sha256,omitempty"`
	TotalElapsedMS       float64               `json:"total_elapsed_ms"`
}

type NoEnergyFeasibleFinalistError struct {
	AssignmentSHA256 []string
	MaximumShortage  float64
	ElapsedMS        float64
}

func (err *NoEnergyFeasibleFinalistError) Error() string {
	return fmt.Sprintf("no finalist completed the intended rotation with finite energy (maximum shortage %.6f)", err.MaximumShortage)
}

type VerificationWave struct {
	Index          int     `json:"index"`
	StartRank      int     `json:"start_rank"`
	CandidateCount int     `json:"candidate_count"`
	Workers        int     `json:"workers"`
	Parallelism    int     `json:"parallelism"`
	TotalElapsedMS float64 `json:"total_elapsed_ms,omitempty"`
}

// CandidateRenderer binds a finalist to its own complete set context. It is
// trusted application code, not a user-provided score/activation certificate.
// The ordinary measurement, engine identity, CPU plan and iteration policy are
// shared by Selected and All Sets.
type CandidateRenderer func(search.ScoredAssignment, int, int) (RenderedConfig, error)

func FixedRenderer(request contracts.OptimizerRequest, index *domain.Index) CandidateRenderer {
	return func(c search.ScoredAssignment, iterations, workers int) (RenderedConfig, error) {
		return RenderConfig(request, index, c.Assignment, iterations, workers)
	}
}

func Verify(ctx context.Context, request contracts.OptimizerRequest, index *domain.Index, candidates []search.ScoredAssignment, runRoot string, iterations, workers, parallelism int) (VerificationResult, error) {
	return VerifyWithRenderer(ctx, request, candidates, FixedRenderer(request, index), runRoot, iterations, workers, parallelism)
}

func VerifyWithRenderer(ctx context.Context, request contracts.OptimizerRequest, candidates []search.ScoredAssignment, render CandidateRenderer, runRoot string, iterations, workers, parallelism int) (VerificationResult, error) {
	var output VerificationResult
	if render == nil {
		return output, fmt.Errorf("missing finalist context renderer")
	}
	if len(candidates) == 0 {
		return output, fmt.Errorf("at least one finalist is required")
	}
	if parallelism <= 0 || parallelism > len(candidates) {
		return output, fmt.Errorf("parallelism must be between one and finalist count")
	}
	fullCandidates, originals, err := prepareInventoryCandidates(request, candidates)
	if err != nil {
		return output, err
	}
	plan := []VerificationWave{{Index: 1, StartRank: 1, CandidateCount: len(candidates), Workers: workers, Parallelism: parallelism}}
	full, err := verifyFullBuildsWithPlan(
		ctx, request, fullCandidates, inventoryCandidateRenderer(render), runRoot, iterations, plan, nil, false,
	)
	if err != nil {
		if noEnergy, ok := asNoEnergyFullBuild(err); ok {
			identities, mapErr := assignmentIdentitiesForFullKeys(request, fullCandidates, originals, noEnergy.CandidateSHA256)
			if mapErr != nil {
				return output, mapErr
			}
			return output, &NoEnergyFeasibleFinalistError{AssignmentSHA256: identities, MaximumShortage: noEnergy.MaximumShortage, ElapsedMS: noEnergy.ElapsedMS}
		}
		return output, err
	}
	return adaptInventoryVerification(full, request, fullCandidates, originals, iterations, workers, parallelism, false)
}

type inventoryAssignmentIdentity struct {
	Kind       string            `json:"kind"`
	Assignment domain.Assignment `json:"assignment"`
}

type inventoryOriginalCandidate struct {
	candidate     search.ScoredAssignment
	rank          int
	assignmentSHA string
}

func prepareInventoryCandidates(request contracts.OptimizerRequest, candidates []search.ScoredAssignment) ([]FullBuildCandidate, map[domain.Assignment]inventoryOriginalCandidate, error) {
	prepared := make([]FullBuildCandidate, 0, len(candidates))
	originals := make(map[domain.Assignment]inventoryOriginalCandidate, len(candidates))
	seen := make(map[domain.Assignment]struct{}, len(candidates))
	for rank, candidate := range candidates {
		if _, exists := seen[candidate.Assignment]; exists {
			return nil, nil, fmt.Errorf("duplicate finalist assignment at rank %d", rank+1)
		}
		seen[candidate.Assignment] = struct{}{}
		identity, err := inventoryFullBuildIdentity(candidate.Assignment)
		if err != nil {
			return nil, nil, err
		}
		assignmentSHA, err := assignmentSHA256(candidate.Assignment)
		if err != nil {
			return nil, nil, err
		}
		prepared = append(prepared, FullBuildCandidate{
			BuildIdentity: identity,
			FormulaDPS:    candidate.DPS,
			Origins: []FullBuildOrigin{{
				Kind:          "inventory_search",
				Phase:         "finalist",
				Family:        candidate.Source,
				ContextSHA256: request.Context.ContextSHA256,
			}},
			tieBreakKey: assignmentSHA,
		})
		originals[candidate.Assignment] = inventoryOriginalCandidate{candidate: candidate, rank: rank + 1, assignmentSHA: assignmentSHA}
	}
	return prepared, originals, nil
}

func inventoryCandidateRenderer(render CandidateRenderer) FullBuildRenderer {
	return func(candidate FullBuildCandidate, iterations, workers int) (RenderedConfig, error) {
		var identity inventoryAssignmentIdentity
		if err := json.Unmarshal(candidate.BuildIdentity, &identity); err != nil {
			return RenderedConfig{}, fmt.Errorf("decode inventory full-build identity: %w", err)
		}
		if identity.Kind != "inventory_assignment_v1" || len(candidate.Origins) == 0 {
			return RenderedConfig{}, fmt.Errorf("inventory full-build identity is missing assignment provenance")
		}
		return render(search.ScoredAssignment{
			Assignment: identity.Assignment,
			DPS:        candidate.FormulaDPS,
			Source:     candidate.Origins[0].Family,
		}, iterations, workers)
	}
}

func adaptInventoryVerification(
	full FullBuildVerificationResult,
	request contracts.OptimizerRequest,
	fullCandidates []FullBuildCandidate,
	originals map[domain.Assignment]inventoryOriginalCandidate,
	iterations, workers, parallelism int,
	includeWaves bool,
) (VerificationResult, error) {
	var output VerificationResult
	frameSHA256, err := FullBuildFrameSHA256(request)
	if err != nil {
		return output, err
	}
	originalByFullKey := make(map[string]inventoryOriginalCandidate, len(fullCandidates))
	for _, candidate := range fullCandidates {
		var identity inventoryAssignmentIdentity
		if err := json.Unmarshal(candidate.BuildIdentity, &identity); err != nil {
			return output, fmt.Errorf("decode inventory full-build identity: %w", err)
		}
		original, ok := originals[identity.Assignment]
		if !ok {
			return output, fmt.Errorf("inventory full-build assignment is absent from input")
		}
		key, err := FullBuildCandidateSHA256(frameSHA256, candidate.BuildIdentity)
		if err != nil {
			return output, err
		}
		originalByFullKey[key] = original
	}
	rowsByFullKey := make(map[string]MeasuredCandidate, len(full.Measurements))
	output = VerificationResult{
		Iterations:     iterations,
		Workers:        workers,
		Parallelism:    parallelism,
		TotalElapsedMS: full.TotalElapsedMS,
	}
	if includeWaves {
		output.Waves = append([]VerificationWave(nil), full.Waves...)
	}
	for _, measurement := range full.Measurements {
		var identity inventoryAssignmentIdentity
		if err := json.Unmarshal(measurement.BuildIdentity, &identity); err != nil {
			return VerificationResult{}, fmt.Errorf("decode measured inventory identity: %w", err)
		}
		original, ok := originals[identity.Assignment]
		if !ok {
			return VerificationResult{}, fmt.Errorf("measured inventory assignment is absent from input")
		}
		row := MeasuredCandidate{
			Rank: original.rank, Source: original.candidate.Source, Assignment: original.candidate.Assignment,
			AssignmentSHA256: original.assignmentSHA, FormulaDPS: original.candidate.DPS,
			MeasuredDPS: measurement.MeasuredDPS, StandardDeviation: measurement.standardDeviationValue,
			StandardError:      measurement.standardErrorValue,
			FormulaResidualDPS: measurement.MeasuredDPS - original.candidate.DPS,
			Iterations:         measurement.Iterations, ElapsedMS: measurement.ElapsedMS,
			ConfigSHA256: measurement.ConfigSHA256, EngineResultSHA256: measurement.EngineResultSHA256,
		}
		output.Candidates = append(output.Candidates, row)
		rowsByFullKey[measurement.CandidateSHA256] = row
	}
	for _, fullKey := range full.EnergyRejectedSHA256 {
		original, ok := originalByFullKey[fullKey]
		if !ok {
			return VerificationResult{}, fmt.Errorf("energy-rejected inventory identity is absent from input")
		}
		output.EnergyRejectedSHA256 = append(output.EnergyRejectedSHA256, original.assignmentSHA)
	}
	if len(full.Measurements) == 0 {
		return output, nil
	}
	if full.Winner == nil {
		return VerificationResult{}, fmt.Errorf("full-build verification winner is missing")
	}
	winner, ok := rowsByFullKey[full.Winner.CandidateSHA256]
	if !ok {
		return VerificationResult{}, fmt.Errorf("full-build winner is absent from measured rows")
	}
	output.Winner = winner
	return output, nil
}

func assignmentIdentitiesForFullKeys(
	request contracts.OptimizerRequest,
	fullCandidates []FullBuildCandidate,
	originals map[domain.Assignment]inventoryOriginalCandidate,
	fullKeys []string,
) ([]string, error) {
	frameSHA256, err := FullBuildFrameSHA256(request)
	if err != nil {
		return nil, err
	}
	originalByFullKey := make(map[string]inventoryOriginalCandidate, len(fullCandidates))
	for _, candidate := range fullCandidates {
		var identity inventoryAssignmentIdentity
		if err := json.Unmarshal(candidate.BuildIdentity, &identity); err != nil {
			return nil, err
		}
		original, ok := originals[identity.Assignment]
		if !ok {
			return nil, fmt.Errorf("inventory full-build assignment is absent from input")
		}
		key, err := FullBuildCandidateSHA256(frameSHA256, candidate.BuildIdentity)
		if err != nil {
			return nil, err
		}
		originalByFullKey[key] = original
	}
	identities := make([]string, 0, len(fullKeys))
	for _, key := range fullKeys {
		original, ok := originalByFullKey[key]
		if !ok {
			return nil, fmt.Errorf("energy-rejected inventory identity is absent from input")
		}
		identities = append(identities, original.assignmentSHA)
	}
	return identities, nil
}

func asNoEnergyFullBuild(err error) (*NoEnergyFeasibleFullBuildError, bool) {
	var noEnergy *NoEnergyFeasibleFullBuildError
	matched := errors.As(err, &noEnergy)
	return noEnergy, matched
}

func finalizeVerificationRows(rows []MeasuredCandidate, valid []bool, shortages []float64, identities []string, iterations, workers, parallelism int, elapsedMS float64) (VerificationResult, error) {
	var output VerificationResult
	if len(rows) != len(valid) || len(rows) != len(shortages) || len(rows) != len(identities) {
		return output, fmt.Errorf("finalist verification vectors have different lengths")
	}
	accepted := make([]MeasuredCandidate, 0, len(rows))
	rejected := make([]string, 0)
	maximumShortage := 0.0
	for index, row := range rows {
		if valid[index] {
			accepted = append(accepted, row)
			continue
		}
		if shortages[index] > 0 {
			rejected = append(rejected, identities[index])
			if shortages[index] > maximumShortage {
				maximumShortage = shortages[index]
			}
		}
	}
	if len(accepted) == 0 {
		return output, &NoEnergyFeasibleFinalistError{AssignmentSHA256: rejected, MaximumShortage: maximumShortage, ElapsedMS: elapsedMS}
	}
	measuredOrder := append([]MeasuredCandidate(nil), accepted...)
	sort.Slice(measuredOrder, func(i, j int) bool {
		if measuredOrder[i].MeasuredDPS != measuredOrder[j].MeasuredDPS {
			return measuredOrder[i].MeasuredDPS > measuredOrder[j].MeasuredDPS
		}
		return measuredOrder[i].AssignmentSHA256 < measuredOrder[j].AssignmentSHA256
	})
	output = VerificationResult{
		Candidates: accepted, Winner: measuredOrder[0], Iterations: iterations, Workers: workers, Parallelism: parallelism,
		EnergyRejectedSHA256: rejected, TotalElapsedMS: elapsedMS,
	}
	return output, nil
}

// PlanDynamicWaves keeps every finalist while filling the available CPU budget
// in a bounded number of complete waves. A seven-row, 16-thread product run is
// therefore 4x4 followed by 3x5 rather than fixed 3x5 plus a third one-row wave.
func PlanDynamicWaves(candidateCount, maxParallelism, cpuBudget int) ([]VerificationWave, error) {
	if candidateCount <= 0 {
		return nil, fmt.Errorf("at least one finalist is required")
	}
	if maxParallelism <= 0 || cpuBudget <= 0 {
		return nil, fmt.Errorf("parallelism and CPU budget must be positive")
	}
	parallelLimit := minInt(maxParallelism, cpuBudget)
	waves := make([]VerificationWave, 0, (candidateCount+parallelLimit-1)/parallelLimit)
	for start := 0; start < candidateCount; {
		count := minInt(parallelLimit, candidateCount-start)
		workers := maxInt(1, cpuBudget/count)
		waves = append(waves, VerificationWave{
			Index:          len(waves) + 1,
			StartRank:      start + 1,
			CandidateCount: count,
			Workers:        workers,
			Parallelism:    count,
		})
		start += count
	}
	return waves, nil
}

// VerifyDynamicWaves executes the immutable plan sequentially and merges the
// rows into the same measured ordering contract as Verify. It never drops or
// duplicates a finalist.
func VerifyDynamicWaves(ctx context.Context, request contracts.OptimizerRequest, index *domain.Index, candidates []search.ScoredAssignment, runRoot string, iterations, maxParallelism, cpuBudget int) (VerificationResult, error) {
	return VerifyDynamicWavesWithRenderer(ctx, request, candidates, FixedRenderer(request, index), runRoot, iterations, maxParallelism, cpuBudget)
}

func VerifyDynamicWavesWithRenderer(ctx context.Context, request contracts.OptimizerRequest, candidates []search.ScoredAssignment, render CandidateRenderer, runRoot string, iterations, maxParallelism, cpuBudget int) (VerificationResult, error) {
	var output VerificationResult
	if _, err := PlanDynamicWaves(len(candidates), maxParallelism, cpuBudget); err != nil {
		return output, err
	}
	fullCandidates, originals, err := prepareInventoryCandidates(request, candidates)
	if err != nil {
		return output, err
	}
	full, err := VerifyFullBuildsWithRenderer(
		ctx, request, fullCandidates, inventoryCandidateRenderer(render), runRoot, iterations, maxParallelism, cpuBudget, nil,
	)
	if err != nil {
		if noEnergy, ok := asNoEnergyFullBuild(err); ok {
			identities, mapErr := assignmentIdentitiesForFullKeys(request, fullCandidates, originals, noEnergy.CandidateSHA256)
			if mapErr != nil {
				return output, mapErr
			}
			return output, &NoEnergyFeasibleFinalistError{AssignmentSHA256: identities, MaximumShortage: noEnergy.MaximumShortage, ElapsedMS: noEnergy.ElapsedMS}
		}
		wave := maxInt(1, len(full.Waves))
		return output, fmt.Errorf("verify dynamic wave %d: %w", wave, err)
	}
	return adaptInventoryVerification(full, request, fullCandidates, originals, iterations, 0, 0, true)
}

func minInt(left, right int) int {
	if left < right {
		return left
	}
	return right
}

func maxInt(left, right int) int {
	if left > right {
		return left
	}
	return right
}

func assignmentSHA256(assignment domain.Assignment) (string, error) {
	payload, err := json.Marshal(assignment)
	if err != nil {
		return "", err
	}
	digest := sha256.Sum256(payload)
	return hex.EncodeToString(digest[:]), nil
}

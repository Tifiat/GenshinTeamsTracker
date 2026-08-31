package finalists

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"sync"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
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
	Candidates     []MeasuredCandidate   `json:"candidates"`
	Winner         MeasuredCandidate     `json:"winner"`
	Iterations     int                   `json:"iterations"`
	Workers        int                   `json:"workers,omitempty"`
	Parallelism    int                   `json:"parallelism,omitempty"`
	Waves          []VerificationWave    `json:"waves,omitempty"`
	Adaptive       *AdaptiveVerification `json:"adaptive,omitempty"`
	TotalElapsedMS float64               `json:"total_elapsed_ms"`
}

type VerificationWave struct {
	Index          int     `json:"index"`
	StartRank      int     `json:"start_rank"`
	CandidateCount int     `json:"candidate_count"`
	Workers        int     `json:"workers"`
	Parallelism    int     `json:"parallelism"`
	TotalElapsedMS float64 `json:"total_elapsed_ms,omitempty"`
}

type preparedCandidate struct {
	rank      int
	candidate search.ScoredAssignment
	rendered  RenderedConfig
	identity  string
	runDir    string
}

func Verify(ctx context.Context, request contracts.OptimizerRequest, index *domain.Index, candidates []search.ScoredAssignment, runRoot string, iterations, workers, parallelism int) (VerificationResult, error) {
	var output VerificationResult
	if len(candidates) == 0 {
		return output, fmt.Errorf("at least one finalist is required")
	}
	if parallelism <= 0 || parallelism > len(candidates) {
		return output, fmt.Errorf("parallelism must be between one and finalist count")
	}
	if err := os.Mkdir(runRoot, 0o700); err != nil {
		return output, fmt.Errorf("create finalist root: %w", err)
	}
	started := time.Now()
	prepared := make([]preparedCandidate, 0, len(candidates))
	seen := make(map[domain.Assignment]struct{}, len(candidates))
	for rank, candidate := range candidates {
		if err := ctx.Err(); err != nil {
			return output, err
		}
		if _, exists := seen[candidate.Assignment]; exists {
			return output, fmt.Errorf("duplicate finalist assignment at rank %d", rank+1)
		}
		seen[candidate.Assignment] = struct{}{}
		rendered, err := RenderConfig(request, index, candidate.Assignment, iterations, workers)
		if err != nil {
			return output, fmt.Errorf("render finalist %d: %w", rank+1, err)
		}
		identity, err := assignmentSHA256(candidate.Assignment)
		if err != nil {
			return output, err
		}
		prepared = append(prepared, preparedCandidate{
			rank: rank, candidate: candidate, rendered: rendered, identity: identity,
			runDir: filepath.Join(runRoot, fmt.Sprintf("%02d-%s", rank+1, identity[:12])),
		})
	}
	runContext, cancel := context.WithCancel(ctx)
	defer cancel()
	rows := make([]MeasuredCandidate, len(prepared))
	jobs := make(chan preparedCandidate)
	errChannel := make(chan error, 1)
	var workersGroup sync.WaitGroup
	for workerIndex := 0; workerIndex < parallelism; workerIndex++ {
		workersGroup.Add(1)
		go func() {
			defer workersGroup.Done()
			for item := range jobs {
				measured, err := engineclient.RunOrdinary(runContext, request, item.rendered.Text, item.runDir, iterations, workers)
				if err != nil {
					select {
					case errChannel <- fmt.Errorf("verify finalist %d: %w", item.rank+1, err):
						cancel()
					default:
					}
					continue
				}
				if measured.ConfigSHA256 != item.rendered.SHA256 {
					select {
					case errChannel <- fmt.Errorf("finalist %d config identity changed across boundary", item.rank+1):
						cancel()
					default:
					}
					continue
				}
				candidate := item.candidate
				rows[item.rank] = MeasuredCandidate{
					Rank: item.rank + 1, Source: candidate.Source, Assignment: candidate.Assignment,
					AssignmentSHA256: item.identity, FormulaDPS: candidate.DPS, MeasuredDPS: measured.DPS,
					StandardDeviation: measured.StandardDeviation, StandardError: measured.StandardError,
					FormulaResidualDPS: measured.DPS - candidate.DPS, Iterations: measured.Iterations,
					ElapsedMS: measured.ElapsedMS, ConfigSHA256: measured.ConfigSHA256,
					EngineResultSHA256: measured.EngineResultSHA256,
				}
			}
		}()
	}
	for _, item := range prepared {
		select {
		case jobs <- item:
		case <-runContext.Done():
			break
		}
		if runContext.Err() != nil {
			break
		}
	}
	close(jobs)
	workersGroup.Wait()
	select {
	case err := <-errChannel:
		return output, err
	default:
	}
	if err := runContext.Err(); err != nil {
		return output, err
	}
	measuredOrder := append([]MeasuredCandidate(nil), rows...)
	sort.Slice(measuredOrder, func(i, j int) bool {
		if measuredOrder[i].MeasuredDPS != measuredOrder[j].MeasuredDPS {
			return measuredOrder[i].MeasuredDPS > measuredOrder[j].MeasuredDPS
		}
		return measuredOrder[i].AssignmentSHA256 < measuredOrder[j].AssignmentSHA256
	})
	output = VerificationResult{
		Candidates: rows, Winner: measuredOrder[0], Iterations: iterations, Workers: workers, Parallelism: parallelism,
		TotalElapsedMS: float64(time.Since(started)) / float64(time.Millisecond),
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
	var output VerificationResult
	plan, err := PlanDynamicWaves(len(candidates), maxParallelism, cpuBudget)
	if err != nil {
		return output, err
	}
	seen := make(map[domain.Assignment]struct{}, len(candidates))
	for rank, candidate := range candidates {
		if _, exists := seen[candidate.Assignment]; exists {
			return output, fmt.Errorf("duplicate finalist assignment at rank %d", rank+1)
		}
		seen[candidate.Assignment] = struct{}{}
	}
	if err := os.Mkdir(runRoot, 0o700); err != nil {
		return output, fmt.Errorf("create dynamic finalist root: %w", err)
	}
	started := time.Now()
	rows := make([]MeasuredCandidate, 0, len(candidates))
	waves := make([]VerificationWave, 0, len(plan))
	for _, wave := range plan {
		start := wave.StartRank - 1
		end := start + wave.CandidateCount
		waveRoot := filepath.Join(runRoot, fmt.Sprintf("wave-%02d", wave.Index))
		result, err := Verify(ctx, request, index, candidates[start:end], waveRoot, iterations, wave.Workers, wave.Parallelism)
		if err != nil {
			return output, fmt.Errorf("verify dynamic wave %d: %w", wave.Index, err)
		}
		for _, row := range result.Candidates {
			row.Rank += start
			rows = append(rows, row)
		}
		wave.TotalElapsedMS = result.TotalElapsedMS
		waves = append(waves, wave)
	}
	if len(rows) != len(candidates) {
		return output, fmt.Errorf("dynamic finalist result count %d does not match input %d", len(rows), len(candidates))
	}
	measuredOrder := append([]MeasuredCandidate(nil), rows...)
	sort.Slice(measuredOrder, func(i, j int) bool {
		if measuredOrder[i].MeasuredDPS != measuredOrder[j].MeasuredDPS {
			return measuredOrder[i].MeasuredDPS > measuredOrder[j].MeasuredDPS
		}
		return measuredOrder[i].AssignmentSHA256 < measuredOrder[j].AssignmentSHA256
	})
	return VerificationResult{
		Candidates: rows, Winner: measuredOrder[0], Iterations: iterations, Waves: waves,
		TotalElapsedMS: float64(time.Since(started)) / float64(time.Millisecond),
	}, nil
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

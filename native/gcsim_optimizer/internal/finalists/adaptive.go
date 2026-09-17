package finalists

import (
	"context"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

const (
	AdaptiveResolvedAtBase      = "resolved_at_base"
	AdaptiveExtendedLeaders     = "extended_unresolved_leaders"
	AdaptiveUnresolvedPanelWide = "unresolved_panel_too_wide"
)

type AdaptiveVerification struct {
	Status                   string   `json:"status"`
	BaseIterations           int      `json:"base_iterations"`
	ExtensionIterations      int      `json:"extension_iterations,omitempty"`
	SigmaThreshold           float64  `json:"sigma_threshold"`
	MaxExtensionCandidates   int      `json:"max_extension_candidates"`
	UnresolvedAtBaseSHA256   []string `json:"unresolved_at_base_sha256"`
	ExtendedAssignmentSHA256 []string `json:"extended_assignment_sha256,omitempty"`
	BaseElapsedMS            float64  `json:"base_elapsed_ms"`
	ExtensionElapsedMS       float64  `json:"extension_elapsed_ms,omitempty"`
}

// VerifyAdaptive runs one bounded panel for every finalist. It only spends a
// higher-fidelity pass on leaders whose measured gap is still inside the
// configured uncertainty boundary. A wide unresolved panel is returned as-is
// instead of making the bounded product path slower than the old full panel.
func VerifyAdaptive(
	ctx context.Context,
	request contracts.OptimizerRequest,
	index *domain.Index,
	candidates []search.ScoredAssignment,
	runRoot string,
	baseIterations, extensionIterations, maxParallelism, cpuBudget int,
	sigmaThreshold float64,
	maxExtensionCandidates int,
) (VerificationResult, error) {
	return VerifyAdaptiveWithRenderer(ctx, request, candidates, FixedRenderer(request, index), runRoot, baseIterations, extensionIterations, maxParallelism, cpuBudget, sigmaThreshold, maxExtensionCandidates)
}

func VerifyAdaptiveWithRenderer(ctx context.Context, request contracts.OptimizerRequest, candidates []search.ScoredAssignment, render CandidateRenderer, runRoot string, baseIterations, extensionIterations, maxParallelism, cpuBudget int, sigmaThreshold float64, maxExtensionCandidates int) (VerificationResult, error) {
	var output VerificationResult
	if baseIterations <= 0 || extensionIterations <= baseIterations {
		return output, fmt.Errorf("adaptive verification requires a positive base and a larger extension iteration count")
	}
	if sigmaThreshold <= 0 || maxExtensionCandidates < 2 {
		return output, fmt.Errorf("adaptive verification threshold and extension bound are invalid")
	}
	if err := os.Mkdir(runRoot, 0o700); err != nil {
		return output, fmt.Errorf("create adaptive finalist root: %w", err)
	}
	base, err := VerifyDynamicWavesWithRenderer(
		ctx, request, candidates, render,
		filepath.Join(runRoot, fmt.Sprintf("base-n%d", baseIterations)),
		baseIterations, maxParallelism, cpuBudget,
	)
	if err != nil {
		return output, fmt.Errorf("adaptive base panel: %w", err)
	}
	unresolved := unresolvedLeaderRows(base.Candidates, sigmaThreshold)
	metadata := &AdaptiveVerification{
		Status:                 AdaptiveResolvedAtBase,
		BaseIterations:         baseIterations,
		ExtensionIterations:    extensionIterations,
		SigmaThreshold:         sigmaThreshold,
		MaxExtensionCandidates: maxExtensionCandidates,
		UnresolvedAtBaseSHA256: assignmentIdentities(unresolved),
		BaseElapsedMS:          base.TotalElapsedMS,
	}
	base.Adaptive = metadata
	if len(unresolved) <= 1 {
		return base, nil
	}
	if len(unresolved) > maxExtensionCandidates {
		metadata.Status = AdaptiveUnresolvedPanelWide
		return base, nil
	}
	candidateByAssignment := make(map[domain.Assignment]search.ScoredAssignment, len(candidates))
	for _, candidate := range candidates {
		candidateByAssignment[candidate.Assignment] = candidate
	}
	extensionCandidates := make([]search.ScoredAssignment, 0, len(unresolved))
	for _, row := range unresolved {
		candidate, ok := candidateByAssignment[row.Assignment]
		if !ok {
			return output, fmt.Errorf("adaptive unresolved assignment is absent from candidate input")
		}
		extensionCandidates = append(extensionCandidates, candidate)
	}
	extension, err := VerifyDynamicWavesWithRenderer(
		ctx, request, extensionCandidates, render,
		filepath.Join(runRoot, fmt.Sprintf("extension-n%d", extensionIterations)),
		extensionIterations, maxParallelism, cpuBudget,
	)
	if err != nil {
		return output, fmt.Errorf("adaptive extension panel: %w", err)
	}
	merged, err := mergeExtendedRows(base, extension)
	if err != nil {
		return output, err
	}
	metadata.Status = AdaptiveExtendedLeaders
	metadata.ExtendedAssignmentSHA256 = assignmentIdentities(extension.Candidates)
	metadata.ExtensionElapsedMS = extension.TotalElapsedMS
	merged.Adaptive = metadata
	return merged, nil
}

func unresolvedLeaderRows(rows []MeasuredCandidate, sigmaThreshold float64) []MeasuredCandidate {
	ordered := measuredOrder(rows)
	if len(ordered) == 0 {
		return nil
	}
	leader := ordered[0]
	unresolved := []MeasuredCandidate{leader}
	for _, contender := range ordered[1:] {
		gap := leader.MeasuredDPS - contender.MeasuredDPS
		gapSE := math.Hypot(leader.StandardError, contender.StandardError)
		if gap <= sigmaThreshold*gapSE {
			unresolved = append(unresolved, contender)
		}
	}
	return unresolved
}

func mergeExtendedRows(base, extension VerificationResult) (VerificationResult, error) {
	if len(base.Candidates) == 0 || len(extension.Candidates) == 0 {
		return VerificationResult{}, fmt.Errorf("adaptive merge requires base and extension rows")
	}
	extended := make(map[string]MeasuredCandidate, len(extension.Candidates))
	for _, row := range extension.Candidates {
		extended[row.AssignmentSHA256] = row
	}
	rows := append([]MeasuredCandidate(nil), base.Candidates...)
	replaced := 0
	for index, row := range rows {
		if replacement, ok := extended[row.AssignmentSHA256]; ok {
			replacement.Rank = row.Rank
			rows[index] = replacement
			replaced++
		}
	}
	if replaced != len(extension.Candidates) {
		return VerificationResult{}, fmt.Errorf("adaptive extension contains a row absent from the base panel")
	}
	ordered := measuredOrder(rows)
	return VerificationResult{
		Candidates:     rows,
		Winner:         ordered[0],
		Iterations:     base.Iterations,
		TotalElapsedMS: base.TotalElapsedMS + extension.TotalElapsedMS,
	}, nil
}

func measuredOrder(rows []MeasuredCandidate) []MeasuredCandidate {
	ordered := append([]MeasuredCandidate(nil), rows...)
	sort.Slice(ordered, func(i, j int) bool {
		if ordered[i].MeasuredDPS != ordered[j].MeasuredDPS {
			return ordered[i].MeasuredDPS > ordered[j].MeasuredDPS
		}
		return ordered[i].AssignmentSHA256 < ordered[j].AssignmentSHA256
	})
	return ordered
}

func assignmentIdentities(rows []MeasuredCandidate) []string {
	identities := make([]string, 0, len(rows))
	for _, row := range rows {
		identities = append(identities, row.AssignmentSHA256)
	}
	return identities
}

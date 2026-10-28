package main

import (
	"fmt"
	"math"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

type productGroupBonus struct {
	SetUID string `json:"set_uid"`
	Pieces int    `json:"pieces"`
}

type productGroupWearer struct {
	WearerKey string              `json:"wearer_key"`
	Bonuses   []productGroupBonus `json:"bonuses"`
}

type groupedProductRow struct {
	Assignment domain.Assignment
	GroupKey   string
	FormulaDPS float64
	RankingDPS float64
	Measured   *finalists.MeasuredCandidate
}

func buildGroupedProductResult(
	request contracts.OptimizerRequest,
	compactSHA, setPanelSHA string,
	opaqueReasons, extraWarnings []string,
	proposals []search.ScoredAssignment,
	verification *finalists.VerificationResult,
	debugReceiptPath string,
) (contracts.OptimizerResult, error) {
	if err := request.Validate(); err != nil {
		return contracts.OptimizerResult{}, fmt.Errorf("validate grouped product request: %w", err)
	}
	options := request.EffectiveResultOptions()
	if verification == nil && !options.FastMode {
		return contracts.OptimizerResult{}, fmt.Errorf("formula-only product result requires fast_mode")
	}
	proposalRows, err := groupedProposals(request, proposals)
	if err != nil {
		return contracts.OptimizerResult{}, err
	}
	if len(proposalRows) == 0 {
		return contracts.OptimizerResult{}, fmt.Errorf("grouped product result requires at least one proposal")
	}

	rankingBasis := "formula"
	rows := make([]groupedProductRow, 0, len(proposalRows))
	if verification == nil {
		rows = proposalRows
	} else {
		rankingBasis = "gcsim"
		proposed := make(map[domain.Assignment]groupedProductRow, len(proposalRows))
		for _, row := range proposalRows {
			proposed[row.Assignment] = row
		}
		measuredAssignments := make(map[domain.Assignment]struct{}, len(verification.Candidates))
		for index, candidate := range verification.Candidates {
			proposal, exists := proposed[candidate.Assignment]
			if !exists {
				// The product view only reports caller-approved proposals. This also
				// keeps test controls from being injected by the measurement wrapper.
				continue
			}
			if _, exists := measuredAssignments[candidate.Assignment]; exists {
				return contracts.OptimizerResult{}, fmt.Errorf("verification repeats measured assignment at candidate %d", index)
			}
			measuredAssignments[candidate.Assignment] = struct{}{}
			if err := validateMeasuredCandidate(candidate); err != nil {
				return contracts.OptimizerResult{}, fmt.Errorf("verification candidate %d: %w", index, err)
			}
			proposal.FormulaDPS = candidate.FormulaDPS
			proposal.RankingDPS = candidate.MeasuredDPS
			copyCandidate := candidate
			proposal.Measured = &copyCandidate
			rows = append(rows, proposal)
		}
		if len(rows) == 0 {
			return contracts.OptimizerResult{}, fmt.Errorf("verification has no measured product proposal")
		}
	}

	selected := selectGroupedProductRows(rows, options)
	if len(selected) == 0 {
		return contracts.OptimizerResult{}, fmt.Errorf("result options selected no product candidates")
	}
	if verification != nil {
		if _, included := findGroupedProductRow(selected, verification.Winner.Assignment); !included {
			return contracts.OptimizerResult{}, fmt.Errorf("measured winner is outside the configured product groups")
		}
	}

	requestSHA, err := contracts.CanonicalSHA256(request)
	if err != nil {
		return contracts.OptimizerResult{}, fmt.Errorf("identify grouped product request: %w", err)
	}
	warnings := []string{}
	if verification == nil {
		warnings = append(warnings, "formula_only_unverified")
		ignoreBurstEnergy, energyErr := setcontext.IgnoreBurstEnergy(request.Context.PreparedConfig.Text)
		if energyErr != nil {
			return contracts.OptimizerResult{}, fmt.Errorf("read product energy policy: %w", energyErr)
		}
		if !ignoreBurstEnergy {
			warnings = append(warnings, "energy_not_simulator_verified")
		}
	} else {
		warnings = append(warnings, "formula_rank_not_measurement_authority")
		if verification.Adaptive != nil && verification.Adaptive.Status == finalists.AdaptiveUnresolvedPanelWide {
			warnings = append(warnings, "adaptive_finalist_panel_too_wide")
		}
		if len(verification.EnergyRejectedSHA256) > 0 {
			warnings = append(warnings, "final_energy_infeasible_candidates_rejected")
		}
	}
	if len(opaqueReasons) > 0 {
		warnings = append(warnings, "opaque_formula_boundaries_present")
	}
	warnings = append(warnings, extraWarnings...)
	warnings = uniqueSortedTokens(warnings)

	candidates := make([]contracts.RankedCandidateResult, 0, len(selected))
	for index, row := range selected {
		assignments := productAssignments(request, row.Assignment)
		candidate := contracts.RankedCandidateResult{
			Rank:            index + 1,
			Artifacts:       assignments,
			FormulaDPS:      decimalText(row.FormulaDPS),
			SetGroupKey:     row.GroupKey,
			SetGroupRank:    selectedGroupRank(selected, index),
			AlternativeRank: selectedAlternativeRank(selected, index),
		}
		if row.Measured != nil {
			candidate.Measured = &contracts.MeasuredResult{
				Iterations:         row.Measured.Iterations,
				DPS:                decimalText(row.Measured.MeasuredDPS),
				StandardError:      decimalText(row.Measured.StandardError),
				EngineResultSHA256: row.Measured.EngineResultSHA256,
			}
			candidate.FormulaResidual = decimalText(row.Measured.FormulaResidualDPS)
		}
		candidates = append(candidates, candidate)
	}

	first := selected[0]
	result := contracts.OptimizerResult{
		SchemaVersion:         contracts.SchemaVersion,
		SchemaKind:            contracts.ResultSchemaKind,
		RequestSHA256:         requestSHA,
		CompactIRSHA256:       compactSHA,
		SetContextPanelSHA256: setPanelSHA,
		RankingBasis:          rankingBasis,
		Status:                "success",
		Winner:                productAssignments(request, first.Assignment),
		Candidates:            candidates,
		FormulaDPS:            decimalText(first.FormulaDPS),
		Warnings:              warnings,
		DebugReceiptPath:      debugReceiptPath,
	}
	if first.Measured != nil {
		result.Measured = &contracts.MeasuredResult{
			Iterations:         first.Measured.Iterations,
			DPS:                decimalText(first.Measured.MeasuredDPS),
			StandardError:      decimalText(first.Measured.StandardError),
			EngineResultSHA256: first.Measured.EngineResultSHA256,
		}
		result.FormulaResidual = decimalText(first.Measured.FormulaResidualDPS)
		measuredOrder := append([]groupedProductRow(nil), selected...)
		sort.Slice(measuredOrder, func(i, j int) bool {
			if measuredOrder[i].RankingDPS != measuredOrder[j].RankingDPS {
				return measuredOrder[i].RankingDPS > measuredOrder[j].RankingDPS
			}
			return compareDomainAssignments(measuredOrder[i].Assignment, measuredOrder[j].Assignment) < 0
		})
		if len(measuredOrder) > 1 {
			second := measuredOrder[1].Measured
			if second != nil && measuredOrder[0].Measured.MeasuredDPS-second.MeasuredDPS <= 1.96*math.Hypot(measuredOrder[0].Measured.StandardError, second.StandardError) {
				result.Warnings = uniqueSortedTokens(append(result.Warnings, "measured_top_confidence_overlap"))
			}
		}
	}
	if err := result.Validate(); err != nil {
		return contracts.OptimizerResult{}, fmt.Errorf("validate grouped product result: %w", err)
	}
	return result, nil
}

func groupedProposals(request contracts.OptimizerRequest, proposals []search.ScoredAssignment) ([]groupedProductRow, error) {
	artifacts := make(map[int64]contracts.Artifact, len(request.Artifacts))
	for _, artifact := range request.Artifacts {
		artifacts[artifact.ArtifactID] = artifact
	}
	rowsByAssignment := make(map[domain.Assignment]groupedProductRow, len(proposals))
	for index, proposal := range proposals {
		if math.IsNaN(proposal.DPS) || math.IsInf(proposal.DPS, 0) || proposal.DPS < 0 {
			return nil, fmt.Errorf("proposal %d DPS must be finite and non-negative", index)
		}
		groupKey, err := canonicalProductGroupKey(request, artifacts, proposal.Assignment)
		if err != nil {
			return nil, fmt.Errorf("proposal %d: %w", index, err)
		}
		row := groupedProductRow{
			Assignment: proposal.Assignment,
			GroupKey:   groupKey,
			FormulaDPS: proposal.DPS,
			RankingDPS: proposal.DPS,
		}
		if prior, exists := rowsByAssignment[proposal.Assignment]; !exists || row.FormulaDPS > prior.FormulaDPS {
			rowsByAssignment[proposal.Assignment] = row
		}
	}
	rows := make([]groupedProductRow, 0, len(rowsByAssignment))
	for _, row := range rowsByAssignment {
		rows = append(rows, row)
	}
	return rows, nil
}

func canonicalProductGroupKey(request contracts.OptimizerRequest, artifacts map[int64]contracts.Artifact, assignment domain.Assignment) (string, error) {
	used := make(map[int64]struct{}, 20)
	wearers := make([]productGroupWearer, 0, len(request.Wearers))
	for wearerIndex, wearer := range request.Wearers {
		counts := make(map[string]int)
		for slotIndex, artifactID := range assignment[wearerIndex] {
			if artifactID <= 0 {
				return "", fmt.Errorf("assignment must use twenty positive physical artifact IDs")
			}
			if _, exists := used[artifactID]; exists {
				return "", fmt.Errorf("assignment repeats physical artifact ID %d", artifactID)
			}
			used[artifactID] = struct{}{}
			artifact, exists := artifacts[artifactID]
			if !exists {
				return "", fmt.Errorf("assignment references unknown artifact ID %d", artifactID)
			}
			if slotIndex >= len(wearer.CurrentArtifacts) || artifact.Slot != wearer.CurrentArtifacts[slotIndex].Slot {
				return "", fmt.Errorf("artifact %d does not match wearer %s slot %d", artifactID, wearer.WearerKey, slotIndex)
			}
			counts[artifact.SetUID]++
		}
		bonuses := make([]productGroupBonus, 0, len(counts))
		setUIDs := make([]string, 0, len(counts))
		for setUID := range counts {
			setUIDs = append(setUIDs, setUID)
		}
		sort.Strings(setUIDs)
		for _, setUID := range setUIDs {
			count := counts[setUID]
			pieces := 0
			switch {
			case count >= 4:
				pieces = 4
			case count >= 2:
				pieces = 2
			default:
				continue
			}
			bonuses = append(bonuses, productGroupBonus{SetUID: setUID, Pieces: pieces})
		}
		wearers = append(wearers, productGroupWearer{WearerKey: wearer.WearerKey, Bonuses: bonuses})
	}
	encoded, err := contracts.CanonicalJSON(wearers)
	if err != nil {
		return "", fmt.Errorf("encode canonical set-group key: %w", err)
	}
	return string(encoded), nil
}

func validateMeasuredCandidate(candidate finalists.MeasuredCandidate) error {
	for label, value := range map[string]float64{
		"formula_dps":    candidate.FormulaDPS,
		"measured_dps":   candidate.MeasuredDPS,
		"standard_error": candidate.StandardError,
	} {
		if math.IsNaN(value) || math.IsInf(value, 0) || value < 0 {
			return fmt.Errorf("%s must be finite and non-negative", label)
		}
	}
	if math.IsNaN(candidate.FormulaResidualDPS) || math.IsInf(candidate.FormulaResidualDPS, 0) {
		return fmt.Errorf("formula residual must be finite")
	}
	if candidate.Iterations <= 0 {
		return fmt.Errorf("measured iterations must be positive")
	}
	if err := validateDigest(candidate.EngineResultSHA256); err != nil {
		return fmt.Errorf("engine result identity: %w", err)
	}
	return nil
}

func validateDigest(value string) error {
	if len(value) != 64 {
		return fmt.Errorf("must be a lowercase SHA-256 digest")
	}
	for _, character := range value {
		if !(character >= '0' && character <= '9' || character >= 'a' && character <= 'f') {
			return fmt.Errorf("must be a lowercase SHA-256 digest")
		}
	}
	return nil
}

func selectGroupedProductRows(rows []groupedProductRow, options contracts.ResultOptions) []groupedProductRow {
	groupsByKey := make(map[string][]groupedProductRow)
	for _, row := range rows {
		groupsByKey[row.GroupKey] = append(groupsByKey[row.GroupKey], row)
	}
	groups := make([][]groupedProductRow, 0, len(groupsByKey))
	for _, group := range groupsByKey {
		sort.Slice(group, func(i, j int) bool {
			if group[i].RankingDPS != group[j].RankingDPS {
				return group[i].RankingDPS > group[j].RankingDPS
			}
			return compareDomainAssignments(group[i].Assignment, group[j].Assignment) < 0
		})
		// Measured reranking can replace the formula anchor. Only neighbours of
		// the actually displayed leader get per-item DPS labels; two independent
		// substitutions must never masquerade as one replacement.
		filtered := group[:1]
		for _, row := range group[1:] {
			if search.AssignmentDistance(group[0].Assignment, row.Assignment) == 1 {
				filtered = append(filtered, row)
			}
		}
		group = filtered
		if len(group) > options.BuildsPerGroup {
			group = group[:options.BuildsPerGroup]
		}
		groups = append(groups, group)
	}
	sort.Slice(groups, func(i, j int) bool {
		left, right := groups[i][0], groups[j][0]
		if left.RankingDPS != right.RankingDPS {
			return left.RankingDPS > right.RankingDPS
		}
		return left.GroupKey < right.GroupKey
	})
	if len(groups) > options.SetGroupLimit {
		groups = groups[:options.SetGroupLimit]
	}
	// Allocate for observed rows, never the potentially unbounded requested count.
	output := make([]groupedProductRow, 0, len(rows))
	for _, group := range groups {
		output = append(output, group...)
	}
	return output
}

func selectedGroupRank(rows []groupedProductRow, index int) int {
	rank := 1
	for current := 1; current <= index; current++ {
		if rows[current].GroupKey != rows[current-1].GroupKey {
			rank++
		}
	}
	return rank
}

func selectedAlternativeRank(rows []groupedProductRow, index int) int {
	rank := 1
	for current := index; current > 0 && rows[current].GroupKey == rows[current-1].GroupKey; current-- {
		rank++
	}
	return rank
}

func compareDomainAssignments(left, right domain.Assignment) int {
	for wearer := range left {
		for slot := range left[wearer] {
			if left[wearer][slot] < right[wearer][slot] {
				return -1
			}
			if left[wearer][slot] > right[wearer][slot] {
				return 1
			}
		}
	}
	return 0
}

func findGroupedProductRow(rows []groupedProductRow, assignment domain.Assignment) (groupedProductRow, bool) {
	for _, row := range rows {
		if row.Assignment == assignment {
			return row, true
		}
	}
	return groupedProductRow{}, false
}

func uniqueSortedTokens(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	for _, value := range values {
		seen[value] = struct{}{}
	}
	output := make([]string, 0, len(seen))
	for value := range seen {
		output = append(output, value)
	}
	sort.Strings(output)
	return output
}

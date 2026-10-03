package main

import (
	"fmt"
	"math"
	"strconv"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

func TestBuildGroupedFormulaOnlyProductResult(t *testing.T) {
	request, _ := productFixtures(t)
	request = withResultOptionsAndEnergyPolicy(t, request, contracts.ResultOptions{
		SetGroupLimit: 2, BuildsPerGroup: 2, FastMode: true,
	})
	request = addArtifactVariants(t, request, 4, func(variant int, _ contracts.Artifact) string {
		if variant <= 2 {
			return "alt_set"
		}
		return "second_set"
	})

	proposals := []search.ScoredAssignment{
		{Assignment: variantAssignment(request, 0), DPS: 80},
		{Assignment: variantAssignment(request, 3), DPS: 90},
		{Assignment: oneSwapAssignment(request, 1, 2), DPS: 95},
		{Assignment: oneSwapAssignment(request, 3, 4), DPS: 85},
		{Assignment: variantAssignment(request, 1), DPS: 100},
	}
	result, err := buildGroupedProductResult(
		request,
		strings.Repeat("a", 64), "",
		nil, nil, proposals, nil, "debug/grouped-result.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	if result.RankingBasis != "formula" || result.Measured != nil || result.FormulaResidual != "" {
		t.Fatalf("unexpected formula-only header: %+v", result)
	}
	if len(result.Candidates) != 4 || result.FormulaDPS != "100" || !containsString(result.Warnings, "formula_only_unverified") {
		t.Fatalf("unexpected formula-only candidates or warnings: %+v", result)
	}
	wantScores := []string{"100", "95", "90", "85"}
	wantGroupRanks := []int{1, 1, 2, 2}
	wantAlternativeRanks := []int{1, 2, 1, 2}
	for index, candidate := range result.Candidates {
		if candidate.FormulaDPS != wantScores[index] || candidate.SetGroupRank != wantGroupRanks[index] || candidate.AlternativeRank != wantAlternativeRanks[index] {
			t.Fatalf("candidate %d has incorrect grouped order: %+v", index, candidate)
		}
		if candidate.Measured != nil || candidate.FormulaResidual != "" {
			t.Fatalf("formula-only candidate %d contains measured output", index)
		}
	}
	if err := result.Validate(); err != nil {
		t.Fatalf("formula-only product result should validate: %v", err)
	}
	finiteRequest := setTestEnergyMode(t, request, false)
	finiteResult, err := buildGroupedProductResult(
		finiteRequest, strings.Repeat("a", 64), "", nil, nil, proposals, nil, "debug/finite-fast-result.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	if !containsString(finiteResult.Warnings, "energy_not_simulator_verified") {
		t.Fatalf("finite formula-only result is missing its energy verification warning: %v", finiteResult.Warnings)
	}

	request.ResultOptions.FastMode = false
	if _, err := buildGroupedProductResult(request, strings.Repeat("a", 64), "", nil, nil, proposals, nil, "debug/result.json"); err == nil {
		t.Fatal("nil verification should require fast mode")
	}
}

func TestGroupedSelectionAllocatesOnlyObservedRows(t *testing.T) {
	rows := []groupedProductRow{{GroupKey: "one", FormulaDPS: 100, RankingDPS: 100}}
	// Deliberately far above request bounds: this helper must never allocate G*K.
	options := contracts.ResultOptions{SetGroupLimit: 1_000_000_000, BuildsPerGroup: 1_000_000_000}
	got := selectGroupedProductRows(rows, options)
	if len(got) != 1 || cap(got) > len(rows) {
		t.Fatalf("requested counts must not allocate absent rows: len=%d cap=%d", len(got), cap(got))
	}
}

func TestBuildGroupedMeasuredProductReturnsSingleSwapsWithoutControlInjection(t *testing.T) {
	request, _ := productFixtures(t)
	request = withResultOptionsAndEnergyPolicy(t, request, contracts.ResultOptions{
		SetGroupLimit: 1, BuildsPerGroup: 4,
	})
	request = addArtifactVariants(t, request, 6, func(int, contracts.Artifact) string { return "shared_set" })
	proposals := make([]search.ScoredAssignment, 0, 6)
	measured := make([]finalists.MeasuredCandidate, 0, 6)
	for variant := 4; variant >= 1; variant-- {
		assignment := oneSwapAssignment(request, 1, variant)
		formula := float64(100 - variant)
		dps := float64(200 - variant)
		proposals = append(proposals, search.ScoredAssignment{Assignment: assignment, DPS: formula})
		measured = append(measured, finalists.MeasuredCandidate{
			Assignment: assignment, FormulaDPS: formula, MeasuredDPS: dps,
			StandardError: 2, FormulaResidualDPS: dps - formula, Iterations: 1000,
			AssignmentSHA256: strings.Repeat("1", 64), EngineResultSHA256: strings.Repeat("2", 64),
		})
	}
	winner := measured[len(measured)-1]
	verification := &finalists.VerificationResult{Candidates: measured, Winner: winner}
	result, err := buildGroupedProductResult(
		request,
		"", strings.Repeat("b", 64),
		nil, nil, proposals, verification, "debug/grouped-measured-result.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	if result.RankingBasis != "gcsim" || len(result.Candidates) != 4 {
		t.Fatalf("expected all six measured alternatives, got basis=%q count=%d", result.RankingBasis, len(result.Candidates))
	}
	if result.Measured == nil || result.Measured.DPS != "199" || result.Candidates[0].Measured == nil || result.Candidates[0].Measured.DPS != "199" {
		t.Fatalf("winner measurement was not retained: %+v", result)
	}
	for index, candidate := range result.Candidates {
		if candidate.SetGroupRank != 1 || candidate.AlternativeRank != index+1 || candidate.Measured == nil {
			t.Fatalf("candidate %d lost measured group data: %+v", index, candidate)
		}
	}
	if err := result.Validate(); err != nil {
		t.Fatalf("measured grouped product should validate: %v", err)
	}
}

func TestBuildGroupedMeasuredProductPreservesContractWarningsAndIdentity(t *testing.T) {
	request, compact := productFixtures(t)
	request = withResultOptionsAndEnergyPolicy(t, request, contracts.ResultOptions{
		SetGroupLimit: 1, BuildsPerGroup: 2,
	})
	request = addArtifactVariants(t, request, 2, func(int, contracts.Artifact) string { return "shared_set" })
	winnerAssignment := oneSwapAssignment(request, 1, 1)
	alternateAssignment := oneSwapAssignment(request, 1, 2)
	winner := finalists.MeasuredCandidate{
		Assignment: winnerAssignment, FormulaDPS: 100, MeasuredDPS: 110,
		StandardError: 2, FormulaResidualDPS: 10, Iterations: 500,
		AssignmentSHA256: strings.Repeat("7", 64), EngineResultSHA256: strings.Repeat("8", 64),
	}
	alternate := finalists.MeasuredCandidate{
		Assignment: alternateAssignment, FormulaDPS: 99, MeasuredDPS: 109,
		StandardError: 2, FormulaResidualDPS: 10, Iterations: 500,
		AssignmentSHA256: strings.Repeat("9", 64), EngineResultSHA256: strings.Repeat("a", 64),
	}
	verification := &finalists.VerificationResult{
		Winner:               winner,
		Candidates:           []finalists.MeasuredCandidate{alternate, winner},
		Adaptive:             &finalists.AdaptiveVerification{Status: finalists.AdaptiveUnresolvedPanelWide},
		EnergyRejectedSHA256: []string{strings.Repeat("b", 64)},
	}
	requestSHA, err := contracts.CanonicalSHA256(request)
	if err != nil {
		t.Fatal(err)
	}
	compactSHA, err := contracts.CanonicalSHA256(compact)
	if err != nil {
		t.Fatal(err)
	}
	debugPath := "debug/grouped-measured-result.json"
	result, err := buildGroupedProductResult(
		request, compactSHA, "", []string{"unknown"}, nil,
		[]search.ScoredAssignment{
			{Assignment: alternateAssignment, DPS: 99},
			{Assignment: winnerAssignment, DPS: 100},
		},
		verification, debugPath,
	)
	if err != nil {
		t.Fatal(err)
	}
	if err := result.Validate(); err != nil {
		t.Fatal(err)
	}
	if result.RequestSHA256 != requestSHA || result.CompactIRSHA256 != compactSHA || result.SetContextPanelSHA256 != "" || result.DebugReceiptPath != debugPath {
		t.Fatalf("grouped result lost request, panel, or receipt identity: %+v", result)
	}
	if result.RankingBasis != "gcsim" || result.Status != "success" || productWinnerAssignment(request, result) != winnerAssignment {
		t.Fatalf("unexpected grouped measured winner: %+v", result)
	}
	if len(result.Winner) != 20 || len(result.Candidates) != 2 || result.FormulaDPS != "100" || result.FormulaResidual != "10" || result.Measured == nil || result.Measured.DPS != "110" || result.Measured.EngineResultSHA256 != winner.EngineResultSHA256 {
		t.Fatalf("grouped measured summary lost winner fields: %+v", result)
	}
	if result.Candidates[0].Rank != 1 || result.Candidates[0].Measured == nil || result.Candidates[0].Measured.DPS != "110" || result.Candidates[1].Measured == nil || result.Candidates[1].Measured.DPS != "109" {
		t.Fatalf("grouped measured order lost measurement fields: %+v", result.Candidates)
	}
	for _, warning := range []string{
		"formula_rank_not_measurement_authority",
		"opaque_formula_boundaries_present",
		"adaptive_finalist_panel_too_wide",
		"measured_top_confidence_overlap",
		"final_energy_infeasible_candidates_rejected",
	} {
		if !containsString(result.Warnings, warning) {
			t.Fatalf("grouped measured result missing %q: %v", warning, result.Warnings)
		}
	}
}

func TestGroupedProductBoundaryCapsAt49AndSupportsSingleRow(t *testing.T) {
	request, proposals, measured := groupedBoundaryFixture(t)
	result, err := buildGroupedProductResult(
		request, strings.Repeat("c", 64), "", nil, nil, proposals, nil, "debug/grouped-49-formula.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	assertGroupedBoundaryRows(t, result, 49, 7, 7)
	if result.RankingBasis != "formula" {
		t.Fatalf("formula boundary result has ranking basis %q", result.RankingBasis)
	}

	request.ResultOptions.FastMode = false
	request.ResultOptions.SetGroupLimit, request.ResultOptions.BuildsPerGroup = 5, 4
	verification := &finalists.VerificationResult{Candidates: measured, Winner: measured[0]}
	measuredResult, err := buildGroupedProductResult(
		request, "", strings.Repeat("d", 64), nil, nil, proposals, verification, "debug/grouped-49-measured.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	assertGroupedBoundaryRows(t, measuredResult, 20, 5, 4)
	if measuredResult.RankingBasis != "gcsim" || measuredResult.Candidates[0].Measured == nil || measuredResult.Candidates[0].Measured.Iterations != 500 {
		t.Fatalf("measured boundary result lost its n500 rows: %+v", measuredResult.Candidates[0])
	}

	request.ResultOptions = &contracts.ResultOptions{SetGroupLimit: 1, BuildsPerGroup: 1, FastMode: true}
	single, err := buildGroupedProductResult(
		request, strings.Repeat("c", 64), "", nil, nil, proposals, nil, "debug/grouped-single.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	assertGroupedBoundaryRows(t, single, 1, 1, 1)
}

func TestGroupedProductFastBoundedReplacementBoundary(t *testing.T) {
	request, proposals := expandedGroupedBoundaryFixture(t, 10, 21)
	result, err := buildGroupedProductResult(
		request, strings.Repeat("e", 64), "", nil, nil, proposals, nil, "debug/grouped-2500-formula.json",
	)
	if err != nil {
		t.Fatal(err)
	}
	assertGroupedBoundaryRows(t, result, 210, 10, 21)
	if !request.EffectiveResultOptions().ExpandedLimits {
		t.Fatal("expanded grouped result fixture did not opt in")
	}
}

func expandedGroupedBoundaryFixture(t *testing.T, groups, alternatives int) (contracts.OptimizerRequest, []search.ScoredAssignment) {
	t.Helper()
	count := groups * alternatives
	request, _ := productFixtures(t)
	request = withResultOptionsAndEnergyPolicy(t, request, contracts.ResultOptions{
		SetGroupLimit: groups, BuildsPerGroup: alternatives, FastMode: true, ExpandedLimits: true,
	})
	request = addArtifactVariants(t, request, count, func(variant int, _ contracts.Artifact) string {
		return "expanded_set_" + strconv.Itoa((variant-1)/alternatives)
	})
	proposals := make([]search.ScoredAssignment, 0, count)
	for variant := 1; variant <= count; variant++ {
		group := (variant - 1) / alternatives
		alternative := (variant - 1) % alternatives
		score := float64((groups-group)*100 + alternatives - alternative)
		proposals = append(proposals, search.ScoredAssignment{
			Assignment: oneSwapAssignment(request, group*alternatives+1, variant),
			DPS:        score,
		})
	}
	return request, proposals
}

func groupedBoundaryFixture(t *testing.T) (contracts.OptimizerRequest, []search.ScoredAssignment, []finalists.MeasuredCandidate) {
	t.Helper()
	// Synthetic slot-compatible copies exercise the 64-row input boundary; the
	// digest strings below are shape fixtures, not simulator evidence.
	request, _ := productFixtures(t)
	request = withResultOptionsAndEnergyPolicy(t, request, contracts.ResultOptions{
		SetGroupLimit: 7, BuildsPerGroup: 7, FastMode: true,
	})
	request = addArtifactVariants(t, request, 64, func(variant int, _ contracts.Artifact) string {
		return "bonus_set_" + strconv.Itoa((variant-1)/8)
	})
	proposals := make([]search.ScoredAssignment, 0, 64)
	measured := make([]finalists.MeasuredCandidate, 0, 64)
	for variant := 1; variant <= 64; variant++ {
		group := (variant - 1) / 8
		alternative := (variant - 1) % 8
		score := float64((7-group)*100 + 7 - alternative)
		assignment := oneSwapAssignment(request, group*8+1, variant)
		proposals = append(proposals, search.ScoredAssignment{Assignment: assignment, DPS: score})
		measured = append(measured, finalists.MeasuredCandidate{
			Assignment: assignment, FormulaDPS: score, MeasuredDPS: score + 1000,
			StandardError: 1, FormulaResidualDPS: 1000, Iterations: 500,
			AssignmentSHA256: fmt.Sprintf("%064x", variant), EngineResultSHA256: fmt.Sprintf("%064x", variant+64),
		})
	}
	return request, proposals, measured
}

func oneSwapAssignment(request contracts.OptimizerRequest, base, variant int) domain.Assignment {
	assignment := variantAssignment(request, base)
	assignment[0][1] = variantAssignment(request, variant)[0][1]
	return assignment
}

func assertGroupedBoundaryRows(t *testing.T, result contracts.OptimizerResult, count, groups, alternatives int) {
	t.Helper()
	if len(result.Candidates) != count {
		t.Fatalf("got %d grouped rows, want %d", len(result.Candidates), count)
	}
	seen := make(map[[20]int64]bool, len(result.Candidates))
	for index, candidate := range result.Candidates {
		wantGroup := index/alternatives + 1
		wantAlternative := index%alternatives + 1
		if candidate.SetGroupRank != wantGroup || candidate.AlternativeRank != wantAlternative {
			t.Fatalf("row %d has group/alternative %d/%d, want %d/%d", index, candidate.SetGroupRank, candidate.AlternativeRank, wantGroup, wantAlternative)
		}
		var assignment [20]int64
		for artifactIndex, artifact := range candidate.Artifacts {
			assignment[artifactIndex] = artifact.ArtifactID
		}
		if seen[assignment] {
			t.Fatalf("row %d repeats an artifact assignment", index)
		}
		seen[assignment] = true
		if index > 0 && candidate.SetGroupRank < result.Candidates[index-1].SetGroupRank {
			t.Fatalf("row %d breaks contiguous group order", index)
		}
	}
	if want := groups * alternatives; count != want {
		t.Fatalf("test setup requested %d rows but asserted %d", want, count)
	}
}

func TestCanonicalProductGroupKeyUsesBonusTiersAndOmitsSingles(t *testing.T) {
	request, _ := productFixtures(t)
	request = addArtifactVariants(t, request, 4, func(variant int, artifact contracts.Artifact) string {
		slotIndex := 0
		for index, slot := range []string{"flower", "plume", "sands", "goblet", "circlet"} {
			if artifact.Slot == slot {
				slotIndex = index
				break
			}
		}
		switch variant {
		case 1:
			if slotIndex < 3 {
				return "two_piece_a"
			}
			return "two_piece_b"
		case 2:
			if slotIndex < 2 {
				return "two_piece_a"
			}
			return "two_piece_b"
		case 3:
			return "single_a_" + artifact.Slot
		default:
			return "single_b_" + artifact.Slot
		}
	})
	artifactIndex := make(map[int64]contracts.Artifact, len(request.Artifacts))
	for _, artifact := range request.Artifacts {
		artifactIndex[artifact.ArtifactID] = artifact
	}
	key := func(variant int) string {
		value, err := canonicalProductGroupKey(request, artifactIndex, variantAssignment(request, variant))
		if err != nil {
			t.Fatal(err)
		}
		return value
	}
	if key(1) != key(2) {
		t.Fatal("2/3-piece and 3/2-piece counts should normalize to identical 2p bonuses")
	}
	if key(3) != key(4) {
		t.Fatal("single-piece sets should be omitted from the team group key")
	}
	if !strings.Contains(key(3), `"wearer_key":"actor_a"`) {
		t.Fatal("group key must retain wearer identity when it has no set bonus")
	}
}

func TestGroupedMeasuredLeaderPromotionNeverLabelsTwoItemChangeAsOne(t *testing.T) {
	anchor := domain.Assignment{{1, 2, 3, 4, 5}, {6, 7, 8, 9, 10}, {11, 12, 13, 14, 15}, {16, 17, 18, 19, 20}}
	flower, plume := anchor, anchor
	flower[0][0] = 21
	plume[0][1] = 22
	rows := []groupedProductRow{
		{Assignment: anchor, GroupKey: "one", FormulaDPS: 100, RankingDPS: 102},
		{Assignment: flower, GroupKey: "one", FormulaDPS: 99, RankingDPS: 105},
		{Assignment: plume, GroupKey: "one", FormulaDPS: 98, RankingDPS: 104},
	}
	got := selectGroupedProductRows(rows, contracts.ResultOptions{SetGroupLimit: 1, BuildsPerGroup: 4})
	if len(got) != 2 || got[0].Assignment != flower || got[1].Assignment != anchor {
		t.Fatalf("promotion must keep the measured winner and only its true single swaps: %+v", got)
	}
}

func TestGroupedProposalRejectsInvalidDPSAndDuplicatePhysicalIDs(t *testing.T) {
	request, _ := productFixtures(t)
	assignment := variantAssignment(request, 0)
	if _, err := groupedProposals(request, []search.ScoredAssignment{{Assignment: assignment, DPS: math.NaN()}}); err == nil {
		t.Fatal("NaN DPS should fail")
	}
	assignment[0][0] = assignment[0][1]
	if _, err := groupedProposals(request, []search.ScoredAssignment{{Assignment: assignment, DPS: 100}}); err == nil {
		t.Fatal("duplicate physical IDs should fail")
	}
}

func withResultOptionsAndEnergyPolicy(t *testing.T, request contracts.OptimizerRequest, options contracts.ResultOptions) contracts.OptimizerRequest {
	t.Helper()
	request.ResultOptions = &options
	return setTestEnergyMode(t, request, true)
}

func setTestEnergyMode(t *testing.T, request contracts.OptimizerRequest, ignoreBurstEnergy bool) contracts.OptimizerRequest {
	t.Helper()
	energyMode := "false"
	if ignoreBurstEnergy {
		energyMode = "true"
	}
	request.Context.PreparedConfig.Text = "options iteration=1000 ignore_burst_energy=" + energyMode + ";\n"
	request.Context.PreparedConfig.SHA256 = contracts.TextSHA256(request.Context.PreparedConfig.Text)
	identity, err := contracts.CanonicalSHA256(struct {
		PreparedConfigSHA256 string `json:"prepared_config_sha256"`
		RotationSHA256       string `json:"rotation_sha256"`
		TargetSHA256         string `json:"target_sha256"`
	}{
		PreparedConfigSHA256: request.Context.PreparedConfig.SHA256,
		RotationSHA256:       request.Context.Rotation.SHA256,
		TargetSHA256:         request.Context.Target.SHA256,
	})
	if err != nil {
		t.Fatal(err)
	}
	request.Context.ContextSHA256 = identity
	return request
}

func addArtifactVariants(t *testing.T, request contracts.OptimizerRequest, count int, setUID func(int, contracts.Artifact) string) contracts.OptimizerRequest {
	t.Helper()
	source := append([]contracts.Artifact(nil), request.Artifacts...)
	for variant := 1; variant <= count; variant++ {
		for _, artifact := range source {
			copyArtifact := artifact
			copyArtifact.ArtifactID += int64(variant * 20)
			copyArtifact.SetUID = setUID(variant, artifact)
			request.Artifacts = append(request.Artifacts, copyArtifact)
		}
	}
	return request
}

func variantAssignment(request contracts.OptimizerRequest, variant int) domain.Assignment {
	var assignment domain.Assignment
	for wearerIndex, wearer := range request.Wearers {
		for slotIndex, current := range wearer.CurrentArtifacts {
			assignment[wearerIndex][slotIndex] = current.ArtifactID + int64(variant*20)
		}
	}
	return assignment
}

package contracts

import (
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"testing"
)

func TestResultOptionsDefaultAndValidation(t *testing.T) {
	request, err := DecodeRequest(readFixture(t, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	if got := request.EffectiveResultOptions(); got != (ResultOptions{SetGroupLimit: 3, BuildsPerGroup: 2}) {
		t.Fatalf("nil options default to %+v", got)
	}
	request.ResultOptions = &ResultOptions{SetGroupLimit: 7, BuildsPerGroup: 7, FastMode: true}
	if err := request.Validate(); err != nil {
		t.Fatalf("maximum result options should validate: %v", err)
	}
	if got := request.EffectiveResultOptions().ResultLimit(); got != 41 {
		t.Fatalf("fast result limit is %d, want 41", got)
	}

	request.ResultOptions = &ResultOptions{SetGroupLimit: 50, BuildsPerGroup: 101, FastMode: true, ExpandedLimits: true}
	if err := request.Validate(); err != nil {
		t.Fatalf("expanded technical maximum should validate: %v", err)
	}
	if got := request.EffectiveResultOptions().ResultLimit(); got != 101 {
		t.Fatalf("expanded result limit is %d", got)
	}
	encoded, err := json.Marshal(request.ResultOptions)
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(encoded), `"expanded_limits":true`) {
		t.Fatalf("expanded limit opt-in is missing from JSON: %s", encoded)
	}
	request.ResultOptions = &ResultOptions{SetGroupLimit: 3, BuildsPerGroup: 2}
	encoded, err = json.Marshal(request.ResultOptions)
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(string(encoded), `"expanded_limits"`) {
		t.Fatalf("default false expanded limit should be omitted from JSON: %s", encoded)
	}

	for _, options := range []ResultOptions{
		{SetGroupLimit: 0, BuildsPerGroup: 2},
		{SetGroupLimit: 8, BuildsPerGroup: 2},
		{SetGroupLimit: 3, BuildsPerGroup: 0},
		{SetGroupLimit: 3, BuildsPerGroup: 12},
		{SetGroupLimit: 0, BuildsPerGroup: 2, ExpandedLimits: true},
		{SetGroupLimit: 51, BuildsPerGroup: 2, ExpandedLimits: true},
		{SetGroupLimit: 50, BuildsPerGroup: 102, ExpandedLimits: true},
		{SetGroupLimit: 2, BuildsPerGroup: 0, ExpandedLimits: true},
		{SetGroupLimit: 10, BuildsPerGroup: 42, FastMode: true},
		{SetGroupLimit: 11, BuildsPerGroup: 21, FastMode: true},
	} {
		request.ResultOptions = &options
		if err := request.Validate(); err == nil {
			t.Fatalf("out-of-range result options should fail: %+v", options)
		}
	}
	request.ResultOptions = &ResultOptions{SetGroupLimit: 5, BuildsPerGroup: 11}
	if err := request.Validate(); err != nil {
		t.Fatalf("recommended maximum 5 by 11 should remain valid: %v", err)
	}
}

func TestProductTimeoutZeroMeansUnlimitedAndNegativeOrUncoveredBudgetsFail(t *testing.T) {
	request, err := DecodeRequest(readFixture(t, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	request.Budgets = TimeBudgets{}
	if err := request.Validate(); err != nil {
		t.Fatalf("zero product/development budgets should mean unlimited: %v", err)
	}

	request.Budgets = TimeBudgets{ProductTimeoutMS: 60_000, DevelopmentTimeoutMS: 0}
	if err := request.Validate(); err != nil {
		t.Fatalf("zero development budget should be unlimited: %v", err)
	}

	for _, budgets := range []TimeBudgets{
		{ProductTimeoutMS: -1},
		{DevelopmentTimeoutMS: -1},
		{ProductTimeoutMS: 60_000, DevelopmentTimeoutMS: 59_999},
		{ProductTimeoutMS: 0, DevelopmentTimeoutMS: 1},
	} {
		request.Budgets = budgets
		if err := request.Validate(); err == nil {
			t.Fatalf("invalid budgets should fail: %+v", budgets)
		}
	}
}

func TestTheoryStillRequiresPositiveBudgets(t *testing.T) {
	request := neutralTheoryRequest(t)
	payload, err := CanonicalJSON(request)
	if err != nil {
		t.Fatal(err)
	}
	_, request, err = DecodeTheoryRequest(payload)
	if err != nil {
		t.Fatal(err)
	}
	if err := request.ValidateTheory(); err != nil {
		t.Fatalf("fixture Theory budgets should remain valid: %v", err)
	}
	request.Budgets = TimeBudgets{}
	if err := request.ValidateTheory(); err == nil {
		t.Fatal("zero budgets should remain invalid for Theory")
	}
}

func TestFinalizingProgressStageIsAllowed(t *testing.T) {
	progress := ProgressRecord{
		SchemaVersion: SchemaVersion, SchemaKind: ProgressSchemaKind,
		RequestSHA256: strings.Repeat("a", 64), Stage: "finalizing",
	}
	if err := progress.Validate(); err != nil {
		t.Fatalf("finalizing progress should validate: %v", err)
	}
}

func TestResultCandidatesBeyondLegacyCapRemainValid(t *testing.T) {
	result, err := DecodeResult(readFixture(t, "result_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	result.RankingBasis = "formula"
	result.FormulaResidual = ""
	result.Measured = nil
	result.Warnings = append(result.Warnings, "formula_only_unverified")
	sort.Strings(result.Warnings)
	result.Candidates = make([]RankedCandidateResult, 0, MaxResultRows)
	for index := 0; index < MaxResultRows; index++ {
		group := index / MaxResultBuildsPerGroup
		alternative := index % MaxResultBuildsPerGroup
		artifacts := append([]ArtifactAssignment(nil), result.Winner...)
		if index > 0 {
			for artifactIndex := range artifacts {
				artifacts[artifactIndex].ArtifactID = int64(1_000_000_000 + index*20 + artifactIndex)
			}
		}
		score := 10000 - group*100 - alternative
		candidate := RankedCandidateResult{
			Rank:            index + 1,
			Artifacts:       artifacts,
			FormulaDPS:      fmt.Sprintf("%d", score),
			SetGroupKey:     fmt.Sprintf("group-%02d", group+1),
			SetGroupRank:    group + 1,
			AlternativeRank: alternative + 1,
		}
		result.Candidates = append(result.Candidates, candidate)
	}
	result.FormulaDPS = result.Candidates[0].FormulaDPS
	if err := result.Validate(); err != nil {
		t.Fatalf("5050 grouped results should validate: %v", err)
	}

	result.Candidates = append(result.Candidates, result.Candidates[0])
	if err := result.Validate(); err == nil {
		t.Fatal("removing the row cap must not allow invalid duplicate candidates")
	}
}

func TestFormulaOnlyResultContract(t *testing.T) {
	result, err := DecodeResult(readFixture(t, "result_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	result.RankingBasis = "formula"
	result.FormulaDPS = "143738.29"
	result.FormulaResidual = ""
	result.Measured = nil
	result.Candidates = []RankedCandidateResult{{
		Rank: 1, Artifacts: append([]ArtifactAssignment(nil), result.Winner...), FormulaDPS: result.FormulaDPS,
	}}
	result.Warnings = append(result.Warnings, "formula_only_unverified")
	sort.Strings(result.Warnings)
	if err := result.Validate(); err != nil {
		t.Fatalf("valid formula-only result should pass: %v", err)
	}

	invalid := result
	invalid.Warnings = make([]string, 0, len(result.Warnings)-1)
	for _, warning := range result.Warnings {
		if warning != "formula_only_unverified" {
			invalid.Warnings = append(invalid.Warnings, warning)
		}
	}
	if err := invalid.Validate(); err == nil || !strings.Contains(err.Error(), "formula_only_unverified") {
		t.Fatalf("formula-only warning is required, got %v", err)
	}
	invalid = result
	invalid.FormulaDPS = "-1"
	if err := invalid.Validate(); err == nil {
		t.Fatal("negative formula DPS should fail")
	}
	invalid = result
	invalid.Candidates = append([]RankedCandidateResult(nil), result.Candidates...)
	invalid.Candidates[0].FormulaResidual = "0"
	if err := invalid.Validate(); err == nil {
		t.Fatal("formula-only candidate residual should fail")
	}
	invalid = result
	invalid.Candidates = append([]RankedCandidateResult(nil), result.Candidates...)
	invalid.Candidates[0].Measured = &MeasuredResult{}
	if err := invalid.Validate(); err == nil {
		t.Fatal("formula-only candidate measurement should fail")
	}
}

func TestGroupedCandidateOrderingContract(t *testing.T) {
	result, err := DecodeResult(readFixture(t, "result_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	result.RankingBasis = "formula"
	result.FormulaDPS = "100"
	result.FormulaResidual = ""
	result.Measured = nil
	first := append([]ArtifactAssignment(nil), result.Winner...)
	second := append([]ArtifactAssignment(nil), result.Winner...)
	second[0].ArtifactID, second[1].ArtifactID = second[1].ArtifactID, second[0].ArtifactID
	third := append([]ArtifactAssignment(nil), result.Winner...)
	third[0].ArtifactID, third[1].ArtifactID = third[1].ArtifactID, third[0].ArtifactID
	third[5].ArtifactID, third[6].ArtifactID = third[6].ArtifactID, third[5].ArtifactID
	result.Candidates = []RankedCandidateResult{
		{Rank: 1, Artifacts: first, FormulaDPS: "100", SetGroupKey: "group-a", SetGroupRank: 1, AlternativeRank: 1},
		{Rank: 2, Artifacts: second, FormulaDPS: "90", SetGroupKey: "group-a", SetGroupRank: 1, AlternativeRank: 2},
		{Rank: 3, Artifacts: third, FormulaDPS: "80", SetGroupKey: "group-b", SetGroupRank: 2, AlternativeRank: 1},
	}
	result.Warnings = append(result.Warnings, "formula_only_unverified")
	sort.Strings(result.Warnings)
	if err := result.Validate(); err != nil {
		t.Fatalf("valid grouped result should pass: %v", err)
	}

	invalid := result
	invalid.Candidates = append([]RankedCandidateResult(nil), result.Candidates...)
	invalid.Candidates[1].AlternativeRank = 3
	if err := invalid.Validate(); err == nil {
		t.Fatal("non-contiguous alternative ranks should fail")
	}
	invalid = result
	invalid.Candidates = append([]RankedCandidateResult(nil), result.Candidates...)
	invalid.Candidates[2].FormulaDPS = "101"
	if err := invalid.Validate(); err == nil {
		t.Fatal("group order that does not follow score should fail")
	}
	invalid = result
	invalid.Candidates = append([]RankedCandidateResult(nil), result.Candidates...)
	invalid.Candidates[1].SetGroupKey = "group-b"
	invalid.Candidates[1].SetGroupRank = 2
	invalid.Candidates[1].AlternativeRank = 1
	invalid.Candidates[2].SetGroupKey = "group-a"
	invalid.Candidates[2].SetGroupRank = 1
	invalid.Candidates[2].AlternativeRank = 1
	if err := invalid.Validate(); err == nil {
		t.Fatal("non-contiguous repeated group should fail")
	}
}

package finalists

import (
	"strings"
	"testing"
)

func TestUnresolvedLeaderRowsUsesCombinedUncertainty(t *testing.T) {
	rows := []MeasuredCandidate{
		{AssignmentSHA256: strings.Repeat("a", 64), MeasuredDPS: 1000, StandardError: 10},
		{AssignmentSHA256: strings.Repeat("b", 64), MeasuredDPS: 970, StandardError: 10},
		{AssignmentSHA256: strings.Repeat("c", 64), MeasuredDPS: 900, StandardError: 10},
	}
	unresolved := unresolvedLeaderRows(rows, 3)
	if len(unresolved) != 2 || unresolved[0].AssignmentSHA256 != strings.Repeat("a", 64) || unresolved[1].AssignmentSHA256 != strings.Repeat("b", 64) {
		t.Fatalf("unexpected unresolved rows: %+v", unresolved)
	}
}

func TestMergeExtendedRowsReplacesOnlyRerunEvidence(t *testing.T) {
	base := VerificationResult{Iterations: 500, TotalElapsedMS: 10, Candidates: []MeasuredCandidate{
		{Rank: 1, AssignmentSHA256: strings.Repeat("a", 64), MeasuredDPS: 100, Iterations: 500},
		{Rank: 2, AssignmentSHA256: strings.Repeat("b", 64), MeasuredDPS: 99, Iterations: 500},
		{Rank: 3, AssignmentSHA256: strings.Repeat("c", 64), MeasuredDPS: 80, Iterations: 500},
	}}
	extension := VerificationResult{Iterations: 1000, TotalElapsedMS: 20, Candidates: []MeasuredCandidate{
		{Rank: 1, AssignmentSHA256: strings.Repeat("a", 64), MeasuredDPS: 98, Iterations: 1000},
		{Rank: 2, AssignmentSHA256: strings.Repeat("b", 64), MeasuredDPS: 101, Iterations: 1000},
	}}
	merged, err := mergeExtendedRows(base, extension)
	if err != nil {
		t.Fatal(err)
	}
	if merged.Winner.AssignmentSHA256 != strings.Repeat("b", 64) || merged.TotalElapsedMS != 30 {
		t.Fatalf("unexpected merged result: %+v", merged)
	}
	if merged.Candidates[0].Iterations != 1000 || merged.Candidates[1].Iterations != 1000 || merged.Candidates[2].Iterations != 500 {
		t.Fatalf("unexpected mixed evidence rows: %+v", merged.Candidates)
	}
}

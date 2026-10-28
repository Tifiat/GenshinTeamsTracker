package finalists

import (
	"errors"
	"testing"
)

func TestFiniteEnergyRejectsOnlyFailingFinalist(t *testing.T) {
	rows := []MeasuredCandidate{
		{Rank: 1, AssignmentSHA256: "first", MeasuredDPS: 200},
		{Rank: 2, AssignmentSHA256: "second", MeasuredDPS: 190},
	}
	result, err := finalizeVerificationRows(
		rows,
		[]bool{false, true},
		[]float64{12.5, 0},
		[]string{"first", "second"},
		500, 4, 2, 10,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Candidates) != 1 || result.Winner.AssignmentSHA256 != "second" {
		t.Fatalf("valid fallback finalist was not retained: %+v", result)
	}
	if len(result.EnergyRejectedSHA256) != 1 || result.EnergyRejectedSHA256[0] != "first" {
		t.Fatalf("energy rejection was not recorded: %+v", result.EnergyRejectedSHA256)
	}
}

func TestFiniteEnergyFailsOnlyWhenEveryFinalistIsRejected(t *testing.T) {
	_, err := finalizeVerificationRows(
		[]MeasuredCandidate{{Rank: 1}, {Rank: 2}},
		[]bool{false, false},
		[]float64{2, 7},
		[]string{"first", "second"},
		500, 4, 2, 10,
	)
	var noEnergy *NoEnergyFeasibleFinalistError
	if !errors.As(err, &noEnergy) || noEnergy.MaximumShortage != 7 || len(noEnergy.AssignmentSHA256) != 2 {
		t.Fatalf("unexpected all-rejected error: %#v", err)
	}
}

func TestAdaptiveMergeRemovesCandidateRejectedAtHigherFidelity(t *testing.T) {
	base := VerificationResult{Candidates: []MeasuredCandidate{
		{Rank: 1, AssignmentSHA256: "first", MeasuredDPS: 200},
		{Rank: 2, AssignmentSHA256: "second", MeasuredDPS: 190},
	}}
	extension := VerificationResult{
		Candidates:           []MeasuredCandidate{{Rank: 2, AssignmentSHA256: "second", MeasuredDPS: 195}},
		EnergyRejectedSHA256: []string{"first"},
	}
	result, err := mergeExtendedRows(base, extension)
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Candidates) != 1 || result.Winner.AssignmentSHA256 != "second" {
		t.Fatalf("higher-fidelity rejection leaked into result: %+v", result)
	}
}

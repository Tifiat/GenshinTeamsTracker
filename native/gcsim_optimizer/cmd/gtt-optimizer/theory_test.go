package main

import (
	"context"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

func TestTheoryCaptureBudgetIncludesNeutralBaseContext(t *testing.T) {
	if got, want := theoryCaptureBudget(40, 2), 82; got != want {
		t.Fatalf("theory capture budget = %d; want %d", got, want)
	}
}

func TestProductCandidateLimitIsFive(t *testing.T) {
	if maxProductCandidates != 5 {
		t.Fatalf("product candidate limit = %d; want 5", maxProductCandidates)
	}
}

func TestTheoryContextBudgetKeepsWideDiscoveryAndBoundedMarginals(t *testing.T) {
	if theoryCandidateContexts != 16 || theoryMarginalCandidates != 6 {
		t.Fatalf("theory context split = %d+%d candidates; want 16+6", theoryCandidateContexts, theoryMarginalCandidates)
	}
	if theoryTotalContextLimit != 40 || theoryMarginalContexts != 24 {
		t.Fatalf("theory context budget = %d (%d marginal); want 40 (24 marginal)", theoryTotalContextLimit, theoryMarginalContexts)
	}
}

func TestMinimizeTheoryCandidateRemovesPracticallyIndistinguishablePackages(t *testing.T) {
	wearers := []contracts.Wearer{
		{WearerKey: "a"}, {WearerKey: "b"}, {WearerKey: "c"}, {WearerKey: "d"},
	}
	var packages [4]domain.Package
	for i := range packages {
		packages[i] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: string(rune('a' + i)), Count: 4}}}
	}
	contribution := [4]float64{10, 0, 0, 5}
	evaluate := func(candidate [4]domain.Package) (theoryCandidate, error) {
		dps := 85.0
		for i := range candidate {
			if len(candidate[i].Sets) > 0 {
				dps += contribution[i]
			}
		}
		return theoryCandidate{
			FormulaDPS: dps,
			Packages:   theoryPackageRows(wearers, candidate),
		}, nil
	}
	best, _ := evaluate(packages)
	best.Source = "shortlist"
	got, err := minimizeTheoryCandidate(best, packages, wearers, evaluate)
	if err != nil {
		t.Fatal(err)
	}
	if got.FormulaDPS != 100 || len(got.UndistinguishedSlots) != 2 {
		t.Fatalf("minimized candidate = %#v", got)
	}
	if len(got.Packages[0].Sets) != 1 || len(got.Packages[1].Sets) != 0 || len(got.Packages[2].Sets) != 0 || len(got.Packages[3].Sets) != 1 {
		t.Fatalf("unexpected minimized packages: %#v", got.Packages)
	}
}

func TestMinimizeTheoryCandidateDropsFormulaJitterButKeepsMaterialContribution(t *testing.T) {
	wearers := []contracts.Wearer{
		{WearerKey: "a"}, {WearerKey: "b"}, {WearerKey: "c"}, {WearerKey: "d"},
	}
	var packages [4]domain.Package
	for i := range packages {
		packages[i] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: string(rune('a' + i)), Count: 4}}}
	}
	contribution := [4]float64{0.01, 0.04, 0.06, 1.0}
	evaluate := func(candidate [4]domain.Package) (theoryCandidate, error) {
		dps := 100.0
		for i := range candidate {
			if len(candidate[i].Sets) > 0 {
				dps += contribution[i]
			}
		}
		return theoryCandidate{FormulaDPS: dps, Packages: theoryPackageRows(wearers, candidate)}, nil
	}
	best, _ := evaluate(packages)
	got, err := minimizeTheoryCandidate(best, packages, wearers, evaluate)
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Packages[0].Sets) != 0 || len(got.Packages[1].Sets) != 0 {
		t.Fatalf("formula jitter packages survived: %#v", got.Packages)
	}
	if len(got.Packages[2].Sets) != 1 || len(got.Packages[3].Sets) != 1 {
		t.Fatalf("material packages were removed: %#v", got.Packages)
	}
}

func TestMinimizeTheoryCandidateKeepsOneOfRedundantSharedPackages(t *testing.T) {
	wearers := []contracts.Wearer{
		{WearerKey: "a"}, {WearerKey: "b"}, {WearerKey: "c"}, {WearerKey: "d"},
	}
	var packages [4]domain.Package
	for i := range packages {
		packages[i] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: string(rune('a' + i)), Count: 4}}}
	}
	evaluate := func(candidate [4]domain.Package) (theoryCandidate, error) {
		dps := 90.0
		if len(candidate[0].Sets) > 0 || len(candidate[1].Sets) > 0 {
			dps += 10
		}
		return theoryCandidate{FormulaDPS: dps, Packages: theoryPackageRows(wearers, candidate)}, nil
	}
	best, _ := evaluate(packages)
	got, err := minimizeTheoryCandidate(best, packages, wearers, evaluate)
	if err != nil {
		t.Fatal(err)
	}
	if len(got.Packages[0].Sets) != 0 || len(got.Packages[1].Sets) != 1 {
		t.Fatalf("redundant shared package was not minimized deterministically: %#v", got.Packages)
	}
}

func TestMinimizeTheoryCandidateReturnsProvenPrefixOnDeadline(t *testing.T) {
	wearers := []contracts.Wearer{
		{WearerKey: "a"}, {WearerKey: "b"}, {WearerKey: "c"}, {WearerKey: "d"},
	}
	var packages [4]domain.Package
	for i := range packages {
		packages[i] = domain.Package{Sets: []contracts.SetRequirement{{SetUID: string(rune('a' + i)), Count: 4}}}
	}
	calls := 0
	evaluate := func(candidate [4]domain.Package) (theoryCandidate, error) {
		calls++
		if calls == 2 {
			return theoryCandidate{}, context.DeadlineExceeded
		}
		return theoryCandidate{
			FormulaDPS: 100,
			Packages:   theoryPackageRows(wearers, candidate),
		}, nil
	}
	best := theoryCandidate{
		FormulaDPS: 100,
		Packages:   theoryPackageRows(wearers, packages),
	}
	got, err := minimizeTheoryCandidate(best, packages, wearers, evaluate)
	if err != context.DeadlineExceeded {
		t.Fatalf("deadline error = %v", err)
	}
	if len(got.UndistinguishedSlots) != 1 || got.UndistinguishedSlots[0] != "a" {
		t.Fatalf("proven marginal prefix lost: %#v", got)
	}
	if len(got.Packages[0].Sets) != 0 || len(got.Packages[1].Sets) != 1 {
		t.Fatalf("partial candidate is not the proven prefix: %#v", got.Packages)
	}
}

package domain

import (
	"math/rand"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

type localValidationControl struct {
	name          string
	ids           [slotCount]int64
	expectedValid *bool
}

func TestPreparedLocalAssignmentValidatorMatchesFullValidation(t *testing.T) {
	request := requestFixture(t)
	originalArtifactCount := len(request.Artifacts)
	spareIDs := make(map[int64]int64, originalArtifactCount)
	var nextArtifactID int64 = 1
	for _, artifact := range request.Artifacts {
		if artifact.ArtifactID >= nextArtifactID {
			nextArtifactID = artifact.ArtifactID + 1
		}
	}
	for i := 0; i < originalArtifactCount; i++ {
		artifact := request.Artifacts[i]
		artifact.ArtifactID = nextArtifactID
		spareIDs[request.Artifacts[i].ArtifactID] = nextArtifactID
		request.Artifacts = append(request.Artifacts, artifact)
		nextArtifactID++
	}
	for slot := 0; slot < slotCount; slot++ {
		artifact := request.Artifacts[slot]
		artifact.ArtifactID = int64(1000 + slot)
		artifact.SetUID = "local_singleton_" + slots[slot]
		request.Artifacts = append(request.Artifacts, artifact)
	}
	index, err := Build(request, nil)
	if err != nil {
		t.Fatal(err)
	}
	freeID := func(originalID int64) int64 {
		t.Helper()
		spareID, ok := spareIDs[originalID]
		if !ok {
			t.Fatalf("fixture artifact %d has no free spare", originalID)
		}
		return spareID
	}

	// Exercise the ordinary index with every wearer as the one being replaced.
	// Its per-slot pools include both free items and same-slot items reserved by
	// the other three wearers.
	for actor := 0; actor < wearerCount; actor++ {
		t.Run(index.Wearers[actor].WearerKey, func(t *testing.T) {
			assertLocalValidationParity(t, index, index.Incumbent, actor, 1000, nil)
		})
	}

	packageCases := []struct {
		name     string
		sets     []contracts.SetRequirement
		legal    [slotCount]int64
		controls []localValidationControl
	}{
		{
			name:  "no bonus",
			legal: [slotCount]int64{1000, 1001, 1002, 1003, 1004},
			controls: []localValidationControl{
				localExpectedControl("unrepresented 2p bonus", [slotCount]int64{freeID(1), freeID(2), 1002, 1003, 1004}, false),
			},
		},
		{
			name:  "2p",
			sets:  []contracts.SetRequirement{{SetUID: "set_a", Count: 2}},
			legal: [slotCount]int64{freeID(1), freeID(2), freeID(8), freeID(14), freeID(20)},
			controls: []localValidationControl{
				localExpectedControl("below tier", [slotCount]int64{freeID(1), 1001, 1002, 1003, 1004}, false),
				localExpectedControl("unrepresented bonus", [slotCount]int64{freeID(1), freeID(2), freeID(8), freeID(9), freeID(15)}, false),
			},
		},
		{
			name:  "4p",
			sets:  []contracts.SetRequirement{{SetUID: "set_a", Count: 4}},
			legal: [slotCount]int64{freeID(1), freeID(2), freeID(3), freeID(4), freeID(10)},
			controls: []localValidationControl{
				localExpectedControl("below tier and unrepresented 2p tier", [slotCount]int64{freeID(1), freeID(2), freeID(3), 1003, 1004}, false),
			},
		},
		{
			name:  "2+2",
			sets:  []contracts.SetRequirement{{SetUID: "set_a", Count: 2}, {SetUID: "set_b", Count: 2}},
			legal: [slotCount]int64{freeID(1), freeID(2), freeID(8), freeID(9), freeID(15)},
			controls: []localValidationControl{
				localExpectedControl("below tier", [slotCount]int64{freeID(1), 1001, freeID(8), freeID(9), freeID(15)}, false),
				localExpectedControl("unrepresented 4p tier", [slotCount]int64{freeID(1), freeID(2), freeID(3), freeID(4), freeID(10)}, false),
			},
		},
	}

	for _, packageCase := range packageCases {
		t.Run("exact_"+packageCase.name, func(t *testing.T) {
			anchor := index.Incumbent
			anchor[0] = packageCase.legal
			view := localPackageView(t, index, anchor, packageCase.sets)
			if !view.exactPackages {
				t.Fatal("ForPackages view did not enable exact package validation")
			}
			if err := view.ValidateAssignment(anchor); err != nil {
				t.Fatalf("exact package anchor with the fixture's other wearers is invalid: %v", err)
			}
			assertLocalValidationParity(t, view, anchor, 0, 1000, packageCase.controls)
		})
	}
}

func localPackageView(t *testing.T, index *Index, anchor Assignment, actorSets []contracts.SetRequirement) *Index {
	t.Helper()
	var packages [wearerCount]Package
	for wearerIndex, wearer := range index.Wearers {
		packages[wearerIndex] = Package{Sets: append([]contracts.SetRequirement(nil), wearer.SelectedSets...)}
	}
	packages[0] = Package{Sets: append([]contracts.SetRequirement(nil), actorSets...)}
	view, err := index.ForPackages(packages, anchor, nil)
	if err != nil {
		t.Fatal(err)
	}
	return view
}

func assertLocalValidationParity(t *testing.T, index *Index, anchor Assignment, actor, randomTrials int, controls []localValidationControl) {
	t.Helper()
	validator, err := index.PrepareLocalAssignmentValidator(anchor, actor)
	if err != nil {
		t.Fatal(err)
	}
	assertLocalControl(t, index, validator, anchor, actor, localExpectedControl("anchor", anchor[actor], true))

	for slot := 0; slot < slotCount; slot++ {
		reservedID := anchor[(actor+1)%wearerCount][slot]
		if !containsID(index.CandidateIDsBySlot[slot], reservedID) {
			t.Fatalf("reserved artifact %d missing from slot %s pool", reservedID, slots[slot])
		}
		collision := anchor[actor]
		collision[slot] = reservedID
		assertLocalControl(t, index, validator, anchor, actor, localExpectedControl("occupied slot "+slots[slot], collision, false))
	}

	unknown := anchor[actor]
	unknown[0] = 9_000_000_001
	assertLocalControl(t, index, validator, anchor, actor, localExpectedControl("unknown artifact", unknown, false))

	wrongSlot := anchor[actor]
	wrongSlot[0] = anchor[actor][slotCount-1]
	assertLocalControl(t, index, validator, anchor, actor, localExpectedControl("wrong slot", wrongSlot, false))

	duplicate := anchor[actor]
	duplicate[1] = duplicate[0]
	if duplicate[0] != duplicate[1] {
		t.Fatal("duplicate control does not repeat an artifact ID")
	}
	assertLocalControl(t, index, validator, anchor, actor, localExpectedControl("duplicate artifact", duplicate, false))

	for _, control := range controls {
		assertLocalControl(t, index, validator, anchor, actor, control)
	}

	randomizer := rand.New(rand.NewSource(20260927 + int64(actor*10000+randomTrials)))
	for trialIndex := 0; trialIndex < randomTrials; trialIndex++ {
		trialIDs := [slotCount]int64{}
		for slot := range trialIDs {
			if randomizer.Intn(64) == 0 {
				trialIDs[slot] = int64(1_000_000 + trialIndex*slotCount + slot)
				continue
			}
			pool := index.CandidateIDsBySlot[slot]
			trialIDs[slot] = pool[randomizer.Intn(len(pool))]
		}
		assertLocalControl(t, index, validator, anchor, actor, localValidationControl{name: "random", ids: trialIDs})
	}
}

func assertLocalControl(t *testing.T, index *Index, validator *LocalAssignmentValidator, anchor Assignment, actor int, control localValidationControl) {
	t.Helper()
	trial := anchor
	trial[actor] = control.ids
	fullValid := index.ValidateAssignment(trial) == nil
	localValid := validator.Validate(control.ids) == nil
	if fullValid != localValid {
		t.Fatalf("%s validity mismatch: full=%t local=%t IDs=%v", control.name, fullValid, localValid, control.ids)
	}
	if control.expectedValid != nil && *control.expectedValid != fullValid {
		t.Fatalf("%s expected valid=%t, got full=%t IDs=%v", control.name, *control.expectedValid, fullValid, control.ids)
	}
}

func localExpectedControl(name string, ids [slotCount]int64, valid bool) localValidationControl {
	return localValidationControl{name: name, ids: ids, expectedValid: &valid}
}

func containsID(ids []int64, wanted int64) bool {
	for _, id := range ids {
		if id == wanted {
			return true
		}
	}
	return false
}

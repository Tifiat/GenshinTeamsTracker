package domain

import (
	"reflect"
	"sort"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func cloneCanonicalAnchorWearers(wearers [4]IndexedWearer) [4]IndexedWearer {
	cloned := wearers
	for actor := range cloned {
		cloned[actor].SelectedSets = append([]contracts.SetRequirement(nil), wearers[actor].SelectedSets...)
		cloned[actor].incumbentStats = make(map[string]float64, len(wearers[actor].incumbentStats))
		for key, value := range wearers[actor].incumbentStats {
			cloned[actor].incumbentStats[key] = value
		}
	}
	return cloned
}

func TestCanonicalAllSetsAnchorIgnoresEquippedAnchorAndRebasesStats(t *testing.T) {
	requestA := requestFixture(t)
	requestB := requestFixture(t)
	if !reflect.DeepEqual(requestA.Artifacts, requestB.Artifacts) {
		t.Fatal("fixture inventories differ before changing equipped anchors")
	}

	setByID := make(map[int64]string, len(requestB.Artifacts))
	for _, artifact := range requestB.Artifacts {
		setByID[artifact.ArtifactID] = artifact.SetUID
	}
	for actor := range requestB.Wearers {
		source := (actor + 1) % len(requestA.Wearers)
		assignments := append(
			[]contracts.ArtifactAssignment(nil),
			requestA.Wearers[source].CurrentArtifacts...,
		)
		for slot := range assignments {
			assignments[slot].WearerKey = requestB.Wearers[actor].WearerKey
		}
		requestB.Wearers[actor].CurrentArtifacts = assignments
		requestB.Wearers[actor].SelectedSetUID = setByID[assignments[0].ArtifactID]
	}
	if requestA.Wearers[0].CurrentArtifacts[0].ArtifactID == requestB.Wearers[0].CurrentArtifacts[0].ArtifactID ||
		requestA.Wearers[0].SelectedSetUID == requestB.Wearers[0].SelectedSetUID {
		t.Fatal("the two fixture requests do not have different equipped anchors")
	}
	if !reflect.DeepEqual(requestA.Artifacts, requestB.Artifacts) {
		t.Fatal("changing equipped anchors changed the shared inventory")
	}

	coordinates := []string{"actor_a.atk_percent", "actor_a.crit_rate", "actor_b.hp_percent"}
	indexA, err := Build(requestA, coordinates)
	if err != nil {
		t.Fatal(err)
	}
	indexB, err := Build(requestB, coordinates)
	if err != nil {
		t.Fatal(err)
	}
	originalAssignmentA, originalAssignmentB := indexA.Incumbent, indexB.Incumbent
	originalWearersA := cloneCanonicalAnchorWearers(indexA.Wearers)
	originalWearersB := cloneCanonicalAnchorWearers(indexB.Wearers)

	canonicalA, packagesA, err := indexA.CanonicalAllSetsAnchor()
	if err != nil {
		t.Fatal(err)
	}
	canonicalB, packagesB, err := indexB.CanonicalAllSetsAnchor()
	if err != nil {
		t.Fatal(err)
	}
	if canonicalA.Incumbent != canonicalB.Incumbent {
		t.Fatalf("canonical IDs depend on equipped assignment:\n%v\n%v", canonicalA.Incumbent, canonicalB.Incumbent)
	}
	if !reflect.DeepEqual(packagesA, packagesB) {
		t.Fatalf("canonical set packages depend on equipped set selection:\n%v\n%v", packagesA, packagesB)
	}

	for slot, ids := range indexA.CandidateIDsBySlot {
		sortedIDs := append([]int64(nil), ids...)
		sort.Slice(sortedIDs, func(i, j int) bool { return sortedIDs[i] < sortedIDs[j] })
		for actor := range canonicalA.Incumbent {
			if got, want := canonicalA.Incumbent[actor][slot], sortedIDs[actor]; got != want {
				t.Fatalf("canonical owner %d slot %d ID=%d, want sorted-slot ID %d", actor, slot, got, want)
			}
		}
	}

	statsA, err := canonicalA.AssignmentStats(canonicalA.Incumbent)
	if err != nil {
		t.Fatal(err)
	}
	statsB, err := canonicalB.AssignmentStats(canonicalB.Incumbent)
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(statsA, statsB) {
		t.Fatalf("canonical stat totals depend on equipped anchor:\n%v\n%v", statsA, statsB)
	}
	for _, canonical := range []*Index{canonicalA, canonicalB} {
		deltas, err := canonical.DenseDeltas(canonical.Incumbent)
		if err != nil {
			t.Fatal(err)
		}
		for i, delta := range deltas {
			if delta != 0 {
				t.Fatalf("canonical raw-stat reference was not rebased at %s: %v", coordinates[i], delta)
			}
		}
	}
	if indexB.Wearers[0].incumbentStats["atk_percent"] == canonicalB.Wearers[0].incumbentStats["atk_percent"] {
		t.Fatal("fixture did not distinguish original and canonical actor stat references")
	}
	if indexA.Incumbent != originalAssignmentA || indexB.Incumbent != originalAssignmentB ||
		!reflect.DeepEqual(indexA.Wearers, originalWearersA) || !reflect.DeepEqual(indexB.Wearers, originalWearersB) {
		t.Fatal("canonical anchor mutated the source inventory indexes")
	}
}

func TestCanonicalAllSetsAnchorRejectsInsufficientSlotInventory(t *testing.T) {
	index, err := Build(requestFixture(t), nil)
	if err != nil {
		t.Fatal(err)
	}
	index.CandidateIDsBySlot[0] = index.CandidateIDsBySlot[0][:3]
	if _, _, err := index.CanonicalAllSetsAnchor(); err == nil || !strings.Contains(err.Error(), "slot flower needs four distinct artifacts") {
		t.Fatalf("insufficient slot error = %v", err)
	}
}

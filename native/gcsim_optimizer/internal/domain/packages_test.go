package domain

import (
	"math"
	"strconv"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestFeasiblePairMasksMatchSmallExhaustiveSlots(t *testing.T) {
	// All two-set slot masks, with a spare off-set item in each slot. This
	// enumerates a tiny synthetic legality domain, not account build search.
	for a := 0; a < 32; a++ {
		for b := 0; b < 32; b++ {
			index := &Index{}
			for slot := 0; slot < 5; slot++ {
				index.Artifacts = append(index.Artifacts, IndexedArtifact{ArtifactID: int64(slot*3 + 1), SlotIndex: slot, SetUID: "off"})
				if a&(1<<slot) != 0 {
					index.Artifacts = append(index.Artifacts, IndexedArtifact{ArtifactID: int64(slot*3 + 2), SlotIndex: slot, SetUID: "a"})
				}
				if b&(1<<slot) != 0 {
					index.Artifacts = append(index.Artifacts, IndexedArtifact{ArtifactID: int64(slot*3 + 3), SlotIndex: slot, SetUID: "b"})
				}
			}
			packages, err := index.FeasiblePackages([]SetCapability{{"a", true, true}, {"b", true, true}}, nil)
			if err != nil {
				t.Fatal(err)
			}
			got := false
			for _, p := range packages {
				if len(p.Sets) == 2 {
					got = true
				}
			}
			want := false
			var visit func(int, int, int)
			visit = func(slot, ca, cb int) {
				if slot == 5 {
					if ca >= 2 && cb >= 2 {
						want = true
					}
					return
				}
				visit(slot+1, ca, cb)
				if a&(1<<slot) != 0 {
					visit(slot+1, ca+1, cb)
				}
				if b&(1<<slot) != 0 {
					visit(slot+1, ca, cb+1)
				}
			}
			visit(0, 0, 0)
			if got != want {
				t.Fatalf("masks %d/%d: %v != %v", a, b, got, want)
			}
		}
	}
}

func TestPackageViewKeepsOriginalArtifactReference(t *testing.T) {
	req := requestFixture(t)
	maxID := int64(0)
	for _, a := range req.Artifacts {
		if a.ArtifactID > maxID {
			maxID = a.ArtifactID
		}
	}
	var newIDs [2]int64
	for i := 0; i < 2; i++ {
		id := req.Wearers[0].CurrentArtifacts[i].ArtifactID
		for _, a := range req.Artifacts {
			if a.ArtifactID == id {
				a.ArtifactID = maxID + int64(i) + 1
				a.SetUID = "new_set"
				if i == 0 {
					v, _ := strconv.ParseFloat(a.MainStat.Value, 64)
					a.MainStat.Value = strconv.FormatFloat(v+20, 'f', -1, 64)
				}
				newIDs[i] = a.ArtifactID
				req.Artifacts = append(req.Artifacts, a)
				break
			}
		}
	}
	index, err := Build(req, []string{"actor_a.hp"})
	if err != nil {
		t.Fatal(err)
	}
	var packages [4]Package
	for i, w := range index.Wearers {
		packages[i] = Package{w.SelectedSets}
	}
	packages[0] = Package{[]contracts.SetRequirement{{SetUID: "new_set", Count: 2}, {SetUID: req.Wearers[0].SelectedSetUID, Count: 2}}}
	// Fixture names are canonicalized without changing actual physical IDs.
	if packages[0].Sets[0].SetUID > packages[0].Sets[1].SetUID {
		packages[0].Sets[0], packages[0].Sets[1] = packages[0].Sets[1], packages[0].Sets[0]
	}
	seed := index.Incumbent
	seed[0][0], seed[0][1] = newIDs[0], newIDs[1]
	view, err := index.ForPackages(packages, seed, []string{"actor_a.hp"})
	if err != nil {
		t.Fatal(err)
	}
	delta, err := view.DenseDeltas(seed)
	if err != nil || math.Abs(delta[0]-20) > 1e-9 {
		t.Fatalf("new seed incorrectly became formula reference: %v %v", delta, err)
	}
	if index.Incumbent == view.Incumbent || len(index.Wearers[0].SelectedSets) != 1 {
		t.Fatal("original inventory view mutated")
	}
	excluded := map[int64]bool{newIDs[0]: true}
	feasible, err := index.FeasiblePackages([]SetCapability{{"new_set", true, false}}, excluded)
	if err != nil || len(feasible) != 0 {
		t.Fatal("occupied item incorrectly available")
	}
	_, err = index.PackageSeed(index.Incumbent, 0, packages[0], nil)
	if err != nil {
		t.Fatal(err)
	}
	if _, err = index.PackageSeed(index.Incumbent, 0, packages[0], map[int64]float64{newIDs[0]: math.NaN()}); err == nil {
		t.Fatal("nonfinite priority accepted")
	}
	seed[0][0] = seed[1][0]
	if _, err = index.ForPackages(packages, seed, nil); err == nil {
		t.Fatal("physical ID conflict accepted")
	}
}

package domain

import (
	"fmt"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestNoBonusAndSingleTwoPieceAreExactPhysicalPackages(t *testing.T) {
	req := requestFixture(t)
	for slot := 0; slot < 5; slot++ {
		a := req.Artifacts[slot]
		a.ArtifactID = int64(1000 + slot)
		a.SetUID = fmt.Sprintf("singleton_%d", slot)
		req.Artifacts = append(req.Artifacts, a)
	}
	index, e := Build(req, nil)
	if e != nil {
		t.Fatal(e)
	}
	var packs [4]Package
	for i, w := range index.Wearers {
		packs[i] = Package{Sets: w.SelectedSets}
	}
	packs[0] = Package{}
	priority := map[int64]float64{}
	for slot := 0; slot < 5; slot++ {
		priority[int64(1000+slot)] = 100
	}
	seed, e := index.PackageSeed(index.Incumbent, 0, packs[0], priority)
	if e != nil {
		t.Fatal(e)
	}
	view, e := index.ForPackages(packs, seed, nil)
	if e != nil {
		t.Fatal(e)
	}
	counts, e := view.SelectedSetCounts(seed)
	if e != nil || len(counts[0]) != 0 {
		t.Fatal("zero package emitted bonus", counts, e)
	}
	bad := seed
	bad[0][0] = index.Incumbent[0][0]
	bad[0][1] = index.Incumbent[0][1]
	if view.ValidateAssignment(bad) == nil {
		t.Fatal("hidden 2p passed zero-bonus formula")
	}
	packs[0] = Package{Sets: []contracts.SetRequirement{{SetUID: index.Wearers[0].SelectedSets[0].SetUID, Count: 2}}}
	seed, e = index.PackageSeed(index.Incumbent, 0, packs[0], priority)
	if e != nil {
		t.Fatal(e)
	}
	view, e = index.ForPackages(packs, seed, nil)
	if e != nil {
		t.Fatal(e)
	}
	if view.ValidateAssignment(index.Incumbent) == nil {
		t.Fatal("hidden 4p passed 2p formula")
	}
}

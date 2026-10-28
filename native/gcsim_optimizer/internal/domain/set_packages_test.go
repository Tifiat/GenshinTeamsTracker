package domain

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"testing"
)

func TestPairLegalityCountsAndZeroDelta(t *testing.T) {
	request := requestFixture(t)
	request.Legality.FixedFourPiece, request.Legality.FixedSetPackages = false, true
	request.Wearers[0].SelectedSetUID = ""
	request.Wearers[0].SelectedSets = []contracts.SetRequirement{{SetUID: "set_a", Count: 2}, {SetUID: "set_x", Count: 2}}
	for i, set := range []string{"set_a", "set_a", "set_x", "set_x", "off"} {
		request.Artifacts[i].SetUID = set
	}
	index, err := Build(request, []string{"actor_a.crit_rate"})
	if err != nil {
		t.Fatal(err)
	}
	deltas, err := index.DenseDeltas(index.Incumbent)
	if err != nil || deltas[0] != 0 {
		t.Fatalf("%v %v", deltas, err)
	}
	counts, err := index.SelectedSetCounts(index.Incumbent)
	if err != nil || len(counts[0]) != 2 || counts[0][0].Count != 2 || counts[0][1].Count != 2 {
		t.Fatalf("%v %v", counts, err)
	}
	index.Artifacts[4].SetUID = "set_x"
	if err := index.ValidateAssignment(index.Incumbent); err != nil {
		t.Fatal("2+3 must pass", err)
	}
	index.Artifacts[3].SetUID = "set_a"
	index.Artifacts[4].SetUID = "set_a"
	if index.ValidateAssignment(index.Incumbent) == nil {
		t.Fatal("4+1 must not replace selected pair")
	}
}

package seteffects

import (
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"testing"
)

func TestNeutralStatRootSelectionDoesNotHideProjectionOrMissingData(t *testing.T) {
	n := ruleTestNeutral()
	n.ReadsComplete = true
	keys := []string{"er"}
	n.Reads = []contracts.NeutralReadRoot{
		{NodeID: 1, Owner: "beta", Stat: "er", Point: contracts.NeutralInputPoint{Order: 10, Frame: 3, Mode: "non_extra_stat"}, Projection: true, Uncertainty: []string{}},
		{NodeID: 2, Owner: "beta", Stat: "er", Point: contracts.NeutralInputPoint{Order: 20, Frame: 4, Mode: "non_extra_stat", StatKeys: &keys}, Uncertainty: []string{}},
	}
	q := RuleStatRead{Owner: 1, Stat: "er", Mode: "non_extra_stat", Frame: 4, Order: 15}
	root, codes, err := findNeutralStatRoot(n, q)
	if err != nil || root.NodeID != 1 || len(codes) != 3 {
		t.Fatal(root, codes, err)
	}
	q.Order = 20
	root, codes, err = findNeutralStatRoot(n, q)
	if err != nil || root.NodeID != 2 || len(codes) != 0 {
		t.Fatal(root, codes, err)
	}
	q.Order = 1
	if _, _, err = findNeutralStatRoot(n, q); err == nil {
		t.Fatal("future stat read accepted")
	}
	q.Order = 20
	q.Owner = 0
	if _, _, err = findNeutralStatRoot(n, q); err == nil {
		t.Fatal("wrong owner accepted")
	}
	q.Owner = 1
	n.ReadsComplete = false
	if _, _, err = findNeutralStatRoot(n, q); err == nil {
		t.Fatal("truncated observations accepted")
	}
}

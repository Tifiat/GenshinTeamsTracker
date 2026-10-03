package domain

import (
	"fmt"
	"reflect"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// Synthetic physical inventory only: no gameplay stats, effects or engine data.
func hypothesisGateFixture(t *testing.T, selected []contracts.SetRequirement, baseKeys [slotCount]string) (
	*LocalAssignmentValidator, [slotCount]int64, [slotCount][]int64, [slotCount]map[string]int64, Assignment,
) {
	t.Helper()
	index := &Index{artifactIndexByID: map[int64]int{}, exactPackages: true}
	add := func(id int64, slot int, setUID string) {
		index.artifactIndexByID[id] = len(index.Artifacts)
		index.Artifacts = append(index.Artifacts, IndexedArtifact{ArtifactID: id, SlotIndex: slot, SetUID: setUID})
		index.CandidateIDsBySlot[slot] = append(index.CandidateIDsBySlot[slot], id)
	}
	var ids [slotCount]map[string]int64
	var pools [slotCount][]int64
	var anchor Assignment
	families := []struct{ key, uid string }{
		{"A1", "A"}, {"A2", "A"}, {"B1", "B"}, {"B2", "B"},
		{"C", "C"}, {"D", "D"}, {"E", "E"}, {"F", "F"}, {"G", "G"},
	}
	order := []string{"B1", "A2", "C", "D", "A1", "E", "B2", "F", "G"}
	for slot := 0; slot < slotCount; slot++ {
		ids[slot] = make(map[string]int64)
		for familyIndex, family := range families {
			id := int64(1000 + 100*slot + familyIndex)
			add(id, slot, family.uid)
			ids[slot][family.key] = id
		}
		for _, key := range order {
			pools[slot] = append(pools[slot], ids[slot][key])
		}
		anchor[0][slot] = ids[slot][baseKeys[slot]]
		for wearer := 1; wearer < wearerCount; wearer++ {
			id := int64(10000 + 100*wearer + slot)
			add(id, slot, fmt.Sprintf("fixed_%d_%d", wearer, slot))
			anchor[wearer][slot] = id
		}
	}
	// Duplicate entries are intentional: the old nested loops visit each one.
	pools[0] = append(pools[0], ids[0]["A1"])
	pools[1] = append(pools[1], ids[1]["A1"])
	for wearer := range index.Wearers {
		index.Wearers[wearer].WearerKey = fmt.Sprintf("wearer_%d", wearer)
	}
	index.Wearers[0].SelectedSets = append([]contracts.SetRequirement(nil), selected...)
	if err := index.ValidateAssignment(anchor); err != nil {
		t.Fatalf("synthetic anchor invalid: %v", err)
	}
	validator, err := index.PrepareLocalAssignmentValidator(anchor, 0)
	if err != nil {
		t.Fatal(err)
	}
	return validator, anchor[0], pools, ids, anchor
}

func hypothesisGatePoolIndex(pool []int64, id int64) int {
	for i, candidate := range pool {
		if candidate == id {
			return i
		}
	}
	return -1
}

func hypothesisGateCount(pool []int64, id int64) int {
	count := 0
	for _, candidate := range pool {
		if candidate == id {
			count++
		}
	}
	return count
}

func hypothesisGateExhaustiveParity(t *testing.T, validator *LocalAssignmentValidator, base [slotCount]int64, pools [slotCount][]int64, plan *HypothesisNeighborhoodGatePlan) {
	t.Helper()
	metadataChecks, ordinaryChecks := 0, 1
	for a := 0; a < slotCount; a++ {
		metadataChecks += len(pools[a])
		ordinaryChecks += len(pools[a])
		if len(plan.Single[a]) != len(pools[a]) {
			t.Fatalf("slot %d single shape %d != %d", a, len(plan.Single[a]), len(pools[a]))
		}
		for poolA, idA := range pools[a] {
			trial := base
			trial[a] = idA
			want := validator.Validate(trial) == nil
			if plan.Single[a][poolA] != want {
				t.Fatalf("single slot %d pool %d ID %d: got %t want %t", a, poolA, idA, plan.Single[a][poolA], want)
			}
		}
		for b := 0; b <= a; b++ {
			if plan.Pairs[a][b] != nil {
				t.Fatalf("reverse/diagonal pair cell %d,%d was populated", a, b)
			}
		}
		for b := a + 1; b < slotCount; b++ {
			ordinaryChecks += len(pools[a]) * len(pools[b])
			if len(plan.Pairs[a][b]) != len(pools[a]) {
				t.Fatalf("pair %d,%d row count %d != %d", a, b, len(plan.Pairs[a][b]), len(pools[a]))
			}
			for poolA, idA := range pools[a] {
				var want []int64
				for _, idB := range pools[b] {
					trial := base
					trial[a], trial[b] = idA, idB
					if validator.Validate(trial) == nil {
						want = append(want, idB)
					}
				}
				if !reflect.DeepEqual(plan.Pairs[a][b][poolA], want) {
					t.Fatalf("pair %d,%d pool %d ID %d: got %v want %v", a, b, poolA, idA, plan.Pairs[a][b][poolA], want)
				}
			}
		}
	}
	if plan.PoolMetadataChecks != metadataChecks || plan.ValidationChecks <= 0 || plan.ValidationChecks > ordinaryChecks {
		t.Fatalf("invalid preparation counts: metadata=%d/%d validation=%d/%d", plan.PoolMetadataChecks, metadataChecks, plan.ValidationChecks, ordinaryChecks)
	}
}

func TestHypothesisNeighborhoodGateMatchesExhaustivePhysicalLegality(t *testing.T) {
	cases := []struct {
		name     string
		selected []contracts.SetRequirement
		base     [slotCount]string
		foldOff  bool
	}{
		{"4p", []contracts.SetRequirement{{SetUID: "A", Count: 4}}, [slotCount]string{"A1", "A1", "A1", "A1", "C"}, true},
		{"2+2", []contracts.SetRequirement{{SetUID: "A", Count: 2}, {SetUID: "B", Count: 2}}, [slotCount]string{"A1", "A1", "B1", "B1", "C"}, true},
		{"single 2p", []contracts.SetRequirement{{SetUID: "A", Count: 2}}, [slotCount]string{"A1", "A1", "C", "D", "E"}, false},
		{"no bonus", nil, [slotCount]string{"C", "D", "E", "F", "G"}, false},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			validator, base, pools, ids, _ := hypothesisGateFixture(t, tc.selected, tc.base)
			plan, err := validator.PrepareHypothesisNeighborhoodGate(base, pools)
			if err != nil {
				t.Fatal(err)
			}
			if plan.FoldedOffClass != tc.foldOff {
				t.Fatalf("off-class folding=%t, want %t", plan.FoldedOffClass, tc.foldOff)
			}
			hypothesisGateExhaustiveParity(t, validator, base, pools, plan)
			if tc.foldOff {
				ordinaryChecks := 1
				for a := 0; a < slotCount; a++ {
					ordinaryChecks += len(pools[a])
					for b := a + 1; b < slotCount; b++ {
						ordinaryChecks += len(pools[a]) * len(pools[b])
					}
				}
				if plan.ValidationChecks*2 >= ordinaryChecks {
					t.Fatalf("family reduction saved too few checks: %d of %d", plan.ValidationChecks, ordinaryChecks)
				}
			}
			if tc.name == "4p" || tc.name == "2+2" {
				row := hypothesisGatePoolIndex(pools[0], ids[0]["B1"])
				if row < 0 || plan.Single[0][row] || hypothesisGateCount(plan.Pairs[0][4][row], ids[4]["A1"]) != 1 {
					t.Fatal("single failure suppressed a legal two-slot package repair")
				}
			}
			if tc.name == "4p" {
				if !plan.Single[4][hypothesisGatePoolIndex(pools[4], ids[4]["A1"])] {
					t.Fatal("fifth selected-set piece should remain legal")
				}
				row := hypothesisGatePoolIndex(pools[0], ids[0]["A1"])
				if hypothesisGateCount(plan.Pairs[0][1][row], ids[1]["A1"]) != 2 {
					t.Fatal("duplicate pool ID did not retain both original-order visits")
				}
			}
			if tc.name == "single 2p" {
				rowA := hypothesisGatePoolIndex(pools[2], ids[2]["A1"])
				rowB := hypothesisGatePoolIndex(pools[2], ids[2]["B1"])
				if !plan.Single[2][rowA] || hypothesisGateCount(plan.Pairs[2][3][rowA], ids[3]["A1"]) != 0 ||
					hypothesisGateCount(plan.Pairs[2][3][rowB], ids[3]["B1"]) != 0 {
					t.Fatal("capped 2p or extra 2p tier became legal")
				}
			}
			if tc.name == "no bonus" {
				row := hypothesisGatePoolIndex(pools[0], ids[0]["A1"])
				if hypothesisGateCount(plan.Pairs[0][1][row], ids[1]["A1"]) != 0 {
					t.Fatal("unselected physical 2p bonus became legal")
				}
			}
		})
	}
}

func TestHypothesisNeighborhoodGateRejectsIncompatibleInputs(t *testing.T) {
	validator, base, pools, ids, anchor := hypothesisGateFixture(t,
		[]contracts.SetRequirement{{SetUID: "A", Count: 4}},
		[slotCount]string{"A1", "A1", "A1", "A1", "C"})
	badBase := base
	badBase[0] = 99999999
	if _, err := validator.PrepareHypothesisNeighborhoodGate(badBase, pools); err == nil || !strings.Contains(err.Error(), "base") {
		t.Fatalf("invalid base accepted: %v", err)
	}
	for _, tc := range []struct {
		name, message string
		id            int64
	}{
		{"missing ID", "unknown", 99999999},
		{"wrong slot", "wrong slot", ids[1]["A1"]},
		{"other wearer", "another wearer", anchor[1][0]},
	} {
		t.Run(tc.name, func(t *testing.T) {
			badPools := pools
			badPools[0] = append([]int64(nil), pools[0]...)
			badPools[0][0] = tc.id
			if _, err := validator.PrepareHypothesisNeighborhoodGate(base, badPools); err == nil || !strings.Contains(err.Error(), tc.message) {
				t.Fatalf("incompatible pool accepted: %v", err)
			}
		})
	}
	var missing *LocalAssignmentValidator
	if _, err := missing.PrepareHypothesisNeighborhoodGate(base, pools); err == nil {
		t.Fatal("missing validator accepted")
	}
}

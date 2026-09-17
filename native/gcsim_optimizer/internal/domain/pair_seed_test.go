package domain

import (
	"reflect"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestPairPackageSeedMatchesTinyExhaustiveOracle(t *testing.T) {
	index := &Index{artifactIndexByID: map[int64]int{}}
	var pools [5][]int64
	var anchor Assignment
	weights := [2]map[int64]float64{{}, {}}
	for slot := 0; slot < 5; slot++ {
		for item, set := range []string{"a", "a", "b", "b", "reserved", "reserved"} {
			id := int64(slot*10 + item + 1)
			index.artifactIndexByID[id] = len(index.Artifacts)
			index.Artifacts = append(index.Artifacts, IndexedArtifact{ArtifactID: id, SlotIndex: slot, SetUID: set})
			index.CandidateIDsBySlot[slot] = append(index.CandidateIDsBySlot[slot], id)
			weights[0][id] = float64((id * 7) % 19)
			weights[1][id] = float64((id * 11) % 23)
			if item < 4 {
				pools[slot] = append(pools[slot], id)
			} else {
				anchor[item-2][slot] = id
				weights[0][id] = 10000
				weights[1][id] = 10000
			}
		}
	}
	pack := func(names ...string) Package {
		out := Package{}
		for _, name := range names {
			out.Sets = append(out.Sets, contracts.SetRequirement{SetUID: name, Count: 4 / len(names)})
		}
		return out
	}
	for _, packages := range [][2]Package{{pack("a"), pack("b")}, {pack("a", "b"), pack("a", "b")}, {pack("a"), pack("a")}} {
		got, e := index.PairPackageSeed(anchor, [2]int{0, 1}, packages, weights)
		if e != nil {
			t.Fatal(e)
		}
		var want pairSeedRow
		found := false
		var visit func(int, pairSeedRow)
		visit = func(slot int, row pairSeedRow) {
			if slot == 5 {
				for actor, p := range packages {
					counts := map[string]int{}
					for _, id := range row.ids[actor] {
						key, _ := index.ArtifactSetUID(id)
						counts[key]++
					}
					for _, s := range p.Sets {
						if counts[s.SetUID] < s.Count {
							return
						}
					}
				}
				if !found || row.score > want.score || (row.score == want.score && pairLexLess(row.ids, want.ids)) {
					want = row
					found = true
				}
				return
			}
			for _, a := range pools[slot] {
				for _, b := range pools[slot] {
					if a == b {
						continue
					}
					next := row
					next.ids[0][slot] = a
					next.ids[1][slot] = b
					next.score += weights[0][a] + weights[1][b]
					visit(slot+1, next)
				}
			}
		}
		visit(0, pairSeedRow{})
		if !found || got[0] != want.ids[0] || got[1] != want.ids[1] || got[2] != anchor[2] || got[3] != anchor[3] {
			t.Fatal("joint linear seed differs from tiny oracle", got, want)
		}
		repeat, e := index.PairPackageSeed(anchor, [2]int{0, 1}, packages, weights)
		if e != nil || !reflect.DeepEqual(repeat, got) {
			t.Fatal("nondeterministic seed")
		}
	}
	if _, e := index.PairPackageSeed(anchor, [2]int{0, 0}, [2]Package{pack("a"), pack("b")}, weights); e == nil {
		t.Fatal("same actor twice")
	}
}

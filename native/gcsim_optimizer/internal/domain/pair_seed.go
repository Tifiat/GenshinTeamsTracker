package domain

import (
	"fmt"
	"math"
)

type pairSeedState [2][3]int
type pairSeedRow struct {
	ids   [2][5]int64
	score float64
}
type pairSlotChoice struct {
	ids   [2]int64
	score float64
	valid bool
}

func pairLexLess(a, b [2][5]int64) bool {
	for actor := 0; actor < 2; actor++ {
		for slot := 0; slot < 5; slot++ {
			if a[actor][slot] != b[actor][slot] {
				return a[actor][slot] < b[actor][slot]
			}
		}
	}
	return false
}

// PairPackageSeed releases TWO wearers together while reserving the other ten
// physical IDs. No item-pair Cartesian scan: for each slot/category only the
// best two items per wearer are needed to resolve a possible shared first ID.
// A tiny count-state DP then joins five slots under both package requirements.
// It is exact only for the supplied additive seed priorities, never team DPS.
func (index *Index) PairPackageSeed(anchor Assignment, actors [2]int, packages [2]Package, priority [2]map[int64]float64) (Assignment, error) {
	if index == nil || actors[0] < 0 || actors[0] >= 4 || actors[1] < 0 || actors[1] >= 4 || actors[0] == actors[1] {
		return Assignment{}, fmt.Errorf("invalid pair seed actors")
	}
	for i, p := range packages {
		if e := p.Validate(); e != nil {
			return Assignment{}, e
		}
		for _, v := range priority[i] {
			if math.IsNaN(v) || math.IsInf(v, 0) {
				return Assignment{}, fmt.Errorf("nonfinite pair seed priority")
			}
		}
	}
	used := map[int64]bool{}
	for a, ids := range anchor {
		if a == actors[0] || a == actors[1] {
			continue
		}
		for slot, id := range ids {
			pos, ok := index.artifactIndexByID[id]
			if !ok || used[id] || index.Artifacts[pos].SlotIndex != slot {
				return Assignment{}, fmt.Errorf("invalid reserved pair seed ID")
			}
			used[id] = true
		}
	}
	var best [5][2][3][2]int64
	for slot, ids := range index.CandidateIDsBySlot {
		for _, id := range ids {
			if used[id] {
				continue
			}
			set, _ := index.ArtifactSetUID(id)
			for actor, p := range packages {
				category := len(p.Sets)
				for i, s := range p.Sets {
					if set == s.SetUID {
						category = i
						break
					}
				}
				pair := &best[slot][actor][category]
				better := func(left, right int64) bool {
					return right == 0 || priority[actor][left] > priority[actor][right] || (priority[actor][left] == priority[actor][right] && left < right)
				}
				if better(id, pair[0]) {
					pair[1] = pair[0]
					pair[0] = id
				} else if better(id, pair[1]) {
					pair[1] = id
				}
			}
		}
	}
	var choices [5][3][3]pairSlotChoice
	for slot := 0; slot < 5; slot++ {
		for a := 0; a <= len(packages[0].Sets); a++ {
			for b := 0; b <= len(packages[1].Sets); b++ {
				c := &choices[slot][a][b]
				for _, first := range best[slot][0][a] {
					for _, second := range best[slot][1][b] {
						if first == 0 || second == 0 || first == second {
							continue
						}
						score := priority[0][first] + priority[1][second]
						if !c.valid || score > c.score || (score == c.score && (first < c.ids[0] || (first == c.ids[0] && second < c.ids[1]))) {
							*c = pairSlotChoice{ids: [2]int64{first, second}, score: score, valid: true}
						}
					}
				}
			}
		}
	}
	states := map[pairSeedState]pairSeedRow{{}: {}}
	for slot := 0; slot < 5; slot++ {
		next := map[pairSeedState]pairSeedRow{}
		for counts, row := range states {
			for a := 0; a <= len(packages[0].Sets); a++ {
				for b := 0; b <= len(packages[1].Sets); b++ {
					choice := choices[slot][a][b]
					if !choice.valid {
						continue
					}
					state := counts
					state[0][a]++
					state[1][b]++
					possible := true
					for actor, p := range packages {
						if state[actor][len(p.Sets)] > 1 {
							possible = false
						}
						for category, s := range p.Sets {
							if state[actor][category]+4-slot < s.Count {
								possible = false
							}
						}
					}
					if !possible {
						continue
					}
					candidate := row
					candidate.score += choice.score
					candidate.ids[0][slot] = choice.ids[0]
					candidate.ids[1][slot] = choice.ids[1]
					old, ok := next[state]
					if !ok || candidate.score > old.score || (candidate.score == old.score && pairLexLess(candidate.ids, old.ids)) {
						next[state] = candidate
					}
				}
			}
		}
		states = next
	}
	var winner pairSeedRow
	found := false
	for _, row := range states {
		if !found || row.score > winner.score || (row.score == winner.score && pairLexLess(row.ids, winner.ids)) {
			winner = row
			found = true
		}
	}
	if !found {
		return Assignment{}, fmt.Errorf("no legal joint package seed")
	}
	anchor[actors[0]] = winner.ids[0]
	anchor[actors[1]] = winner.ids[1]
	return anchor, nil
}

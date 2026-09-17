package search

// pairedSetLanes partitions legal builds by set membership, not artifact pairs:
// ten 3+2 patterns, ten 2+3, thirty 2+2+off. Each physical build belongs to
// exactly one lane. Only small slot patterns are enumerated (at most 3^5).
func (engine *Engine) pairedSetLanes(occupied map[int64]struct{}, first, second string) []lane {
	var pools [5][3][]int64
	for slot := 0; slot < 5; slot++ {
		for _, id := range engine.domain.CandidateIDsBySlot[slot] {
			if _, used := occupied[id]; used {
				continue
			}
			set, _ := engine.domain.ArtifactSetUID(id)
			category := 2
			if set == first {
				category = 0
			} else if set == second {
				category = 1
			}
			pools[slot][category] = append(pools[slot][category], id)
		}
	}
	var output []lane
	var walk func(int, [3]int, lane)
	walk = func(slot int, counts [3]int, row lane) {
		if counts[0] > 3 || counts[1] > 3 || counts[2] > 1 {
			return
		}
		remaining := 5 - slot
		if counts[0]+remaining < 2 || counts[1]+remaining < 2 {
			return
		}
		if slot == 5 {
			if counts[0] >= 2 && counts[1] >= 2 {
				output = append(output, row)
			}
			return
		}
		for category, pool := range pools[slot] {
			if len(pool) == 0 {
				continue
			}
			next := row
			next.pools[slot] = pool
			next.raw = saturatingMultiply(row.raw, int64(len(pool)))
			updated := counts
			updated[category]++
			walk(slot+1, updated, next)
		}
	}
	walk(0, [3]int{}, lane{raw: 1})
	return output
}

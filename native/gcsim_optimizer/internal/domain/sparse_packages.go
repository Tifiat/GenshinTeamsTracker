package domain

import (
	"fmt"
	"math/bits"
	"sort"
)

// One best REAL item per family/slot suffices for a linear seed. DP over the
// 32 slot masks finds the maximum-weight legal family matching. No mean item,
// independent stat maxima, or arbitrary family/item shortlist is used.
func (index *Index) sparsePackageSeed(p Package, priority map[int64]float64, used map[int64]bool) ([5]int64, float64, error) {
	by := map[string][5]int64{}
	for _, item := range index.Artifacts {
		if used[item.ArtifactID] {
			continue
		}
		row := by[item.SetUID]
		old := row[item.SlotIndex]
		if old == 0 || priority[item.ArtifactID] > priority[old] || priority[item.ArtifactID] == priority[old] && item.ArtifactID < old {
			row[item.SlotIndex] = item.ArtifactID
			by[item.SetUID] = row
		}
	}
	return chooseSparsePackageLinear(p, by, priority)
}

func chooseSparsePackageLinear(p Package, by map[string][5]int64, priority map[int64]float64) ([5]int64, float64, error) {
	target := ""
	if len(p.Sets) > 0 {
		target = p.Sets[0].SetUID
	}
	keys := make([]string, 0, len(by))
	for key := range by {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	type state struct {
		ok    bool
		value float64
		ids   [5]int64
	}
	var dp [32]state
	dp[0].ok = true
	for _, uid := range keys {
		var next [32]state
		row := by[uid]
		available := 0
		for slot, id := range row {
			if id != 0 {
				available |= 1 << slot
			}
		}
		min, max := 0, 1
		if uid == target {
			min, max = 2, 3
		}
		for mask, old := range dp {
			if !old.ok {
				continue
			}
			free := available &^ mask
			for subset := free; ; subset = (subset - 1) & free {
				count := bits.OnesCount(uint(subset))
				if count >= min && count <= max {
					candidate := old
					for slot, id := range row {
						if subset&(1<<slot) != 0 {
							candidate.value += priority[id]
							candidate.ids[slot] = id
						}
					}
					at := mask | subset
					if !next[at].ok || candidate.value > next[at].value {
						next[at] = candidate
					}
				}
				if subset == 0 {
					break
				}
			}
		}
		dp = next
	}
	if !dp[31].ok || target != "" && by[target] == [5]int64{} {
		return [5]int64{}, 0, fmt.Errorf("no legal completion for package %s", p.Key())
	}
	return dp[31].ids, dp[31].value, nil
}

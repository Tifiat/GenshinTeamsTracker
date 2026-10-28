package domain

import (
	"fmt"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// CanonicalAllSetsAnchor is a reproducible reference, not an incumbent supplied
// by equipped gear. Slot/ID order and wearer order alone choose twenty IDs.
// Every ordinary item remains available to the subsequent search.
func (index *Index) CanonicalAllSetsAnchor() (*Index, [4]Package, error) {
	var packs [4]Package
	if index == nil {
		return nil, packs, fmt.Errorf("nil inventory")
	}
	out := *index
	out.exactPackages = true
	for actor := range out.Wearers {
		w := &out.Wearers[actor]
		w.SelectedSets = nil
		w.incumbentStats = map[string]float64{}
		counts := map[string]int{}
		for slot, ids := range index.CandidateIDsBySlot {
			if len(ids) < 4 {
				return nil, packs, fmt.Errorf("slot %s needs four distinct artifacts", slots[slot])
			}
			id := ids[actor] // Build's canonical request order is strictly sorted by ID.
			out.Incumbent[actor][slot], w.CurrentIDs[slot] = id, id
			item := index.artifact(id)
			counts[item.SetUID]++
			for _, stat := range item.stats {
				w.incumbentStats[stat.key] += stat.value
			}
		}
		keys := []string{}
		for key, count := range counts {
			if count >= 2 {
				keys = append(keys, key)
			}
		}
		sort.Strings(keys)
		for _, key := range keys {
			count := 2
			if counts[key] >= 4 {
				count = 4
			}
			w.SelectedSets = append(w.SelectedSets, contracts.SetRequirement{SetUID: key, Count: count})
		}
		packs[actor] = Package{Sets: w.SelectedSets}
	}
	return &out, packs, out.ValidateAssignment(out.Incumbent)
}

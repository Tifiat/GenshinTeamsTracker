package domain

// One immutable weighted inventory per screening point. Exclusion probes reuse
// ordered REAL items and the same exact family/slot solver as PackageSeed.
// This removes repeated inventory scans, not candidates or bonus packages.
import (
	"fmt"
	"math"
	"sort"
)

type PackageLinearPlan struct {
	pack     Package
	priority map[int64]float64
	groups   map[string][5][]int64
	sparse   bool
}

func (index *Index) PreparePackageLinear(p Package, priority map[int64]float64, occupied map[int64]bool) (*PackageLinearPlan, error) {
	if index == nil {
		return nil, fmt.Errorf("missing package index")
	}
	if err := p.Validate(); err != nil {
		return nil, err
	}
	plan := &PackageLinearPlan{pack: p, priority: make(map[int64]float64, len(priority)), groups: map[string][5][]int64{}, sparse: len(p.Sets) == 0 || len(p.Sets) == 1 && p.Sets[0].Count == 2}
	for id, value := range priority {
		if math.IsNaN(value) || math.IsInf(value, 0) {
			return nil, fmt.Errorf("nonfinite package priority")
		}
		plan.priority[id] = value
	}
	for _, item := range index.Artifacts {
		if occupied[item.ArtifactID] {
			continue
		}
		key := item.SetUID
		if !plan.sparse {
			key = ""
			for _, set := range p.Sets {
				if set.SetUID == item.SetUID {
					key = item.SetUID
					break
				}
			}
		}
		row := plan.groups[key]
		row[item.SlotIndex] = append(row[item.SlotIndex], item.ArtifactID)
		plan.groups[key] = row
	}
	for _, row := range plan.groups {
		for _, ids := range row {
			sort.Slice(ids, func(i, j int) bool {
				if plan.priority[ids[i]] != plan.priority[ids[j]] {
					return plan.priority[ids[i]] > plan.priority[ids[j]]
				}
				return ids[i] < ids[j]
			})
		}
	}
	return plan, nil
}

func (plan *PackageLinearPlan) Assignment(exclude ...int64) ([5]int64, float64, error) {
	by := map[string][5]int64{}
	for uid, slots := range plan.groups {
		var row [5]int64
		for slot, ids := range slots {
			for _, id := range ids {
				skip := false
				for _, x := range exclude {
					if x == id {
						skip = true
						break
					}
				}
				if !skip {
					row[slot] = id
					break
				}
			}
		}
		if row != [5]int64{} {
			by[uid] = row
		}
	}
	if plan.sparse {
		return chooseSparsePackageLinear(plan.pack, by, plan.priority)
	}
	var best [5][3]int64
	for slot := 0; slot < 5; slot++ {
		for category, set := range plan.pack.Sets {
			best[slot][category] = by[set.SetUID][slot]
		}
		best[slot][len(plan.pack.Sets)] = by[""][slot]
	}
	return choosePackageLinear(plan.pack, best, plan.priority)
}

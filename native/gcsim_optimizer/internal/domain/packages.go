package domain

import (
	"fmt"
	"math"
	"math/bits"
	"sort"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// SetCapability is source/catalog metadata, not a stat-effect or activation
// proof. The All Sets orchestrator must bind this catalog to its engine context.
type SetCapability struct {
	UID       string `json:"uid"`
	TwoPiece  bool   `json:"two_piece"`
	FourPiece bool   `json:"four_piece"`
}

type Package struct {
	Sets []contracts.SetRequirement `json:"sets"`
}

// ArtifactLinearPriorities is only an initial-seed guide. Weights come from
// the current team formula, including cross-owner dependencies. No artifact
// is removed because its linear priority is low; FGBS scores complete builds.
func (index *Index) ArtifactLinearPriorities(actor int, weights []float64) (map[int64]float64, error) {
	if index == nil || actor < 0 || actor >= wearerCount || len(weights) != len(index.Coordinates) {
		return nil, fmt.Errorf("invalid item priority input")
	}
	for _, v := range weights {
		if math.IsNaN(v) || math.IsInf(v, 0) {
			return nil, fmt.Errorf("nonfinite item priority")
		}
	}
	out := make(map[int64]float64, len(index.Artifacts))
	prefix := index.Wearers[actor].WearerKey + "."
	for _, item := range index.Artifacts {
		for _, stat := range item.stats {
			if n, ok := index.coordinateIndex[prefix+stat.key]; ok {
				out[item.ArtifactID] += weights[n] * stat.value
			}
		}
	}
	return out, nil
}

func (p Package) Key() string {
	var parts []string
	for _, s := range p.Sets {
		parts = append(parts, fmt.Sprintf("%s:%d", s.SetUID, s.Count))
	}
	return strings.Join(parts, "+")
}

func (p Package) Validate() error {
	if len(p.Sets) != 1 && len(p.Sets) != 2 {
		return fmt.Errorf("package must be 4p or distinct 2+2")
	}
	for i, s := range p.Sets {
		if s.SetUID == "" || s.Count != 4/len(p.Sets) || (i > 0 && p.Sets[i-1].SetUID >= s.SetUID) {
			return fmt.Errorf("noncanonical package")
		}
	}
	return nil
}

// FeasiblePackages is an O(items + sets^2) slot-mask check, not a build search.
// Excluding occupied IDs makes it exact for availability of ONE wearer while
// the other three are fixed; it never proves a whole-team Cartesian assignment.
// Unknown effect semantics do not remove an engine-modeled package.
func (index *Index) FeasiblePackages(catalog []SetCapability, excluded map[int64]bool) ([]Package, error) {
	if index == nil {
		return nil, fmt.Errorf("artifact index required")
	}
	masks := map[string]uint8{}
	var anySlots uint8
	for _, item := range index.Artifacts {
		if excluded[item.ArtifactID] {
			continue
		}
		masks[item.SetUID] |= 1 << item.SlotIndex
		anySlots |= 1 << item.SlotIndex
	}
	if bits.OnesCount8(anySlots) != slotCount {
		return []Package{}, nil
	}
	seen := map[string]bool{}
	var four []Package
	var pairs []string
	for _, s := range catalog {
		if s.UID == "" || seen[s.UID] || (!s.TwoPiece && s.FourPiece) {
			return nil, fmt.Errorf("invalid or duplicate set capability")
		}
		seen[s.UID] = true
		n := bits.OnesCount8(masks[s.UID])
		if s.TwoPiece && s.FourPiece && n >= 4 {
			four = append(four, Package{[]contracts.SetRequirement{{SetUID: s.UID, Count: 4}}})
		}
		if s.TwoPiece && n >= 2 {
			pairs = append(pairs, s.UID)
		}
	}
	sort.Strings(pairs)
	result := four
	for i, a := range pairs {
		for _, b := range pairs[i+1:] {
			if bits.OnesCount8(masks[a]|masks[b]) >= 4 {
				result = append(result, Package{[]contracts.SetRequirement{{SetUID: a, Count: 2}, {SetUID: b, Count: 2}}})
			}
		}
	}
	sort.Slice(result, func(i, j int) bool { return result[i].Key() < result[j].Key() })
	return result, nil
}

// ForPackages creates a cheap immutable inventory view with different fixed
// package constraints/reference coordinates. Raw artifact sums remain relative
// to the ORIGINAL capture stats, not the new feasible seed. No inventory
// reparsing, ID renumbering or implicit set-stat injection is performed.
func (index *Index) ForPackages(packages [wearerCount]Package, seed Assignment, coordinates []string) (*Index, error) {
	if index == nil {
		return nil, fmt.Errorf("artifact index required")
	}
	view := *index
	view.Coordinates = append([]string(nil), coordinates...)
	view.coordinateIndex = make(map[string]int, len(coordinates))
	for i, key := range coordinates {
		if key == "" || (i > 0 && coordinates[i-1] >= key) {
			return nil, fmt.Errorf("noncanonical formula coordinates")
		}
		view.coordinateIndex[key] = i
	}
	for i, p := range packages {
		if err := p.Validate(); err != nil {
			return nil, err
		}
		view.Wearers[i].SelectedSets = append([]contracts.SetRequirement(nil), p.Sets...)
		view.Wearers[i].CurrentIDs = seed[i]
	}
	view.Incumbent = seed
	if err := view.ValidateAssignment(seed); err != nil {
		return nil, err
	}
	return &view, nil
}

// PackageSeed constructs ONE legal wearer completion using only 4p/2+2 slot
// labels (at most 3^5 states), not physical artifact combinations. Priority is
// optional proposal-order information, never a dominance/hard-pruning proof.
// Other wearers remain fixed and retain their IDs. This is an initial feasible
// seed, not the claimed best build; shared FGBS does the actual combination search.
func (index *Index) PackageSeed(anchor Assignment, actor int, p Package, priority map[int64]float64) (Assignment, error) {
	if index == nil || actor < 0 || actor >= wearerCount {
		return Assignment{}, fmt.Errorf("invalid seed owner")
	}
	if err := p.Validate(); err != nil {
		return Assignment{}, err
	}
	for _, score := range priority {
		if math.IsNaN(score) || math.IsInf(score, 0) {
			return Assignment{}, fmt.Errorf("nonfinite package seed priority")
		}
	}
	used := map[int64]bool{}
	for i, ids := range anchor {
		if i != actor {
			for slot, id := range ids {
				pos, ok := index.artifactIndexByID[id]
				if !ok || index.Artifacts[pos].SlotIndex != slot || used[id] {
					return Assignment{}, fmt.Errorf("invalid occupied seed IDs")
				}
				used[id] = true
			}
		}
	}
	chosen, _, err := index.packageLinearSeed(p, priority, used)
	if err != nil {
		return Assignment{}, err
	}
	anchor[actor] = chosen
	return anchor, nil
}

// PackagePriority is a linear relaxation with explicit occupied IDs. Callers
// releasing multiple actors MUST later resolve shared IDs jointly; this scalar
// is not a legal team, formula damage, upper bound or pruning certificate.
func (index *Index) PackagePriority(p Package, priority map[int64]float64, occupied map[int64]bool) (float64, error) {
	_, score, e := index.packageLinearSeed(p, priority, occupied)
	return score, e
}

func (index *Index) packageLinearSeed(p Package, priority map[int64]float64, used map[int64]bool) ([5]int64, float64, error) {
	if index == nil {
		return [5]int64{}, 0, fmt.Errorf("missing package index")
	}
	if e := p.Validate(); e != nil {
		return [5]int64{}, 0, e
	}
	for _, score := range priority {
		if math.IsNaN(score) || math.IsInf(score, 0) {
			return [5]int64{}, 0, fmt.Errorf("nonfinite package priority")
		}
	}
	var best [slotCount][3]int64
	for slot, ids := range index.CandidateIDsBySlot {
		for _, id := range ids {
			if used[id] {
				continue
			}
			set, _ := index.ArtifactSetUID(id)
			category := len(p.Sets)
			for i, s := range p.Sets {
				if s.SetUID == set {
					category = i
					break
				}
			}
			old := best[slot][category]
			if old == 0 || priority[id] > priority[old] || (priority[id] == priority[old] && id < old) {
				best[slot][category] = id
			}
		}
	}
	var chosen [slotCount]int64
	bestScore := 0.0
	found := false
	var visit func(int, [3]int, [slotCount]int64, float64)
	visit = func(slot int, counts [3]int, ids [slotCount]int64, score float64) {
		for i, s := range p.Sets {
			if counts[i]+slotCount-slot < s.Count {
				return
			}
		}
		if slot == slotCount {
			if !found || score > bestScore {
				chosen, bestScore, found = ids, score, true
			}
			return
		}
		for category := 0; category <= len(p.Sets); category++ {
			id := best[slot][category]
			if id == 0 {
				continue
			}
			nextCounts, nextIDs := counts, ids
			nextCounts[category]++
			nextIDs[slot] = id
			visit(slot+1, nextCounts, nextIDs, score+priority[id])
		}
	}
	visit(0, [3]int{}, [slotCount]int64{}, 0)
	if !found {
		return [5]int64{}, 0, fmt.Errorf("no legal completion for package %s", p.Key())
	}
	return chosen, bestScore, nil
}

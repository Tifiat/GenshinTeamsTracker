package domain

import "fmt"

// HypothesisNeighborhoodGatePlan is a research-only physical-legality lookup
// for one fixed valid wearer base. Single[slot][poolIndex] records a one-slot
// replacement. For a < b, Pairs[a][b][indexA] contains the ORIGINAL-ORDER
// pool-b IDs that pass LocalAssignmentValidator.Validate when both slots are
// replaced. Reverse and diagonal pair cells are deliberately empty. Repeated
// pool IDs remain repeated, matching an ordinary pool visit.
//
// These booleans and lists say nothing about stats, effects, response coverage
// or candidate quality. The caller must still score and retain legal builds.
type HypothesisNeighborhoodGatePlan struct {
	Single             [slotCount][]bool
	Pairs              [slotCount][slotCount][][]int64
	ValidationChecks   int // base plus family-representative single/pair checks
	PoolMetadataChecks int // one check per input pool entry, including duplicates
	FoldedOffClass     bool
}

type hypothesisNeighborhoodClass struct {
	uid string
	off bool // typed sentinel; cannot collide with any physical SetUID
}

type hypothesisNeighborhoodRepresentative struct {
	id int64
}

// PrepareHypothesisNeighborhoodGate validates the base once and all pool
// metadata once. Every family eligibility decision uses the existing physical
// validator, including exact package tiers. A malformed/incompatible pool
// returns an error so a research caller can fall back to ordinary enumeration.
// Single failures never skip pair checks: a second replacement can repair a
// required 4p or 2+2 count.
func (validator *LocalAssignmentValidator) PrepareHypothesisNeighborhoodGate(
	base [slotCount]int64, pools [slotCount][]int64,
) (*HypothesisNeighborhoodGatePlan, error) {
	if err := validator.Validate(base); err != nil {
		return nil, fmt.Errorf("invalid neighborhood base: %w", err)
	}
	plan := &HypothesisNeighborhoodGatePlan{ValidationChecks: 1}
	selectedUIDs := make(map[string]struct{}, len(validator.selectedSets))
	requiredCount, distinct := 0, true
	for _, selected := range validator.selectedSets {
		if selected.SetUID == "" || selected.Count != 2 && selected.Count != 4 {
			distinct = false
		}
		if _, exists := selectedUIDs[selected.SetUID]; exists {
			distinct = false
		} else {
			selectedUIDs[selected.SetUID] = struct{}{}
			requiredCount += selected.Count
		}
	}
	// With at least four required pieces across distinct selected UIDs, any
	// legal five-item completion has at most one outsider. Its physical UID
	// cannot create an extra 2p bonus, so nonselected families are equivalent
	// for THIS legality check. For 2p/none, preserve every real UID: two
	// outsiders might otherwise make an unrepresented bonus.
	plan.FoldedOffClass = distinct && requiredCount >= 4

	var familyByPool [slotCount][]int
	var representatives [slotCount][]hypothesisNeighborhoodRepresentative
	for slot, ids := range pools {
		familyByPool[slot] = make([]int, len(ids))
		plan.Single[slot] = make([]bool, len(ids))
		familyIndex := make(map[hypothesisNeighborhoodClass]int)
		for poolIndex, id := range ids {
			plan.PoolMetadataChecks++
			artifactIndex, exists := validator.index.artifactIndexByID[id]
			if !exists || artifactIndex < 0 || artifactIndex >= len(validator.index.Artifacts) {
				return nil, fmt.Errorf("pool slot %s index %d references unknown artifact %d", slots[slot], poolIndex, id)
			}
			artifact := validator.index.Artifacts[artifactIndex]
			if artifact.SlotIndex != slot {
				return nil, fmt.Errorf("pool slot %s index %d has artifact %d in the wrong slot", slots[slot], poolIndex, id)
			}
			if _, occupied := validator.occupied[id]; occupied {
				return nil, fmt.Errorf("pool slot %s index %d has artifact %d assigned to another wearer", slots[slot], poolIndex, id)
			}
			class := hypothesisNeighborhoodClass{uid: artifact.SetUID}
			if _, selected := selectedUIDs[artifact.SetUID]; plan.FoldedOffClass && !selected {
				class = hypothesisNeighborhoodClass{off: true}
			}
			representativeIndex, known := familyIndex[class]
			if !known {
				representativeIndex = len(representatives[slot])
				familyIndex[class] = representativeIndex
				representatives[slot] = append(representatives[slot], hypothesisNeighborhoodRepresentative{id: id})
			}
			familyByPool[slot][poolIndex] = representativeIndex
		}
	}
	for slot, families := range representatives {
		allowed := make([]bool, len(families))
		for familyIndex, family := range families {
			trial := base
			trial[slot] = family.id
			plan.ValidationChecks++
			allowed[familyIndex] = validator.Validate(trial) == nil
		}
		for poolIndex, familyIndex := range familyByPool[slot] {
			plan.Single[slot][poolIndex] = allowed[familyIndex]
		}
	}
	for a := 0; a < slotCount; a++ {
		for b := a + 1; b < slotCount; b++ {
			allowed := make([][]bool, len(representatives[a]))
			for familyA, itemA := range representatives[a] {
				allowed[familyA] = make([]bool, len(representatives[b]))
				for familyB, itemB := range representatives[b] {
					trial := base
					trial[a], trial[b] = itemA.id, itemB.id
					plan.ValidationChecks++
					allowed[familyA][familyB] = validator.Validate(trial) == nil
				}
			}
			plan.Pairs[a][b] = make([][]int64, len(pools[a]))
			for poolA, familyA := range familyByPool[a] {
				for poolB, idB := range pools[b] {
					if allowed[familyA][familyByPool[b][poolB]] {
						plan.Pairs[a][b][poolA] = append(plan.Pairs[a][b][poolA], idB)
					}
				}
			}
		}
	}
	return plan, nil
}

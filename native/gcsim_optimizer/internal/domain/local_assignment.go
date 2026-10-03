package domain

import (
	"fmt"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// LocalAssignmentValidator checks replacements for one wearer while the other
// wearers stay fixed at a previously validated anchor.
type LocalAssignmentValidator struct {
	index         *Index
	actor         int
	occupied      map[int64]struct{}
	selectedSets  []contracts.SetRequirement
	exactPackages bool
}

// PrepareLocalAssignmentValidator validates the anchor once and retains its
// fixed item IDs and package rules for repeated single-wearer checks.
func (index *Index) PrepareLocalAssignmentValidator(anchor Assignment, actor int) (*LocalAssignmentValidator, error) {
	if index == nil {
		return nil, fmt.Errorf("artifact index is nil")
	}
	if actor < 0 || actor >= wearerCount {
		return nil, fmt.Errorf("invalid local assignment wearer")
	}
	if err := index.ValidateAssignment(anchor); err != nil {
		return nil, err
	}
	occupied := make(map[int64]struct{}, (wearerCount-1)*slotCount)
	for wearerIndex, wearerIDs := range anchor {
		if wearerIndex == actor {
			continue
		}
		for _, id := range wearerIDs {
			occupied[id] = struct{}{}
		}
	}
	return &LocalAssignmentValidator{
		index:         index,
		actor:         actor,
		occupied:      occupied,
		selectedSets:  append([]contracts.SetRequirement(nil), index.Wearers[actor].SelectedSets...),
		exactPackages: index.exactPackages,
	}, nil
}

// Validate checks the five replacement IDs against the prepared fixed team.
func (validator *LocalAssignmentValidator) Validate(ids [slotCount]int64) error {
	if validator == nil || validator.index == nil || validator.actor < 0 || validator.actor >= wearerCount {
		return fmt.Errorf("local assignment validator is unavailable")
	}
	var setUIDs [slotCount]string
	var setCounts [slotCount]int
	setCount := 0
	for slot, id := range ids {
		artifactIndex, ok := validator.index.artifactIndexByID[id]
		if !ok {
			return fmt.Errorf("wearer %d slot %s references unknown artifact %d", validator.actor, slots[slot], id)
		}
		artifact := validator.index.Artifacts[artifactIndex]
		if artifact.SlotIndex != slot {
			return fmt.Errorf("artifact %d is in the wrong slot", id)
		}
		if _, exists := validator.occupied[id]; exists {
			return fmt.Errorf("artifact %d is already assigned to another wearer", id)
		}
		for previous := 0; previous < slot; previous++ {
			if ids[previous] == id {
				return fmt.Errorf("artifact %d is assigned more than once", id)
			}
		}
		setIndex := 0
		for setIndex < setCount && setUIDs[setIndex] != artifact.SetUID {
			setIndex++
		}
		if setIndex == setCount {
			setUIDs[setIndex] = artifact.SetUID
			setCounts[setIndex] = 1
			setCount++
		} else {
			setCounts[setIndex]++
		}
	}
	for _, selected := range validator.selectedSets {
		count := 0
		for setIndex := 0; setIndex < setCount; setIndex++ {
			if setUIDs[setIndex] == selected.SetUID {
				count = setCounts[setIndex]
				break
			}
		}
		if count < selected.Count {
			return fmt.Errorf("wearer %s does not satisfy fixed set package %s:%d", validator.index.Wearers[validator.actor].WearerKey, selected.SetUID, selected.Count)
		}
	}
	if validator.exactPackages {
		for setIndex := 0; setIndex < setCount; setIndex++ {
			count := setCounts[setIndex]
			if count < 2 {
				continue
			}
			found := false
			for _, selected := range validator.selectedSets {
				if selected.SetUID == setUIDs[setIndex] && (selected.Count == 4 && count >= 4 || selected.Count == 2 && count < 4) {
					found = true
					break
				}
			}
			if !found {
				return fmt.Errorf("wearer %s has unrepresented bonus %s:%d", validator.index.Wearers[validator.actor].WearerKey, setUIDs[setIndex], count)
			}
		}
	}
	return nil
}

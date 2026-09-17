// Package domain compiles the immutable artifact request into indexed numeric
// data used by search. It owns physical legality, not formula arithmetic.
package domain

import (
	"fmt"
	"math"
	"strconv"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

const wearerCount = 4
const slotCount = 5

var slots = [slotCount]string{"flower", "plume", "sands", "goblet", "circlet"}

type statValue struct {
	key   string
	value float64
}

type IndexedArtifact struct {
	ArtifactID int64
	SlotIndex  int
	SetUID     string
	stats      []statValue
}

type IndexedWearer struct {
	WearerKey      string
	SelectedSets   []contracts.SetRequirement
	CurrentIDs     [slotCount]int64
	incumbentStats map[string]float64
}

type Assignment [wearerCount][slotCount]int64

type Index struct {
	Artifacts          []IndexedArtifact
	Wearers            [wearerCount]IndexedWearer
	CandidateIDsBySlot [slotCount][]int64
	Coordinates        []string
	coordinateIndex    map[string]int
	artifactIndexByID  map[int64]int
	Incumbent          Assignment
}

// AssignmentStats returns the complete artifact stat totals for every wearer.
// Unlike DenseDeltas, this deliberately keeps coordinates which are absent
// from the compact formula because ordinary finalist simulation must render
// the exact physical build, not only the formula-visible part of it.
func (index *Index) AssignmentStats(assignment Assignment) ([wearerCount]map[string]float64, error) {
	var output [wearerCount]map[string]float64
	if err := index.ValidateAssignment(assignment); err != nil {
		return output, err
	}
	for wearerIndex, wearerIDs := range assignment {
		stats := make(map[string]float64)
		for _, artifactID := range wearerIDs {
			for _, stat := range index.artifact(artifactID).stats {
				stats[stat.key] += stat.value
			}
		}
		output[wearerIndex] = stats
	}
	return output, nil
}

// SelectedSetCounts returns actual counts for each selected bonus package.
// Singleton off-set pieces have no active bonus and are not emitted.
func (index *Index) SelectedSetCounts(assignment Assignment) ([wearerCount][]contracts.SetRequirement, error) {
	var output [wearerCount][]contracts.SetRequirement
	if err := index.ValidateAssignment(assignment); err != nil {
		return output, err
	}
	for wearerIndex, wearerIDs := range assignment {
		for _, set := range index.Wearers[wearerIndex].SelectedSets {
			count := 0
			for _, artifactID := range wearerIDs {
				if index.artifact(artifactID).SetUID == set.SetUID {
					count++
				}
			}
			output[wearerIndex] = append(output[wearerIndex], contracts.SetRequirement{SetUID: set.SetUID, Count: count})
		}
	}
	return output, nil
}

func Build(request contracts.OptimizerRequest, coordinates []string) (*Index, error) {
	if err := request.Validate(); err != nil {
		return nil, err
	}
	coordinateIndex := make(map[string]int, len(coordinates))
	for index, coordinate := range coordinates {
		if coordinate == "" || (index > 0 && coordinates[index-1] >= coordinate) {
			return nil, fmt.Errorf("formula coordinates must be strictly sorted and unique")
		}
		coordinateIndex[coordinate] = index
	}
	output := &Index{
		Artifacts:         make([]IndexedArtifact, 0, len(request.Artifacts)),
		Coordinates:       append([]string(nil), coordinates...),
		coordinateIndex:   coordinateIndex,
		artifactIndexByID: make(map[int64]int, len(request.Artifacts)),
	}
	for _, artifact := range request.Artifacts {
		row := IndexedArtifact{
			ArtifactID: artifact.ArtifactID,
			SlotIndex:  slotIndex(artifact.Slot),
			SetUID:     artifact.SetUID,
			stats:      make([]statValue, 0, len(artifact.Substats)+1),
		}
		main, err := parseStat(artifact.MainStat)
		if err != nil {
			return nil, fmt.Errorf("artifact %d main stat: %w", artifact.ArtifactID, err)
		}
		row.stats = append(row.stats, main)
		for _, stat := range artifact.Substats {
			parsed, err := parseStat(stat)
			if err != nil {
				return nil, fmt.Errorf("artifact %d substat: %w", artifact.ArtifactID, err)
			}
			row.stats = append(row.stats, parsed)
		}
		output.artifactIndexByID[row.ArtifactID] = len(output.Artifacts)
		output.Artifacts = append(output.Artifacts, row)
		output.CandidateIDsBySlot[row.SlotIndex] = append(output.CandidateIDsBySlot[row.SlotIndex], row.ArtifactID)
	}
	for wearerIndex, wearer := range request.Wearers {
		indexed := IndexedWearer{
			WearerKey:      wearer.WearerKey,
			SelectedSets:   append([]contracts.SetRequirement(nil), wearer.SetRequirements()...),
			incumbentStats: make(map[string]float64),
		}
		for slotIndex, assignment := range wearer.CurrentArtifacts {
			indexed.CurrentIDs[slotIndex] = assignment.ArtifactID
			output.Incumbent[wearerIndex][slotIndex] = assignment.ArtifactID
			artifact := output.artifact(assignment.ArtifactID)
			for _, stat := range artifact.stats {
				indexed.incumbentStats[stat.key] += stat.value
			}
		}
		output.Wearers[wearerIndex] = indexed
	}
	if err := output.ValidateAssignment(output.Incumbent); err != nil {
		return nil, fmt.Errorf("incumbent assignment: %w", err)
	}
	return output, nil
}

func (index *Index) ValidateAssignment(assignment Assignment) error {
	if index == nil {
		return fmt.Errorf("artifact index is nil")
	}
	used := make(map[int64]struct{}, wearerCount*slotCount)
	for wearerIndex, wearerIDs := range assignment {
		var setCounts [2]int
		for slotIndex, artifactID := range wearerIDs {
			artifactIndex, ok := index.artifactIndexByID[artifactID]
			if !ok {
				return fmt.Errorf("wearer %d slot %s references unknown artifact %d", wearerIndex, slots[slotIndex], artifactID)
			}
			artifact := index.Artifacts[artifactIndex]
			if artifact.SlotIndex != slotIndex {
				return fmt.Errorf("artifact %d is in the wrong slot", artifactID)
			}
			if _, exists := used[artifactID]; exists {
				return fmt.Errorf("artifact %d is assigned more than once", artifactID)
			}
			used[artifactID] = struct{}{}
			for i, set := range index.Wearers[wearerIndex].SelectedSets {
				if artifact.SetUID == set.SetUID {
					setCounts[i]++
				}
			}
		}
		for i, set := range index.Wearers[wearerIndex].SelectedSets {
			if setCounts[i] < set.Count {
				return fmt.Errorf("wearer %s does not satisfy fixed set package %s:%d", index.Wearers[wearerIndex].WearerKey, set.SetUID, set.Count)
			}
		}
	}
	return nil
}

// DenseDeltas converts a legal physical assignment into the exact formula
// coordinate order. Stats absent from the formula are intentionally ignored.
func (index *Index) DenseDeltas(assignment Assignment) ([]float64, error) {
	if err := index.ValidateAssignment(assignment); err != nil {
		return nil, err
	}
	deltas := make([]float64, len(index.Coordinates))
	for wearerIndex, wearerIDs := range assignment {
		candidate := make(map[string]float64)
		for _, artifactID := range wearerIDs {
			for _, stat := range index.artifact(artifactID).stats {
				candidate[stat.key] += stat.value
			}
		}
		wearer := index.Wearers[wearerIndex]
		for key, value := range candidate {
			coordinate := wearer.WearerKey + "." + key
			if coordinateIndex, ok := index.coordinateIndex[coordinate]; ok {
				deltas[coordinateIndex] = value - wearer.incumbentStats[key]
			}
		}
		for key, incumbent := range wearer.incumbentStats {
			if _, exists := candidate[key]; exists {
				continue
			}
			coordinate := wearer.WearerKey + "." + key
			if coordinateIndex, ok := index.coordinateIndex[coordinate]; ok {
				deltas[coordinateIndex] = -incumbent
			}
		}
	}
	return deltas, nil
}

func (index *Index) artifact(id int64) IndexedArtifact {
	return index.Artifacts[index.artifactIndexByID[id]]
}

func (index *Index) ArtifactSetUID(id int64) (string, bool) {
	position, ok := index.artifactIndexByID[id]
	if !ok {
		return "", false
	}
	return index.Artifacts[position].SetUID, true
}

func parseStat(stat contracts.StatValue) (statValue, error) {
	value, err := strconv.ParseFloat(stat.Value, 64)
	if err != nil || math.IsNaN(value) || math.IsInf(value, 0) {
		return statValue{}, fmt.Errorf("invalid numeric value")
	}
	return statValue{key: stat.Key, value: value}, nil
}

func slotIndex(slot string) int {
	for index, value := range slots {
		if value == slot {
			return index
		}
	}
	panic("validated artifact slot not found: " + strings.TrimSpace(slot))
}

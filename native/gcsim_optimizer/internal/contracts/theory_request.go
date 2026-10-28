package contracts

import "fmt"

var theoryBaselineSlots = [...]string{"flower", "plume", "sands", "goblet", "circlet"}

var theoryBaselineValues = map[string]StatValue{
	"flower":  {Key: "hp", Value: "4780"},
	"plume":   {Key: "atk", Value: "311"},
	"sands":   {Key: "atk_percent", Value: "0.466"},
	"goblet":  {Key: "atk_percent", Value: "0.466"},
	"circlet": {Key: "crit_rate", Value: "0.311"},
}

// ExpandTheoryBaselines returns a normal strict optimizer request whose
// private synthetic artifacts exist only inside the Theory process. The wire
// request keeps CurrentArtifacts empty and therefore never claims owned IDs.
func (request OptimizerRequest) ExpandTheoryBaselines() (OptimizerRequest, error) {
	if !request.Legality.TheorySearch || request.Legality.FixedFourPiece || request.Legality.FixedSetPackages {
		return OptimizerRequest{}, fmt.Errorf("theory request requires the neutral Theory legality policy")
	}
	if len(request.Artifacts) != 0 {
		return OptimizerRequest{}, fmt.Errorf("theory wire request must not contain owned artifacts")
	}
	expanded := request
	expanded.Wearers = append([]Wearer(nil), request.Wearers...)
	expanded.Artifacts = append([]Artifact(nil), request.Artifacts...)
	var nextID int64
	for _, artifact := range expanded.Artifacts {
		if artifact.ArtifactID > nextID {
			nextID = artifact.ArtifactID
		}
	}
	for wearerIndex := range expanded.Wearers {
		wearer := expanded.Wearers[wearerIndex]
		baseline := wearer.TheoryBaseline
		if baseline == nil {
			return OptimizerRequest{}, fmt.Errorf("wearers[%d] is missing theory_baseline", wearerIndex)
		}
		if wearer.SelectedSetUID != "" || len(wearer.SelectedSets) != 0 {
			return OptimizerRequest{}, fmt.Errorf("wearers[%d] theory baseline must not select an initial set package", wearerIndex)
		}
		if len(wearer.CurrentArtifacts) != 0 {
			return OptimizerRequest{}, fmt.Errorf(
				"wearers[%d] theory baseline cannot claim current artifacts",
				wearerIndex,
			)
		}
		if err := validateTheoryBaseline(wearerIndex, *baseline); err != nil {
			return OptimizerRequest{}, err
		}
		assignments := make([]ArtifactAssignment, 0, len(theoryBaselineSlots))
		for slotIndex, row := range baseline.MainStats {
			nextID++
			expanded.Artifacts = append(expanded.Artifacts, Artifact{
				ArtifactID: nextID,
				Slot:       row.Slot,
				SetUID:     fmt.Sprintf("gtt_theory_neutral_%d_%d", wearerIndex+1, slotIndex+1),
				Rarity:     5,
				Level:      20,
				MainStat:   StatValue{Key: row.Key, Value: row.Value},
				Substats:   []StatValue{},
			})
			assignments = append(assignments, ArtifactAssignment{
				WearerKey:  wearer.WearerKey,
				Slot:       row.Slot,
				ArtifactID: nextID,
			})
		}
		wearer.CurrentArtifacts = assignments
		wearer.TheoryBaseline = nil
		expanded.Wearers[wearerIndex] = wearer
	}
	if err := expanded.ValidateTheory(); err != nil {
		return OptimizerRequest{}, err
	}
	return expanded, nil
}

func validateTheoryBaseline(wearerIndex int, baseline TheoryArtifactBaseline) error {
	if len(baseline.MainStats) != len(theoryBaselineSlots) {
		return fmt.Errorf("wearers[%d].theory_baseline must contain five main stats", wearerIndex)
	}
	for index, row := range baseline.MainStats {
		expectedSlot := theoryBaselineSlots[index]
		expected := theoryBaselineValues[expectedSlot]
		if row.Slot != expectedSlot || row.Key != expected.Key || row.Value != expected.Value {
			return fmt.Errorf(
				"wearers[%d].theory_baseline.main_stats[%d] is not the canonical baseline",
				wearerIndex,
				index,
			)
		}
	}
	return nil
}

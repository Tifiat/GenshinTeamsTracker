package energy

import (
	"fmt"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

func TestRequirementUsesBurstDeadlinesAndCharacterKeys(t *testing.T) {
	request := energyRequest(t)
	index, err := domain.Build(request, nil)
	if err != nil {
		t.Fatal(err)
	}
	incumbentER, err := index.IncumbentStat(0, energyRechargeKey)
	if err != nil {
		t.Fatal(err)
	}
	states := make([]contracts.IREnergyCharacterState, 4)
	for sequence := range states {
		actor := 3 - sequence // engine/config order need not equal optimizer order
		states[sequence] = contracts.IREnergyCharacterState{
			CharacterIndex: sequence, CharacterKey: index.Wearers[actor].WearerKey,
			Energy: "60", EnergyMax: "60",
		}
	}
	key := index.Wearers[0].WearerKey
	characterIndex := 3
	raw, observed := "30", decimalText(1+incumbentER)
	onField := true
	member := contracts.IRSeedMember{EnergyLedger: &contracts.IREnergyLedger{
		InitialStates: states,
		Events: []contracts.IREnergyEvent{
			{SequenceIndex: 0, Frame: 10, CharacterIndex: characterIndex, CharacterKey: key, Kind: "burst", Source: key + "-burst", EnergyBefore: "60", EnergyAfter: "0", EnergyMax: "60", Amount: "60"},
			{SequenceIndex: 1, Frame: 20, CharacterIndex: characterIndex, CharacterKey: key, Kind: "flat", Source: "flat-refund", EnergyBefore: "0", EnergyAfter: "10", EnergyMax: "60", Amount: "10"},
			{SequenceIndex: 2, Frame: 30, CharacterIndex: characterIndex, CharacterKey: key, Kind: "particle", Source: "skill-particle", EnergyBefore: "10", EnergyAfter: "40", EnergyMax: "60", Amount: raw, RawAtER100: &raw, ObservedER: &observed, OnField: &onField},
			{SequenceIndex: 3, Frame: 40, CharacterIndex: characterIndex, CharacterKey: key, Kind: "burst", Source: key + "-burst", EnergyBefore: "40", EnergyAfter: "0", EnergyMax: "60", Amount: "60"},
			// This particle is after the deadline and must not pay the second burst.
			{SequenceIndex: 4, Frame: 50, CharacterIndex: characterIndex, CharacterKey: key, Kind: "particle", Source: "late-particle", EnergyBefore: "0", EnergyAfter: "30", EnergyMax: "60", Amount: raw, RawAtER100: &raw, ObservedER: &observed, OnField: &onField},
		},
		UncertaintyCodes: []string{"energy_source_schedule_observed_not_symbolic"},
	}}
	model, err := Compile(index, []contracts.IRSeedMember{member})
	if err != nil {
		t.Fatal(err)
	}
	assessment, err := model.Assess(index.Incumbent)
	if err != nil {
		t.Fatal(err)
	}
	want := 2.0 / 3.0
	if math.Abs(assessment.Wearers[0].RequiredArtifactER-want) > 1e-7 {
		t.Fatalf("required artifact ER = %.9f, want %.9f", assessment.Wearers[0].RequiredArtifactER, want)
	}
	if assessment.Wearers[0].BurstDeadlines != 2 {
		t.Fatalf("burst deadlines = %d", assessment.Wearers[0].BurstDeadlines)
	}
	for actor := 1; actor < 4; actor++ {
		if assessment.Wearers[actor].RequiredArtifactER != 0 || !assessment.Wearers[actor].Feasible {
			t.Fatalf("inactive wearer %d assessment = %#v", actor, assessment.Wearers[actor])
		}
	}
}

func TestAssessmentDistinguishesInsufficientAndExcessArtifactER(t *testing.T) {
	request := energyRequest(t)
	alternative := request.Artifacts[0]
	alternative.ArtifactID = 99002
	alternative.Substats = []contracts.StatValue{{Key: energyRechargeKey, Value: "0.8"}}
	request.Artifacts = append(request.Artifacts, alternative)
	index, err := domain.Build(request, nil)
	if err != nil {
		t.Fatal(err)
	}
	incumbentER, err := index.IncumbentStat(0, energyRechargeKey)
	if err != nil {
		t.Fatal(err)
	}
	states := make([]contracts.IREnergyCharacterState, 4)
	for actor, wearer := range index.Wearers {
		states[actor] = contracts.IREnergyCharacterState{
			CharacterIndex: actor, CharacterKey: wearer.WearerKey,
			Energy: "60", EnergyMax: "60",
		}
	}
	key := index.Wearers[0].WearerKey
	raw, observed := "40", decimalText(1+incumbentER)
	onField := true
	member := contracts.IRSeedMember{EnergyLedger: &contracts.IREnergyLedger{
		InitialStates: states,
		Events: []contracts.IREnergyEvent{
			{SequenceIndex: 0, Frame: 1, CharacterIndex: 0, CharacterKey: key, Kind: "burst", Source: key + "-burst", EnergyBefore: "60", EnergyAfter: "0", EnergyMax: "60", Amount: "60"},
			{SequenceIndex: 1, Frame: 2, CharacterIndex: 0, CharacterKey: key, Kind: "particle", Source: "skill", EnergyBefore: "0", EnergyAfter: raw, EnergyMax: "60", Amount: raw, RawAtER100: &raw, ObservedER: &observed, OnField: &onField},
			{SequenceIndex: 2, Frame: 3, CharacterIndex: 0, CharacterKey: key, Kind: "burst", Source: key + "-burst", EnergyBefore: raw, EnergyAfter: "0", EnergyMax: "60", Amount: "60"},
		},
	}}
	model, err := Compile(index, []contracts.IRSeedMember{member})
	if err != nil {
		t.Fatal(err)
	}
	insufficient, err := model.Assess(index.Incumbent)
	if err != nil {
		t.Fatal(err)
	}
	if insufficient.Feasible || insufficient.Wearers[0].MaximumShortage <= 0 || insufficient.Wearers[0].Margin >= 0 {
		t.Fatalf("incumbent should be energy-insufficient: %#v", insufficient.Wearers[0])
	}
	highER := index.Incumbent
	highER[0][0] = alternative.ArtifactID
	excess, err := model.Assess(highER)
	if err != nil {
		t.Fatal(err)
	}
	if !excess.Feasible || !excess.Wearers[0].Feasible || excess.Wearers[0].MaximumShortage != 0 || excess.Wearers[0].Margin <= 0 {
		t.Fatalf("high-ER assignment should have a positive margin: %#v", excess.Wearers[0])
	}
}

func energyRequest(t *testing.T) contracts.OptimizerRequest {
	t.Helper()
	_, filename, _, _ := runtime.Caller(0)
	path := filepath.Join(filepath.Dir(filename), "..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", "request_v1.json")
	payload, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	request, err := contracts.DecodeRequest(payload)
	if err != nil {
		t.Fatal(err)
	}
	return request
}

func decimalText(value float64) string {
	return fmt.Sprintf("%.12g", value)
}

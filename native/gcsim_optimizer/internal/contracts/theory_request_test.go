package contracts

import (
	"strings"
	"testing"
)

func canonicalTheoryBaseline() *TheoryArtifactBaseline {
	return &TheoryArtifactBaseline{MainStats: []TheoryMainStat{
		{Slot: "flower", Key: "hp", Value: "4780"},
		{Slot: "plume", Key: "atk", Value: "311"},
		{Slot: "sands", Key: "atk_percent", Value: "0.466"},
		{Slot: "goblet", Key: "atk_percent", Value: "0.466"},
		{Slot: "circlet", Key: "crit_rate", Value: "0.311"},
	}}
}

func neutralTheoryRequest(t *testing.T) OptimizerRequest {
	t.Helper()
	request, err := DecodeRequest(readFixture(t, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	request.Artifacts = []Artifact{}
	request.Legality.FixedFourPiece = false
	request.Legality.FixedSetPackages = false
	request.Legality.TheorySearch = true
	request.Legality.MaxOffSetPiecesPerWearer = 0
	for index := range request.Wearers {
		request.Wearers[index].SelectedSetUID = ""
		request.Wearers[index].SelectedSets = nil
		request.Wearers[index].CurrentArtifacts = []ArtifactAssignment{}
		request.Wearers[index].TheoryBaseline = canonicalTheoryBaseline()
	}
	return request
}

func TestDecodeTheoryRequestExpandsPrivateBaselineWithoutChangingWireIdentity(t *testing.T) {
	request := neutralTheoryRequest(t)
	payload, err := CanonicalJSON(request)
	if err != nil {
		t.Fatal(err)
	}

	raw, expanded, err := DecodeTheoryRequest(payload)
	if err != nil {
		t.Fatal(err)
	}
	if raw.Wearers[0].TheoryBaseline == nil || len(raw.Wearers[0].CurrentArtifacts) != 0 {
		t.Fatal("raw Theory request lost its non-owned baseline identity")
	}
	if len(raw.Artifacts) != 0 {
		t.Fatal("raw Theory request must not claim private artifacts")
	}
	if len(expanded.Artifacts) != 20 {
		t.Fatalf("expanded inventory has %d artifacts; want 20", len(expanded.Artifacts))
	}
	seen := map[int64]bool{}
	for index, wearer := range expanded.Wearers {
		if wearer.TheoryBaseline != nil || len(wearer.CurrentArtifacts) != 5 || len(wearer.SetRequirements()) != 0 {
			t.Fatalf("expanded wearer %d retained a wire baseline or set package", index)
		}
		for _, assignment := range wearer.CurrentArtifacts {
			if assignment.ArtifactID <= 0 || seen[assignment.ArtifactID] {
				t.Fatalf("private Theory artifact id is invalid or reused: %d", assignment.ArtifactID)
			}
			seen[assignment.ArtifactID] = true
		}
	}
	if err := expanded.ValidateTheory(); err != nil {
		t.Fatalf("expanded Theory request is not valid: %v", err)
	}
	if err := expanded.Validate(); err == nil {
		t.Fatal("ordinary Selected validation accepted a Theory request")
	}
}

func TestDecodeTheoryRequestRejectsNonCanonicalBaseline(t *testing.T) {
	request := neutralTheoryRequest(t)
	request.Wearers[0].TheoryBaseline.MainStats[3].Key = "hydro_dmg_percent"
	payload, err := CanonicalJSON(request)
	if err != nil {
		t.Fatal(err)
	}

	_, _, err = DecodeTheoryRequest(payload)
	if err == nil || !strings.Contains(err.Error(), "canonical baseline") {
		t.Fatalf("non-canonical baseline should fail closed, got %v", err)
	}
}

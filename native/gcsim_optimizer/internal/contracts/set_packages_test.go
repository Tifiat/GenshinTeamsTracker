package contracts

import "testing"

func TestSelectedSetPackageContract(t *testing.T) {
	for _, valid := range []Wearer{
		{SelectedSetUID: "a"},
		{SelectedSets: []SetRequirement{{"a", 4}}},
		{SelectedSets: []SetRequirement{{"a", 2}, {"b", 2}}},
	} {
		if err := validateSetRequirements("wearer", valid); err != nil {
			t.Fatal(err)
		}
	}
	for _, invalid := range []Wearer{
		{}, {SelectedSetUID: "a", SelectedSets: []SetRequirement{{"a", 4}}},
		{SelectedSets: []SetRequirement{{"b", 2}, {"a", 2}}},
		{SelectedSets: []SetRequirement{{"a", 2}, {"a", 2}}},
		{SelectedSets: []SetRequirement{{"a", 3}, {"b", 2}}},
		{SelectedSets: []SetRequirement{{"a", 2}}},
	} {
		if validateSetRequirements("wearer", invalid) == nil {
			t.Fatalf("accepted %+v", invalid)
		}
	}
	request, err := DecodeRequest(readFixture(t, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	request.Wearers[0].SelectedSetUID = ""
	request.Wearers[0].SelectedSets = []SetRequirement{{"a", 2}, {"b", 2}}
	if request.Validate() == nil {
		t.Fatal("legacy policy accepted pair")
	}
	request.Legality.FixedFourPiece = false
	if request.Validate() == nil {
		t.Fatal("missing policy accepted")
	}
	request.Legality.FixedSetPackages = true
	if err := request.Validate(); err != nil {
		t.Fatal(err)
	}
	request.Legality.FixedFourPiece = true
	if request.Validate() == nil {
		t.Fatal("conflicting policies accepted")
	}
}

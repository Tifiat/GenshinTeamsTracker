package theorypackages

import (
	"reflect"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

func TestCatalogRetainsEveryDeclaredBonusAndStableTupleOrder(t *testing.T) {
	rows, err := Packages([]domain.SetCapability{{UID: "b", TwoPiece: true}, {UID: "a", TwoPiece: true, FourPiece: true}})
	if err != nil {
		t.Fatal(err)
	}
	var keys []string
	for _, p := range rows {
		keys = append(keys, p.Key())
	}
	want := []string{"a:2", "a:2+b:2", "a:4", "b:2", "none"}
	if !reflect.DeepEqual(keys, want) {
		t.Fatalf("lost/reordered declared package: got %v want %v", keys, want)
	}
	changed, err := Packages([]domain.SetCapability{{UID: "a", TwoPiece: true, FourPiece: true}, {UID: "b", TwoPiece: true}})
	if err != nil || !reflect.DeepEqual(rows, changed) {
		t.Fatal("catalog input order changed declared package order")
	}
	tuple := [4]domain.Package{rows[4], rows[2], rows[3], rows[1]}
	if got := Key(tuple); got != "none|a:4|b:2|a:2+b:2" {
		t.Fatalf("tuple wearer order or package identity changed: %s", got)
	}
	tuple[1], tuple[2] = tuple[2], tuple[1]
	if Key(tuple) == "none|a:4|b:2|a:2+b:2" {
		t.Fatal("distinct ownership collapsed into an alias key")
	}
}

func TestCatalogRejectsInvalidCapabilitiesAndOwnsReturnedSets(t *testing.T) {
	for _, invalid := range [][]domain.SetCapability{
		{{UID: ""}}, {{UID: "a", FourPiece: true}}, {{UID: "a"}, {UID: "a", TwoPiece: true}},
	} {
		if _, err := Packages(invalid); err == nil {
			t.Fatal("invalid catalog accepted")
		}
	}
	rows, err := Packages([]domain.SetCapability{{UID: "a", TwoPiece: true, FourPiece: true}})
	if err != nil {
		t.Fatal(err)
	}
	rows[0].Sets[0] = contracts.SetRequirement{SetUID: "caller-mutation", Count: 4}
	if rows[1].Sets[0].SetUID != "a" {
		t.Fatal("returned package rows share mutable set slices")
	}
}

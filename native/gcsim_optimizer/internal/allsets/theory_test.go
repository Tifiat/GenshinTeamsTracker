package allsets

import (
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

func TestTheoreticalPackagesIncludeAllModeledFourPieceAndDistinctPairs(t *testing.T) {
	rows, err := theoreticalPackages([]domain.SetCapability{
		{UID: "set_c", TwoPiece: true, FourPiece: true},
		{UID: "set_a", TwoPiece: true, FourPiece: false},
		{UID: "set_b", TwoPiece: true, FourPiece: true},
	})
	if err != nil {
		t.Fatal(err)
	}
	want := []string{
		"set_a:2+set_b:2", "set_a:2+set_c:2", "set_b:2+set_c:2",
		"set_b:4", "set_c:4",
	}
	if len(rows) != len(want) {
		t.Fatalf("%d packages; want %d", len(rows), len(want))
	}
	for i, row := range rows {
		if row.Key() != want[i] {
			t.Fatalf("package %d = %s; want %s", i, row.Key(), want[i])
		}
	}
}

func TestTheoreticalPackagesRejectDuplicateCatalogKeys(t *testing.T) {
	_, err := theoreticalPackages([]domain.SetCapability{
		{UID: "set_a", TwoPiece: true, FourPiece: true},
		{UID: "set_a", TwoPiece: true, FourPiece: true},
	})
	if err == nil {
		t.Fatal("duplicate source catalog must fail closed")
	}
}

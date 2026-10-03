package domain

// Synthetic inventory parity against the existing exact linear matcher.
// Equal/negative weights, missing slots, reservations and exclusions are kept.
import (
	"math"
	"math/rand"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestPackageLinearPlanMatchesIndependentInventoryScans(t *testing.T) {
	rng := rand.New(rand.NewSource(20))
	index := &Index{artifactIndexByID: map[int64]int{}}
	for _, uid := range []string{"a", "b", "c", "d", "e", "f", "g"} {
		for slot := 0; slot < 5; slot++ {
			for copy := 0; copy < 4; copy++ {
				id := int64(len(index.Artifacts) + 1)
				index.artifactIndexByID[id] = len(index.Artifacts)
				index.Artifacts = append(index.Artifacts, IndexedArtifact{ArtifactID: id, SetUID: uid, SlotIndex: slot})
				index.CandidateIDsBySlot[slot] = append(index.CandidateIDsBySlot[slot], id)
			}
		}
	}
	packages := []Package{{}, {Sets: []contracts.SetRequirement{{SetUID: "a", Count: 2}}}, {Sets: []contracts.SetRequirement{{SetUID: "a", Count: 4}}}, {Sets: []contracts.SetRequirement{{SetUID: "a", Count: 2}, {SetUID: "b", Count: 2}}}, {Sets: []contracts.SetRequirement{{SetUID: "absent", Count: 4}}}}
	for trial := 0; trial < 30; trial++ {
		weights, occupied := map[int64]float64{}, map[int64]bool{}
		for _, item := range index.Artifacts {
			weights[item.ArtifactID] = float64(rng.Intn(7) - 3)
			occupied[item.ArtifactID] = rng.Intn(5) == 0
		}
		for _, pack := range packages {
			plan, err := index.PreparePackageLinear(pack, weights, occupied)
			if err != nil {
				t.Fatal(err)
			}
			for probe := 0; probe < 12; probe++ {
				excluded := []int64{}
				used := map[int64]bool{}
				for id, yes := range occupied {
					used[id] = yes
				}
				for n := 0; n < probe; n++ {
					id := int64(rng.Intn(len(index.Artifacts)) + 1)
					excluded = append(excluded, id)
					used[id] = true
				}
				got, score, e := plan.Assignment(excluded...)
				want, value, we := index.PackageLinearAssignment(pack, weights, used)
				if (e == nil) != (we == nil) || e == nil && (got != want || score != value) {
					t.Fatal(trial, pack.Key(), excluded, got, want, score, value, e, we)
				}
			}
		}
	}
	if _, err := index.PreparePackageLinear(Package{}, map[int64]float64{1: math.NaN()}, nil); err == nil {
		t.Fatal("nonfinite priority accepted")
	}
}

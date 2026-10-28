package formula

import (
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// These bounded passing points do NOT accept the separate shared-EM boundary
// retained in known_boundary_checks and the cloud receipt's failing gate.
func TestSourceDerivedContributorResponses(t *testing.T) {
	checkEngineResponseSamples(t, "gob11_cloud_samples_v1.json", 4)
}

func TestContributorDenseAndWearerPaths(t *testing.T) {
	checkContributorDenseAndWearerPaths(t, "gob11_cloud_samples_v1.json")
}

func TestCapturedScalarReactionResponses(t *testing.T) {
	checkEngineResponseSamples(t, "gob11_captured_scalar_samples_v1.json", 6)
	checkContributorDenseAndWearerPaths(t, "gob11_captured_scalar_samples_v1.json")
}

func checkContributorDenseAndWearerPaths(t *testing.T, filename string) {
	t.Helper()
	data, err := os.ReadFile(filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", filename))
	if err != nil {
		t.Fatal(err)
	}
	var fixture struct {
		Samples []struct {
			Case   string
			Member contracts.IRSeedMember
			Checks []struct {
				Deltas   map[string]float64
				Expected string `json:"engine_expected_damage"`
			}
		}
	}
	if err = json.Unmarshal(data, &fixture); err != nil {
		t.Fatal(err)
	}
	for _, sample := range fixture.Samples {
		t.Run(sample.Case, func(t *testing.T) {
			actorSet, coordinateSet := map[string]bool{}, map[string]bool{}
			for _, c := range sample.Member.Channels {
				actorSet[c.ActorKey] = true
			}
			for _, n := range sample.Member.Nodes {
				if n.Coordinate != "" {
					coordinateSet[n.Coordinate] = true
					actorSet[strings.Split(n.Coordinate, ".")[0]] = true
				}
			}
			actors, coords := []string{}, []string{}
			for k := range actorSet {
				actors = append(actors, k)
			}
			sort.Strings(actors)
			for k := range coordinateSet {
				coords = append(coords, k)
			}
			sort.Strings(coords)
			compiled, e := CompileSeedMember(sample.Member, actors, coords)
			if e != nil {
				t.Fatal(e)
			}
			check := func(got float64, err error, want float64) {
				t.Helper()
				if err != nil || math.Abs(got-want) > math.Max(1, math.Abs(want))*1e-10 {
					t.Fatalf("got %g want %g err=%v", got, want, err)
				}
			}
			for _, point := range sample.Checks {
				want, e := strconv.ParseFloat(point.Expected, 64)
				if e != nil {
					t.Fatal(e)
				}
				dense := make([]float64, len(coords))
				owner := ""
				for key, value := range point.Deltas {
					i := sort.SearchStrings(coords, key)
					if i < len(coords) && coords[i] == key {
						dense[i] = value
					}
					owner = strings.Split(key, ".")[0]
				}
				got, e := compiled.EvaluateDamageDense(dense)
				check(got, e, want)
				// Re-establish a complete anchor before the one-wearer hot path. Channel
				// attribution must not hide foreign contributors' dependencies.
				if _, e = compiled.EvaluateDamageDense(make([]float64, len(coords))); e != nil {
					t.Fatal(e)
				}
				a := sort.SearchStrings(actors, owner)
				if a < len(actors) && actors[a] == owner {
					got, e = compiled.EvaluateDamageDenseForActor(dense, a)
					check(got, e, want)
				}
			}
		})
	}
}

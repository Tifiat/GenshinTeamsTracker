package finalists

import (
	"context"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"sync"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

func r2Fixture(t *testing.T, pilot, final []float64, se float64, mutate func(int, int, *engineclient.OrdinaryResult)) (VerificationResult, error, map[[2]int]int, string) {
	t.Helper()
	request := fullBuildRequestFixture(false)
	candidates := make([]search.ScoredAssignment, 9)
	for i := range candidates {
		var a domain.Assignment
		for owner := range a {
			for slot := range a[owner] {
				a[owner][slot] = int64(100 + owner*5 + slot)
			}
		}
		a[0][0] = int64(i + 1)
		candidates[i] = search.ScoredAssignment{Assignment: a, DPS: float64(9000 - i), Source: "r2_fixture"}
	}
	render := func(c search.ScoredAssignment, n, workers int) (RenderedConfig, error) {
		text := fmt.Sprintf("options iteration=%d workers=%d ignore_burst_energy=false;\n# inventory_id=%d\n", n, workers, c.Assignment[0][0])
		return RenderedConfig{Text: text, SHA256: contracts.TextSHA256(text)}, nil
	}
	calls := map[[2]int]int{}
	var mutex sync.Mutex
	runner := func(_ context.Context, _ contracts.OptimizerRequest, text, _ string, n, workers int) (engineclient.OrdinaryResult, error) {
		_, idText, ok := strings.Cut(text, "# inventory_id=")
		if !ok {
			return engineclient.OrdinaryResult{}, fmt.Errorf("identity marker absent")
		}
		id, e := strconv.Atoi(strings.TrimSpace(idText))
		if e != nil {
			return engineclient.OrdinaryResult{}, e
		}
		mutex.Lock()
		calls[[2]int{id, n}]++
		mutex.Unlock()
		dps := pilot[id-1]
		if n == 500 {
			dps = final[id-1]
		}
		row := ordinaryFixtureResult(text, n, dps, 0)
		row.StandardError = se
		row.StandardDeviation = se * math.Sqrt(float64(n))
		if mutate != nil {
			mutate(id, n, &row)
		}
		return row, nil
	}
	root := filepath.Join(t.TempDir(), "staged")
	result, e := verifyStagedWithRunner(context.Background(), request, candidates, render, root, 4, 16, runner)
	return result, e, calls, root
}

func TestR2ClearPilotLeaderAndHonestMixedRows(t *testing.T) {
	p := []float64{1000, 900, 800, 700, 600, 500, 400, 300, 200}
	result, e, calls, _ := r2Fixture(t, p, p, 1, nil)
	if e != nil {
		t.Fatal(e)
	}
	if result.Winner.Iterations != 500 || result.Winner.Assignment[0][0] != 1 || result.Iterations != 0 || result.Staged.IterationPolicy != "per_candidate" {
		t.Fatalf("winner or mixed header: %+v", result)
	}
	for i, row := range result.Candidates {
		want := 100
		if i == 0 {
			want = 500
		}
		if row.Iterations != want {
			t.Fatalf("row %d n=%d", i, row.Iterations)
		}
	}
	if len(calls) != 10 || calls[[2]int{1, 500}] != 1 {
		t.Fatalf("calls %+v", calls)
	}
	for _, n := range calls {
		if n != 1 {
			t.Fatal("same-stage repeat")
		}
	}
}

func TestR2InitialNearTiesAreAllConfirmed(t *testing.T) {
	p := []float64{1000, 995, 800, 700, 600, 500, 400, 300, 200}
	result, e, calls, _ := r2Fixture(t, p, p, 2, nil)
	if e != nil {
		t.Fatal(e)
	}
	if len(calls) != 11 || calls[[2]int{1, 500}] != 1 || calls[[2]int{2, 500}] != 1 || len(result.Staged.Stages) != 2 {
		t.Fatalf("near ties %+v", calls)
	}
}

func TestR2ConfirmationRankReversalPromotesOldPilots(t *testing.T) {
	p := []float64{1000, 900, 850, 700, 600, 500, 400, 300, 200}
	f := []float64{800, 950, 900, 700, 600, 500, 400, 300, 200}
	result, e, calls, _ := r2Fixture(t, p, f, 1, nil)
	if e != nil {
		t.Fatal(e)
	}
	if result.Winner.Assignment[0][0] != 2 || result.Winner.Iterations != 500 || calls[[2]int{2, 500}] != 1 || calls[[2]int{3, 500}] != 1 || len(result.Staged.Stages) != 3 {
		t.Fatalf("reversal %+v calls %+v", result, calls)
	}
}

func TestR2AllCloseIsBoundedAtNineConfirmations(t *testing.T) {
	p := []float64{1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000}
	result, e, calls, _ := r2Fixture(t, p, p, 10, nil)
	if e != nil {
		t.Fatal(e)
	}
	total := 0
	for k, count := range calls {
		if count != 1 {
			t.Fatal("repeated run")
		}
		total += k[1] * count
	}
	if len(calls) != 18 || total != 5400 || result.Winner.Iterations != 500 {
		t.Fatalf("bounded panel calls%d total%d", len(calls), total)
	}
}

func TestR2InvalidMeasurementFailsAndRetainsStageEvidence(t *testing.T) {
	p := []float64{1000, 900, 800, 700, 600, 500, 400, 300, 200}
	for _, kind := range []string{"identity", "nonfinite", "iterations"} {
		t.Run(kind, func(t *testing.T) {
			_, e, calls, root := r2Fixture(t, p, p, 1, func(id, n int, row *engineclient.OrdinaryResult) {
				if id != 1 {
					return
				}
				switch kind {
				case "identity":
					row.ConfigSHA256 = strings.Repeat("e", 64)
				case "nonfinite":
					row.DPS = math.NaN()
				case "iterations":
					row.Iterations = 7
				}
			})
			if e == nil {
				t.Fatal("invalid measurement accepted")
			}
			if _, readErr := os.ReadFile(filepath.Join(root, "verification-stages.json")); readErr != nil {
				t.Fatal("partial stage evidence missing", readErr)
			}
			for key := range calls {
				if key[1] != 100 {
					t.Fatal("invalid pilot triggered confirmation")
				}
			}
		})
	}
}

func TestR2EnergyRejectedPilotLeaderCannotWin(t *testing.T) {
	p := []float64{1000, 900, 800, 700, 600, 500, 400, 300, 200}
	result, e, calls, _ := r2Fixture(t, p, p, 1, func(id, n int, row *engineclient.OrdinaryResult) {
		if id == 1 && n == 500 {
			row.InsufficientEnergyMax = 4
		}
	})
	if e != nil {
		t.Fatal(e)
	}
	if result.Winner.Assignment[0][0] != 2 || result.Winner.Iterations != 500 || len(result.EnergyRejectedSHA256) != 1 || calls[[2]int{2, 500}] != 1 {
		t.Fatalf("energy fallback %+v", result)
	}
}

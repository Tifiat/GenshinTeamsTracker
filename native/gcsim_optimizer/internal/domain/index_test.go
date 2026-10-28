package domain

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestIndexIncumbentAndLegality(t *testing.T) {
	request := requestFixture(t)
	index, err := Build(request, []string{"actor_a.atk_percent", "actor_a.crit_rate", "actor_b.hp_percent"})
	if err != nil {
		t.Fatal(err)
	}
	deltas, err := index.DenseDeltas(index.Incumbent)
	if err != nil {
		t.Fatal(err)
	}
	for _, value := range deltas {
		if value != 0 {
			t.Fatalf("incumbent delta = %v", value)
		}
	}

	duplicate := index.Incumbent
	duplicate[1][0] = duplicate[0][0]
	if err := index.ValidateAssignment(duplicate); err == nil || !strings.Contains(err.Error(), "wrong slot") && !strings.Contains(err.Error(), "more than once") {
		t.Fatalf("duplicate assignment should fail, got %v", err)
	}
	wrongSlot := index.Incumbent
	wrongSlot[0][0] = wrongSlot[0][1]
	if err := index.ValidateAssignment(wrongSlot); err == nil || !strings.Contains(err.Error(), "wrong slot") {
		t.Fatalf("wrong-slot assignment should fail, got %v", err)
	}
}

func requestFixture(t *testing.T) contracts.OptimizerRequest {
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

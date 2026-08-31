package finalists

import "testing"

func TestPlanDynamicWavesUsesTwoFullCPUPartitionsForSevenFinalists(t *testing.T) {
	waves, err := PlanDynamicWaves(7, 4, 16)
	if err != nil {
		t.Fatal(err)
	}
	if len(waves) != 2 {
		t.Fatalf("got %d waves; want 2", len(waves))
	}
	assertWave := func(index, count, workers, parallelism int) {
		t.Helper()
		wave := waves[index]
		if wave.CandidateCount != count || wave.Workers != workers || wave.Parallelism != parallelism {
			t.Fatalf("wave %d = %+v", index+1, wave)
		}
	}
	assertWave(0, 4, 4, 4)
	assertWave(1, 3, 5, 3)
}

func TestPlanDynamicWavesNeverDropsRemainder(t *testing.T) {
	waves, err := PlanDynamicWaves(6, 4, 16)
	if err != nil {
		t.Fatal(err)
	}
	total := 0
	for _, wave := range waves {
		total += wave.CandidateCount
		if wave.Workers*wave.Parallelism > 16 {
			t.Fatalf("wave exceeds CPU budget: %+v", wave)
		}
	}
	if total != 6 {
		t.Fatalf("planned %d candidates; want 6", total)
	}
}

func TestPlanDynamicWavesRejectsInvalidBoundary(t *testing.T) {
	for _, input := range [][3]int{{0, 4, 16}, {7, 0, 16}, {7, 4, 0}} {
		if _, err := PlanDynamicWaves(input[0], input[1], input[2]); err == nil {
			t.Fatalf("input %v unexpectedly passed", input)
		}
	}
}

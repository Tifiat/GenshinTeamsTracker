package projectionmetrics

import (
	"fmt"
	"reflect"
	"sync"
	"testing"
)

func TestR4CounterTotalsConcurrentAndRunBoundaries(t *testing.T) {
	old := r4FastCounters
	r4FastCounters = true
	defer func() { r4FastCounters = old; Finish() }()
	StartCounters()
	var wg sync.WaitGroup
	for worker := 0; worker < 8; worker++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < 10000; i++ {
				Count("artifact.evaluate_calls", 1)
				Count("artifact.gradient_calls", 3)
				Count("ordinary", 1)
			}
		}()
	}
	wg.Wait()
	r := Finish()
	if !reflect.DeepEqual(r.Counts, map[string]uint64{"artifact.evaluate_calls": 80000, "artifact.gradient_calls": 240000, "ordinary": 80000}) {
		t.Fatal("concurrent exact totals differ", r.Counts)
	}
	oldTimer := func() func() { StartCounters(); return Begin("old") }()
	Finish()
	StartCounters()
	oldTimer()
	Count("artifact.evaluate_calls", 0)
	Count("artifact.gradient_calls", ^uint64(0))
	Count("artifact.gradient_calls", 1)
	next := Finish()
	if len(next.Phases) != 0 || next.Counts["artifact.gradient_calls"] != 0 || len(next.Counts) != 2 {
		t.Fatal("run epochs/zero/wrap changed", next)
	}
	Count("artifact.evaluate_calls", 10)
	if !reflect.DeepEqual(Finish(), next) {
		t.Fatal("disabled counter changed finished report")
	}
}

func TestR4CounterCapacityMatchesFrozen(t *testing.T) {
	old := r4FastCounters
	r4FastCounters = true
	defer func() { r4FastCounters = old; Finish() }()
	for _, fixedFirst := range []bool{false, true} {
		StartCounters()
		r4ReferenceStartCounters()
		count := func(name string, n uint64) { Count(name, n); r4ReferenceCount(name, n) }
		if fixedFirst {
			count("artifact.evaluate_calls", 1)
		}
		for i := 0; i < 256; i++ {
			count(fmt.Sprintf("name%d", i), 1)
		}
		count("artifact.evaluate_calls", 5)
		count("artifact.gradient_calls", 2)
		count("name0", 2)
		got, want := Finish(), r4ReferenceFinish()
		if len(got.Counts) != 256 || !reflect.DeepEqual(got.Counts, want.Counts) {
			t.Fatal("original bounded counter behavior changed", fixedFirst, len(got.Counts), len(want.Counts))
		}
	}
}

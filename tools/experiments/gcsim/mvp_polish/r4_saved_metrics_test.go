package projectionmetrics

import (
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"
	"time"
)

func TestR4SavedCounterCosts(t *testing.T) {
	root := os.Getenv("GTT_R4_SAVED_INPUTS")
	if root == "" {
		t.Skip("finite measured-call gate only")
	}
	previous := r4FastCounters
	r4FastCounters = true
	defer func() { r4FastCounters = previous; Finish() }()
	var rows []map[string]any
	for _, enabled := range []bool{false, true} {
		for _, fast := range []bool{false, true} {
			if enabled {
				if fast {
					StartCounters()
				} else {
					r4ReferenceStartCounters()
				}
			}
			count := Count
			if !fast {
				count = r4ReferenceCount
			}
			runtime.GC()
			var before, after runtime.MemStats
			runtime.ReadMemStats(&before)
			start := time.Now()
			for i := 0; i < 366624; i++ {
				count("artifact.evaluate_calls", 1)
			}
			for i := 0; i < 8982; i++ {
				count("artifact.gradient_calls", 1)
			}
			wall := time.Since(start)
			runtime.ReadMemStats(&after)
			report := Report{}
			if fast {
				report = Finish()
			} else {
				report = r4ReferenceFinish()
			}
			if enabled && !reflect.DeepEqual(report.Counts, map[string]uint64{"artifact.evaluate_calls": 366624, "artifact.gradient_calls": 8982}) {
				t.Fatal("measured exact totals changed", report.Counts)
			}
			rows = append(rows, map[string]any{"enabled": enabled, "fast": fast, "count_calls": 375606, "wall_ms": float64(wall) / float64(time.Millisecond), "alloc_bytes": after.TotalAlloc - before.TotalAlloc, "allocations": after.Mallocs - before.Mallocs, "counts": report.Counts, "scope": "exact R3 measured arithmetic-call counts, single sequential caller; includes first registration if enabled"})
		}
	}
	data, e := json.MarshalIndent(rows, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(root, "r4-counter-costs.json"), data, 0600); e != nil {
		t.Fatal(e)
	}
}

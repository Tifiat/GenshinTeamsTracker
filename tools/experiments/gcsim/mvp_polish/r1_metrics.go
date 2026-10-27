package projectionmetrics

// Finite wall/count telemetry for the single-neutral experiment. These are
// inclusive wall phases; no CPU, heap, allocation or value snapshots are taken.
import (
	"sync"
	"time"
)

type Phase struct{ Calls, WallNS, CPUNS, AllocBytes, Allocations, GCs uint64 }
type Report struct {
	Mode                   string
	Counts                 map[string]uint64
	Phases                 map[string]Phase
	CPUAvailable           bool
	SnapshotWallNS         uint64
	ProjectionValueWitness string
	Contract               string
}

var mu sync.Mutex
var enabled bool
var current Report

func StartCounters() {
	mu.Lock()
	defer mu.Unlock()
	enabled = true
	current = Report{Mode: "wall_and_counts", Counts: map[string]uint64{}, Phases: map[string]Phase{}, Contract: "R1 inclusive wall/count phases; nested times overlap. No CPU/ReadMemStats/value witness. Counter/timer overhead included. Baseline capture process/decode timers remain disjoint per member."}
}
func Count(name string, n uint64) {
	mu.Lock()
	defer mu.Unlock()
	if enabled && len(current.Counts) < 256 {
		current.Counts[name] += n
	}
}
func Begin(name string) func() {
	mu.Lock()
	active := enabled
	mu.Unlock()
	if !active {
		return func() {}
	}
	started := time.Now()
	return func() {
		mu.Lock()
		defer mu.Unlock()
		if len(current.Phases) >= 64 {
			return
		}
		p := current.Phases[name]
		p.Calls++
		p.WallNS += uint64(time.Since(started))
		current.Phases[name] = p
	}
}
func Finish() Report { mu.Lock(); defer mu.Unlock(); enabled = false; return current }

package projectionmetrics

// Same bounded wall/count report; hot arithmetic counters use two fixed atomic
// slots in the current run. Rare names/phases retain their mutex protection.
import (
	"os"
	"sync"
	"sync/atomic"
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

type counterRun struct {
	report                     Report
	evaluate, gradient         atomic.Uint64
	evaluateSeen, gradientSeen atomic.Bool
	full                       atomic.Bool
	fast                       bool
}

var mu sync.Mutex
var active atomic.Pointer[counterRun]
var current Report
var r4FastCounters = os.Getenv("GTT_R4_FAST_COUNTERS") == "1"

func StartCounters() {
	mu.Lock()
	defer mu.Unlock()
	r := &counterRun{fast: r4FastCounters, report: Report{Mode: "wall_and_counts", Counts: map[string]uint64{}, Phases: map[string]Phase{},
		Contract: "R1 inclusive wall/count phases; nested times overlap. No CPU/ReadMemStats/value witness. Counter/timer overhead included. Baseline capture process/decode timers remain disjoint per member."}}
	active.Store(r)
}

func Count(name string, n uint64) {
	r := active.Load()
	if r == nil {
		return
	}
	if r.fast {
		switch name {
		case "artifact.evaluate_calls":
			countFixed(r, name, n, &r.evaluate, &r.evaluateSeen)
			return
		case "artifact.gradient_calls":
			countFixed(r, name, n, &r.gradient, &r.gradientSeen)
			return
		}
	}
	mu.Lock()
	defer mu.Unlock()
	if active.Load() == r && len(r.report.Counts) < 256 {
		r.report.Counts[name] += n
		if len(r.report.Counts) == 256 {
			r.full.Store(true)
		}
	}
}

func countFixed(r *counterRun, name string, n uint64, value *atomic.Uint64, ready *atomic.Bool) {
	if ready.Load() {
		if !r.full.Load() {
			value.Add(n)
		}
		return
	}
	mu.Lock()
	defer mu.Unlock()
	if active.Load() != r || len(r.report.Counts) >= 256 {
		return
	}
	// Register each fixed name once. Zero increments and uint64 wrap retain
	// the same key and the original256-name saturation behavior.
	r.report.Counts[name] = 0
	value.Add(n)
	ready.Store(true)
	if len(r.report.Counts) == 256 {
		r.full.Store(true)
	}
}

func Begin(name string) func() {
	r := active.Load()
	if r == nil {
		return func() {}
	}
	started := time.Now()
	return func() {
		mu.Lock()
		defer mu.Unlock()
		if active.Load() != r || len(r.report.Phases) >= 64 {
			return
		}
		p := r.report.Phases[name]
		p.Calls++
		p.WallNS += uint64(time.Since(started))
		r.report.Phases[name] = p
	}
}

// The stage owner joins producers before Finish, as before. A call overlapping
// Finish can only affect its captured old run, never a new run's counters/maps.
func Finish() Report {
	mu.Lock()
	defer mu.Unlock()
	r := active.Swap(nil)
	if r == nil {
		return current
	}
	if r.evaluateSeen.Load() {
		r.report.Counts["artifact.evaluate_calls"] = r.evaluate.Load()
	}
	if r.gradientSeen.Load() {
		r.report.Counts["artifact.gradient_calls"] = r.gradient.Load()
	}
	current = r.report
	return current
}

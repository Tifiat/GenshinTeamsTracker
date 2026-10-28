package formula

import (
	"encoding/json"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"testing"
	"time"
)

func r5Cost(t *testing.T, work func()) map[string]any {
	t.Helper()
	runtime.GC()
	var before, after runtime.MemStats
	runtime.ReadMemStats(&before)
	start := time.Now()
	work()
	elapsed := time.Since(start)
	runtime.ReadMemStats(&after)
	return map[string]any{"wall_ms": float64(elapsed) / float64(time.Millisecond),
		"allocated_bytes": after.TotalAlloc - before.TotalAlloc, "allocations": after.Mallocs - before.Mallocs,
		"cpu_available": false}
}

func TestR5SavedEvaluateAndScratchCosts(t *testing.T) {
	root := os.Getenv("GTT_R5_SAVED_INPUTS")
	if root == "" {
		t.Skip("owned retained-input gate only")
	}
	var rows []map[string]any
	for _, seed := range []string{"742031889", "742031890"} {
		data, err := os.ReadFile(filepath.Join(root, seed, "member.json"))
		if err != nil {
			t.Fatal(err)
		}
		member, err := contracts.DecodeSeedMember(data)
		if err != nil {
			t.Fatal(err)
		}
		actors, coords := map[string]bool{}, map[string]bool{}
		for _, c := range member.Channels {
			actors[c.ActorKey] = true
		}
		for _, n := range member.Nodes {
			if n.Operation == "artifact_stat" {
				coords[n.Coordinate] = true
			}
		}
		actorKeys, coordinates := []string{}, []string{}
		for key := range actors {
			actorKeys = append(actorKeys, key)
		}
		sort.Strings(actorKeys)
		for key := range coords {
			coordinates = append(coordinates, key)
		}
		sort.Strings(coordinates)
		compiled, err := CompileSeedMember(member, actorKeys, coordinates)
		if err != nil {
			t.Fatal(err)
		}
		prepared, err := PrepareParametric([]*CompiledMember{compiled}, nil)
		if err != nil {
			t.Fatal(err)
		}
		local, err := prepared.Specialize(make([]float64, len(coordinates)), nil, 0)
		if err != nil {
			t.Fatal(err)
		}
		const calls = 2048
		vectors := make([][]float64, calls)
		for i := range vectors {
			vectors[i] = make([]float64, len(local.coordinates))
			for j := range vectors[i] {
				vectors[i][j] = float64((i/4+j)%3) * .01
			}
		}
		reference := make([]uint64, calls)
		p := copyArtifactScratch(local)
		before := r5Cost(t, func() {
			for i, x := range vectors {
				value, e := p.evaluateR4Legacy(x)
				if e != nil {
					t.Fatal(e)
				}
				reference[i] = math.Float64bits(value)
			}
		})
		p = copyArtifactScratch(local)
		after := r5Cost(t, func() {
			for i, x := range vectors {
				value, e := p.Evaluate(x)
				if e != nil || math.Float64bits(value) != reference[i] {
					t.Fatal("saved evaluate bit parity", i, e)
				}
			}
		})
		cache := NewSpecializationCache(16, 1000000)
		const views = 64
		var view *ParametricProgram
		oldView := r5Cost(t, func() {
			for i := 0; i < views; i++ {
				view = prepared.WithSpecializationCache(cache).WithoutPruning()
			}
		})
		runtime.KeepAlive(view)
		newView := r5Cost(t, func() {
			for i := 0; i < views; i++ {
				view = prepared.WithSearchScratch(cache, true)
			}
		})
		if !view.program.unresolved || view.specializations != cache {
			t.Fatal("view settings lost")
		}
		runtime.KeepAlive(view)
		rows = append(rows, map[string]any{"seed": seed, "evaluate_calls_per_arm": calls,
			"specialized_coordinates": len(local.coordinates), "specialized_nodes": local.NodeCount(),
			"evaluate_R4": before, "evaluate_R5": after, "all_value_bits_equal": true,
			"scratch_views_per_arm": views, "scratch_R4_two_copies": oldView, "scratch_R5_one_copy": newView,
			"scope": "Historical retained capture, not the R4 neutral graph. Copy constructor only; zero-preflight remains and was checked separately. One sample each, no full-run speed claim."})
	}
	raw, err := json.MarshalIndent(rows, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(root, "r5-evaluate-view-costs.json"), append(raw, '\n'), 0600); err != nil {
		t.Fatal(err)
	}
}

func TestR5SavedEvaluateConfirmation(t *testing.T) {
	root := os.Getenv("GTT_R5_SAVED_INPUTS")
	if root == "" {
		t.Skip("one specifically admitted retained-input confirmation")
	}
	var rows []map[string]any
	for fixture, seed := range []string{"742031889", "742031890"} {
		data, err := os.ReadFile(filepath.Join(root, seed, "member.json"))
		if err != nil {
			t.Fatal(err)
		}
		member, err := contracts.DecodeSeedMember(data)
		if err != nil {
			t.Fatal(err)
		}
		actorSet, coordinateSet := map[string]bool{}, map[string]bool{}
		for _, c := range member.Channels {
			actorSet[c.ActorKey] = true
		}
		for _, n := range member.Nodes {
			if n.Operation == "artifact_stat" {
				coordinateSet[n.Coordinate] = true
			}
		}
		actors, coordinates := []string{}, []string{}
		for k := range actorSet {
			actors = append(actors, k)
		}
		sort.Strings(actors)
		for k := range coordinateSet {
			coordinates = append(coordinates, k)
		}
		sort.Strings(coordinates)
		compiled, err := CompileSeedMember(member, actors, coordinates)
		if err != nil {
			t.Fatal(err)
		}
		prepared, err := PrepareParametric([]*CompiledMember{compiled}, nil)
		if err != nil {
			t.Fatal(err)
		}
		local, err := prepared.Specialize(make([]float64, len(coordinates)), nil, 0)
		if err != nil {
			t.Fatal(err)
		}
		const width = 2048
		vectors := make([][]float64, width)
		bits := make([]uint64, width)
		oracle := copyArtifactScratch(local)
		for i := range vectors {
			vectors[i] = make([]float64, len(local.coordinates))
			for j := range vectors[i] {
				vectors[i][j] = float64((i/4+j)%3) * .01
			}
			v, e := oracle.evaluateR4Legacy(vectors[i])
			if e != nil {
				t.Fatal(e)
			}
			bits[i] = math.Float64bits(v)
		}
		order := []bool{false, true}
		if fixture == 1 {
			order = []bool{true, false}
		}
		for _, fused := range order {
			p := copyArtifactScratch(local)
			evaluate := p.evaluateR4Legacy
			if fused {
				evaluate = p.Evaluate
			}
			for _, x := range vectors {
				if _, e := evaluate(x); e != nil {
					t.Fatal(e)
				}
			}
			const calls = 1048576
			cost := r5Cost(t, func() {
				for i := 0; i < calls; i++ {
					index := i & (width - 1)
					value, e := evaluate(vectors[index])
					if e != nil || math.Float64bits(value) != bits[index] {
						t.Fatal("confirmation parity", i, e)
					}
				}
			})
			cost["seed"], cost["fused"], cost["calls"] = seed, fused, calls
			cost["order"] = order
			rows = append(rows, cost)
		}
	}
	raw, err := json.MarshalIndent(map[string]any{"rows": rows, "scope": "One ROOT-admitted clarification; equal bit-comparison work in both arms, reversed fixture order. Same retained data, no engine/search, no further repeats."}, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(root, "r5-evaluate-confirm-costs.json"), append(raw, '\n'), 0600); err != nil {
		t.Fatal(err)
	}
}

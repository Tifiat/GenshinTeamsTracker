package formula

import (
	"encoding/json"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"sort"
	"strconv"
	"testing"
	"time"
)

func TestR4SavedRegionCosts(t *testing.T) {
	root := os.Getenv("GTT_R4_SAVED_INPUTS")
	if root == "" {
		t.Skip("owned real-input measurement only")
	}
	previous := r4DirtyRegions
	defer func() { r4DirtyRegions = previous }()
	var rows []map[string]any
	for _, seed := range []string{"742031889", "742031890"} {
		raw, e := os.ReadFile(filepath.Join(root, seed, "member.json"))
		if e != nil {
			t.Fatal(e)
		}
		member, e := contracts.DecodeSeedMember(raw)
		if e != nil {
			t.Fatal(e)
		}
		sideRaw, e := os.ReadFile(filepath.Join(root, seed, "member.json.effects.json"))
		if e != nil {
			t.Fatal(e)
		}
		var side contracts.EffectInputsOutput
		if e = json.Unmarshal(sideRaw, &side); e != nil {
			t.Fatal(e)
		}
		coordinateSet := map[string]bool{}
		for _, n := range member.Nodes {
			if n.Operation == "artifact_stat" {
				coordinateSet[n.Coordinate] = true
			}
		}
		coordinates := []string{}
		for s := range coordinateSet {
			coordinates = append(coordinates, s)
		}
		sort.Strings(coordinates)
		actors := append([]string(nil), side.CharacterKeys...)
		sort.Strings(actors)
		compiled, e := CompileSeedMember(member, actors, coordinates)
		if e != nil {
			t.Fatal(e)
		}
		ports := []EffectPort{}
		seen := map[uint32]bool{}
		add := func(id uint32, value string) {
			if seen[id] {
				return
			}
			v, err := strconv.ParseFloat(value, 64)
			if err != nil {
				t.Fatal(err)
			}
			seen[id] = true
			ports = append(ports, EffectPort{Member: 0, NodeID: id, Key: strconv.FormatUint(uint64(id), 10), Observed: v})
		}
		for _, in := range side.EffectInputs {
			add(in.NodeID, in.Observed)
		}
		for _, in := range side.ResistanceInputs {
			add(in.NodeID, in.Observed)
		}
		prepared, e := PrepareParametric([]*CompiledMember{compiled}, ports)
		if e != nil {
			t.Fatal(e)
		}
		vectors := make([][]float64, 64)
		for step := range vectors {
			vector := make([]float64, len(ports))
			if step > 0 {
				copy(vector, vectors[step-1])
			}
			switch step % 4 {
			case 1:
				vector[step%len(vector)] += 0.001
			case 2:
				vector[(step+7)%len(vector)] += 0.002
			case 3:
				for i := range vector {
					vector[i] = float64((step+i)%5) * 0.001
				}
			}
			vectors[step] = vector
		}
		var expected []*ParametricProgram
		var expectedBits []uint64
		for _, dirty := range []bool{false, true} {
			r4DirtyRegions = dirty
			p := prepared.ForkTheory()
			runtime.GC()
			var before, after runtime.MemStats
			runtime.ReadMemStats(&before)
			start := time.Now()
			results := make([]*ParametricProgram, 0, len(vectors))
			for _, vector := range vectors {
				bound, err := p.BindConstantEffectsRegions(vector)
				if err != nil {
					t.Fatal(err)
				}
				results = append(results, bound)
			}
			wall := time.Since(start)
			runtime.ReadMemStats(&after)
			if !dirty {
				expected = results
				expectedBits = make([]uint64, len(results))
			}
			for i, result := range results {
				value, err := result.Evaluate(make([]float64, len(coordinates)), nil)
				if err != nil {
					t.Fatal(err)
				}
				if !dirty {
					expectedBits[i] = math.Float64bits(value)
				} else if math.Float64bits(value) != expectedBits[i] || !reflect.DeepEqual(result.program.nodes, expected[i].program.nodes) || result.program.root != expected[i].program.root {
					t.Fatal("saved region graph/value parity differs", i)
				}
			}
			indexBytes := 0
			if d := p.regions.r4Dirty; d != nil {
				indexBytes = 4*(len(d.usersStart)+len(d.effectsStart)+len(d.users)+len(d.effectRoots)+len(d.marked)+cap(d.pending)) + 8*len(d.rank)
			}
			rows = append(rows, map[string]any{"seed": seed, "dirty": dirty, "calls": len(vectors), "ports": len(ports), "source_nodes": len(prepared.program.nodes), "damage_nodes": len(prepared.damageOrder), "wall_ms": float64(wall) / float64(time.Millisecond), "alloc_bytes": after.TotalAlloc - before.TotalAlloc, "allocations": after.Mallocs - before.Mallocs, "gc_cycles": after.NumGC - before.NumGC, "stats": p.RegionBindingStats(), "dirty_index_bytes": indexBytes, "scope": "historical single-seed actual graph with observed effect/resistance ports;64 fixed unchanged/disjoint/dense vectors, not the complete R3 neutral graph"})
		}
	}
	data, e := json.MarshalIndent(rows, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(root, "r4-region-costs.json"), data, 0600); e != nil {
		t.Fatal(e)
	}
}

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

func TestR3SavedGradientCosts(t *testing.T) {
	root := os.Getenv("GTT_R3_SAVED_INPUTS")
	if root == "" {
		t.Skip("owned saved-data gate only")
	}
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
		for key := range actorSet {
			actors = append(actors, key)
		}
		sort.Strings(actors)
		for key := range coordinateSet {
			coordinates = append(coordinates, key)
		}
		sort.Strings(coordinates)
		compiled, e := CompileSeedMember(member, actors, coordinates)
		if e != nil {
			t.Fatal(e)
		}
		prepared, e := SpecializeArtifacts([]*CompiledMember{compiled}, make([]float64, len(coordinates)), 0)
		if e != nil {
			t.Fatal(e)
		}
		var control uint64
		for _, reuse := range []bool{false, true} {
			setting := "0"
			if reuse {
				setting = "1"
			}
			t.Setenv("GTT_R3_ADJOINT_REUSE", setting)
			p := copyArtifactScratch(prepared)
			delta := make([]float64, len(p.coordinates))
			runtime.GC()
			var coldBefore, coldAfter, before, after, retained runtime.MemStats
			runtime.ReadMemStats(&coldBefore)
			if _, _, _, e = p.ValueGradient(delta); e != nil {
				t.Fatal(e)
			}
			runtime.ReadMemStats(&coldAfter)
			runtime.GC()
			runtime.ReadMemStats(&before)
			start := time.Now()
			sum := 0.0
			for i := 0; i < 32; i++ {
				if len(delta) > 0 {
					delta[0] = float64(i % 3)
				}
				value, g, _, err := p.ValueGradient(delta)
				if err != nil {
					t.Fatal(err)
				}
				sum += value
				for _, v := range g {
					sum += v
				}
			}
			wall := time.Since(start)
			runtime.ReadMemStats(&after)
			bits := math.Float64bits(sum)
			if !reuse {
				control = bits
			} else if bits != control {
				t.Fatal("saved gradient bit parity failed")
			}
			runtime.GC()
			runtime.ReadMemStats(&retained)
			runtime.KeepAlive(p)
			rows = append(rows, map[string]any{"seed": seed, "reuse": reuse, "calls": 32, "nodes": p.NodeCount(),
				"wall_ms": float64(wall) / float64(time.Millisecond), "first_call_alloc_bytes": coldAfter.TotalAlloc - coldBefore.TotalAlloc,
				"alloc_bytes": after.TotalAlloc - before.TotalAlloc, "allocations": after.Mallocs - before.Mallocs,
				"retained_delta_bytes": int64(retained.HeapAlloc) - int64(coldBefore.HeapAlloc), "adjoint_bytes": len(p.r3Adjoints) * 8, "score_bits": bits,
				"actor": actors[0], "scope": "historical single-member zero-effect specialization; not the R2 neutral graph/search"})
		}
	}
	raw, e := json.MarshalIndent(rows, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(root, "gradient-costs.json"), raw, 0600); e != nil {
		t.Fatal(e)
	}
}

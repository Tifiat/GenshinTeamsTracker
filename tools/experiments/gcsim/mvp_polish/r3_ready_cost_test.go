package engineclient

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"runtime/pprof"
	"sort"
	"testing"
	"time"
)

func TestR3SavedReadyCosts(t *testing.T) {
	root := os.Getenv("GTT_R3_SAVED_INPUTS")
	if root == "" {
		t.Skip("owned saved-data gate only")
	}
	corrective := os.Getenv("GTT_R3_READY_CORRECTIVE") == "1"
	if !corrective {
		profile, e := os.Create(filepath.Join(root, "ready-cpu.pprof"))
		if e != nil {
			t.Fatal(e)
		}
		if e = pprof.StartCPUProfile(profile); e != nil {
			t.Fatal(e)
		}
		defer func() { pprof.StopCPUProfile(); profile.Close() }()
	}
	var rows []map[string]any
	for index, seed := range []string{"742031889", "742031890"} {
		var pin struct {
			Source  string `json:"source"`
			Config  string `json:"config"`
			Member  string `json:"member"`
			Sidecar string `json:"sidecar"`
		}
		data, e := os.ReadFile(filepath.Join(root, seed, "pins.json"))
		if e != nil || json.Unmarshal(data, &pin) != nil {
			t.Fatal("fixture pins missing")
		}
		var firstBits []uint64
		order := []bool{false, true}
		if index == 1 {
			order = []bool{true, false}
		}
		if corrective {
			order = []bool{false, true, true, false}
		}
		for arm, typed := range order {
			setting := "0"
			if typed {
				setting = "1"
			}
			t.Setenv("GTT_R3_TYPED_CANONICAL", setting)
			runtime.GC()
			var before, after, retained runtime.MemStats
			runtime.ReadMemStats(&before)
			row := map[string]any{"seed": seed, "typed": typed, "arm": arm,
				"cpu_profile_enabled": !corrective, "gomaxprocs": runtime.GOMAXPROCS(0),
				"logical_cpus": runtime.NumCPU(), "goroutines_before": runtime.NumGoroutine()}
			cpuBefore, cpuAvailable := r3ProcessCPU()
			start := time.Now()
			mark := start
			step := func(name string) {
				now := time.Now()
				row[name] = float64(now.Sub(mark)) / float64(time.Millisecond)
				mark = now
			}
			raw, e := os.ReadFile(filepath.Join(root, seed, "member.json"))
			if e != nil {
				t.Fatal(e)
			}
			step("member_read_ms")
			member, e := contracts.DecodeSeedMember(raw)
			if e != nil {
				t.Fatal(e)
			}
			step("member_decode_validate_ms")
			sideRaw, e := os.ReadFile(filepath.Join(root, seed, "member.json.effects.json"))
			if e != nil {
				t.Fatal(e)
			}
			step("sidecar_read_ms")
			effects, e := decodeEffectInputs(sideRaw, raw, member, pin.Config, pin.Source)
			if e != nil {
				t.Fatal(e)
			}
			step("sidecar_decode_validate_ms")
			digest := sha256.Sum256(raw)
			if hex.EncodeToString(digest[:]) != pin.Member {
				t.Fatal("saved payload content drift")
			}
			step("raw_identity_ms")
			coordinateSet := map[string]bool{}
			for _, node := range member.Nodes {
				if node.Operation == "artifact_stat" {
					coordinateSet[node.Coordinate] = true
				}
			}
			coordinates := make([]string, 0, len(coordinateSet))
			for key := range coordinateSet {
				coordinates = append(coordinates, key)
			}
			sort.Strings(coordinates)
			compiled, e := formula.CompileSeedMember(member, effects.CharacterKeys, coordinates)
			if e != nil {
				t.Fatal(e)
			}
			step("compile_graph_ms")
			row["ready_total_ms"] = float64(time.Since(start)) / float64(time.Millisecond)
			cpuAfter, cpuAfterAvailable := r3ProcessCPU()
			runtime.ReadMemStats(&after)
			row["cpu_available"] = cpuAvailable && cpuAfterAvailable
			if cpuAvailable && cpuAfterAvailable {
				row["process_cpu_ms"] = float64(cpuAfter-cpuBefore) / float64(time.Millisecond)
			}
			row["gc_cycles"] = after.NumGC - before.NumGC
			row["gc_pause_ms"] = float64(after.PauseTotalNs-before.PauseTotalNs) / float64(time.Millisecond)
			row["goroutines_after"] = runtime.NumGoroutine()
			row["read_ms"] = row["member_read_ms"].(float64) + row["sidecar_read_ms"].(float64)
			// Fixture-only sidecar digest is outside ready wall/alloc/CPU. The
			// actual product member digest and sidecar binding stay inside.
			diagnosticStart := time.Now()
			sideDigest := sha256.Sum256(sideRaw)
			if hex.EncodeToString(sideDigest[:]) != pin.Sidecar {
				t.Fatal("saved sidecar drift")
			}
			row["diagnostic_sidecar_hash_ms"] = float64(time.Since(diagnosticStart)) / float64(time.Millisecond)
			score, e := compiled.EvaluateDense(make([]float64, len(coordinates)))
			if e != nil {
				t.Fatal(e)
			}
			bits := []uint64{math.Float64bits(score.Damage)}
			for _, v := range score.ByActor {
				bits = append(bits, math.Float64bits(v))
			}
			if firstBits == nil {
				firstBits = bits
			} else {
				for i := range bits {
					if bits[i] != firstBits[i] {
						t.Fatal("compiled ready graph value parity failed")
					}
				}
			}
			raw = nil
			sideRaw = nil
			runtime.GC()
			runtime.ReadMemStats(&retained)
			runtime.KeepAlive(member)
			runtime.KeepAlive(effects)
			runtime.KeepAlive(compiled)
			row["alloc_bytes"] = after.TotalAlloc - before.TotalAlloc
			row["allocations"] = after.Mallocs - before.Mallocs
			row["heap_after_work_bytes"] = after.HeapAlloc
			row["retained_ready_delta_bytes"] = int64(retained.HeapAlloc) - int64(before.HeapAlloc)
			row["baseline_score_bits"] = bits
			row["nodes"] = len(member.Nodes)
			rows = append(rows, row)
		}
	}
	raw, e := json.MarshalIndent(rows, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(root, "ready-costs.json"), raw, 0600); e != nil {
		t.Fatal(e)
	}
	if corrective {
		return
	}
	runtime.GC()
	allocation, e := os.Create(filepath.Join(root, "ready-allocs.pprof"))
	if e != nil {
		t.Fatal(e)
	}
	if e = pprof.Lookup("allocs").WriteTo(allocation, 0); e != nil {
		allocation.Close()
		t.Fatal(e)
	}
	allocation.Close()
}

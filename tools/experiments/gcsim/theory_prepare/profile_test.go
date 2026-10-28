package setcontext

import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"runtime"
	"sort"
	"strconv"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

// This synthetic graph measures port/key work and region binding separately.
// It is not a replay of an unavailable saved production DAG or an engine test.
func researchPrepareModel(t *testing.T, count int) *NeutralModel {
	t.Helper()
	base := fixtureContext(t)
	capture := syntheticCapture(base, "100")
	ports := []formula.EffectPort{}
	for member := range capture.Members {
		nodes := []contracts.IRNode{
			{NodeID: 1, Operation: "constant", Value: "100", Inputs: []contracts.IRInput{}},
			{NodeID: 2, Operation: "artifact_stat", Coordinate: "actor_a.em", Inputs: []contracts.IRInput{}},
			{NodeID: 3, Operation: "add", Inputs: []contracts.IRInput{{NodeID: 1, Relation: "base"}, {NodeID: 2, Relation: "delta"}}},
		}
		roots := make([]uint32, count)
		for i := 0; i < count; i++ {
			id := uint32(len(nodes) + 1)
			nodes = append(nodes,
				contracts.IRNode{NodeID: id, Operation: "constant", Value: "1", Inputs: []contracts.IRInput{}},
				contracts.IRNode{NodeID: id + 1, Operation: "multiply", Inputs: []contracts.IRInput{{NodeID: id, Relation: "scale"}, {NodeID: 3, Relation: "damage"}}})
			roots[i] = id + 1
			ports = append(ports, formula.EffectPort{Member: member, NodeID: id, Key: fmt.Sprintf("effect/%05d", i), Observed: 1})
		}
		for len(roots) > 1 {
			next := []uint32{}
			for i := 0; i < len(roots); i += 2 {
				if i+1 == len(roots) {
					next = append(next, roots[i])
					continue
				}
				id := uint32(len(nodes) + 1)
				nodes = append(nodes, contracts.IRNode{NodeID: id, Operation: "add", Inputs: []contracts.IRInput{{NodeID: roots[i], Relation: "left"}, {NodeID: roots[i+1], Relation: "right"}}})
				next = append(next, id)
			}
			roots = next
		}
		for i := range nodes {
			sort.Slice(nodes[i].Inputs, func(a, b int) bool {
				return nodes[i].Inputs[a].NodeID < nodes[i].Inputs[b].NodeID
			})
		}
		capture.Members[member].Nodes = nodes
		capture.Members[member].Channels[0].RootNodeID = roots[0]
		capture.Members[member].Channels[0].BaselineDamage = strconv.Itoa(100 * count)
	}
	compiled, err := compileCapture(base, capture)
	if err != nil {
		t.Fatal(err)
	}
	prepared, err := compiled.panel.PrepareEffectInputs(ports)
	if err != nil {
		t.Fatal(err)
	}
	m := &NeutralModel{prepared: prepared}
	m.prepareEffectKeys()
	if len(m.effectKeys) != count || len(m.constantKeys) != count {
		t.Fatal("synthetic port coverage differs", len(m.effectKeys), len(m.constantKeys), count)
	}
	for i := range m.effectKeys {
		m.effectDimensions = append(m.effectDimensions, i)
		m.constantDimensions = append(m.constantDimensions, i)
	}
	return m
}

func researchPrepareRecord(t *testing.T, row map[string]any) {
	t.Helper()
	data, err := json.Marshal(row)
	if err != nil {
		t.Fatal(err)
	}
	fmt.Println("PREP_RECEIPT " + string(data))
}

func TestPrepareBindCostProfile(t *testing.T) {
	deadline := time.Now().Add(60 * time.Second)
	for _, count := range []int{11651, 15345} {
		for _, variant := range []string{"OLD", "CHUNKED"} {
			created := time.Now()
			m := researchPrepareModel(t, count)
			m.researchChunked = variant == "CHUNKED"
			values := make([]float64, count)
			for i := range values {
				values[i] = float64(i%17) / 32
			}
			first, err := m.bindConstants(values)
			if err != nil {
				t.Fatal(err)
			}
			want, err := first.Evaluate(make([]float64, len(first.Coordinates())), nil)
			if err != nil || math.IsNaN(want) || math.IsInf(want, 0) {
				t.Fatal("invalid synthetic result", want, err)
			}
			setupSeconds := time.Since(created).Seconds()
			for _, phase := range []string{"same_payload_hits", "unique_payloads", "reentry_after_churn"} {
				before := m.researchPrepare
				runtime.GC()
				var memoryBefore, memoryAfter runtime.MemStats
				runtime.ReadMemStats(&memoryBefore)
				at := time.Now()
				calls := 2000
				if phase != "same_payload_hits" {
					calls = 320
				}
				for i := 0; i < calls; i++ {
					if time.Now().After(deadline) {
						t.Fatal("microprofile work exceeded declared 60s guard")
					}
					if phase != "same_payload_hits" {
						values[0] = float64(i+1) / 100
					}
					program, e := m.bindConstants(values)
					if e != nil {
						t.Fatal(e)
					}
					if phase == "same_payload_hits" && program != first {
						t.Fatal("identical inputs missed retained program")
					}
					if len(m.programCache) > neutralProgramEntries || m.programNodes > neutralProgramNodes {
						t.Fatal("cache memory cap violated")
					}
				}
				seconds := time.Since(at).Seconds()
				runtime.ReadMemStats(&memoryAfter)
				after := m.researchPrepare
				researchPrepareRecord(t, map[string]any{
					"kind": "preparation_micro_profile", "name": fmt.Sprintf("%s %d ports %s: %.3fs", variant, count, phase, seconds),
					"variant": variant,
					"ports":   count, "phase": phase, "calls": calls, "seconds": seconds, "setup_seconds": setupSeconds,
					"constant_hit_calls": after.HitCalls - before.HitCalls, "constant_miss_calls": after.MissCalls - before.MissCalls,
					"key_seconds": after.KeySeconds - before.KeySeconds, "hit_seconds": after.HitSeconds - before.HitSeconds,
					"validation_seconds": after.ValidationSeconds - before.ValidationSeconds,
					"miss_seconds":       after.MissSeconds - before.MissSeconds, "ordering_seconds": after.OrderSeconds - before.OrderSeconds,
					"region_seconds": after.RegionSeconds - before.RegionSeconds, "evictions": after.Evictions - before.Evictions,
					"peak_entries": after.PeakEntries, "peak_nodes": after.PeakNodes,
					"heap_alloc_delta_bytes": int64(memoryAfter.HeapAlloc) - int64(memoryBefore.HeapAlloc),
					"total_alloc_bytes":      memoryAfter.TotalAlloc - memoryBefore.TotalAlloc,
					"program_entries":        len(m.programCache), "program_nodes": m.programNodes,
					"scope": "synthetic graph, accepted binder vs exact chunked key; no engine or production speed claim"})
			}
		}
	}
}

func TestPrepareChunkedDigestExact(t *testing.T) {
	for _, count := range []int{0, 1, 511, 512, 513, 11651, 15345} {
		values := make([]float64, count+3)
		values[0], values[1], values[2] = 0, math.Copysign(0, -1), math.SmallestNonzeroFloat64
		for i := 3; i < len(values); i++ {
			values[i] = math.Ldexp(float64(i%101-50), i%200-100)
		}
		dimensions := make([]int, count)
		for i := range dimensions {
			dimensions[i] = count - 1 - i
		}
		for change := 0; change < 3; change++ {
			data := make([]byte, 8*count)
			for i, dimension := range dimensions {
				binary.LittleEndian.PutUint64(data[8*i:], math.Float64bits(values[dimension]))
			}
			if researchChunkedConstantDigest(values, dimensions) != sha256.Sum256(data) {
				t.Fatalf("digest differs for %d ports, mutation %d", count, change)
			}
			values[0] = math.Copysign(float64(change), -1)
		}
	}
}

func TestPrepareChunkedMutableAndLatentGuards(t *testing.T) {
	m, keys := compactConstantModel(t)
	m.researchChunked = true
	values := []float64{1, 2, 3}
	a, err := m.bindConstants(values)
	if err != nil {
		t.Fatal(err)
	}
	before, _ := a.Evaluate(make([]float64, len(a.Coordinates())), nil)
	values[0] = 2
	b, err := m.bindConstants(values)
	if err != nil || a == b {
		t.Fatal("mutable payload reused old program", err)
	}
	after, _ := a.Evaluate(make([]float64, len(a.Coordinates())), nil)
	if before != after {
		t.Fatal("bound program changed after input mutation")
	}
	fromMap, err := m.bindProgram(compactMapEffects(keys, values))
	if err != nil || fromMap != b {
		t.Fatal("chunked dense key differs from existing map key", err)
	}
	values[2] = 9
	latent, err := m.bindConstants(values)
	if err != nil || latent != b {
		t.Fatal("finite latent input changed damage key", err)
	}
	// Even a port omitted by the damage projection must remain finite.
	for _, invalid := range []float64{math.NaN(), math.Inf(1), math.Inf(-1)} {
		values[2] = invalid
		if _, err := m.bindConstants(values); err == nil {
			t.Fatal("latent nonfinite input accepted")
		}
	}
	if _, err := m.bindConstants(values[:2]); err == nil {
		t.Fatal("short input accepted")
	}
	other, _ := compactConstantModel(t)
	other.researchChunked = true
	values[2] = 3
	c, err := other.bindConstants(values)
	if err != nil || c == b || other.stats.ProgramHits != 0 {
		t.Fatal("independent model shared retained program", err)
	}
}

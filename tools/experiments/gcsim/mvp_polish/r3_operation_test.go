package contracts

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"
)

func TestR3OperationValidatorDifferential(t *testing.T) {
	previous := r3OperationSwitch
	defer func() { r3OperationSwitch = previous }()
	prior := map[uint32]struct{}{1: {}, 2: {}, 3: {}, 4: {}}
	inputs := [][]IRInput{nil, {}, {{1, "value"}}, {{1, "left"}, {2, "right"}},
		{{1, "value"}, {1, "value"}}, {{2, "value"}, {1, "value"}}, {{99, "value"}, {2, "value"}},
		{{1, ""}, {2, "value"}}, {{1, "value"}, {2, "value"}, {3, "value"}, {4, "value"}}}
	operations := []string{"constant", "artifact_stat", "add", "multiply", "min", "max", "power", "opaque_frozen", "select_lt", "unknown", "ADD", ""}
	cases := 0
	for _, operation := range operations {
		for _, input := range inputs {
			for _, value := range []string{"", "0", "-0", "1e9", "NaN", "1e9999"} {
				for _, coordinate := range []string{"", "actor.atk", "bad coordinate"} {
					node := IRNode{NodeID: 5, Operation: operation, Inputs: input, Value: value, Coordinate: coordinate}
					want := node.r3FrozenNodeValidate("members[0]", prior)
					for _, enabled := range []bool{false, true} {
						r3OperationSwitch = enabled
						got := node.validate("members[0]", prior)
						if (want == nil) != (got == nil) || fmt.Sprint(want) != fmt.Sprint(got) {
							t.Fatal("validator rejection order/error changed", operation, enabled, want, got)
						}
					}
					cases++
				}
			}
		}
	}
	t.Logf("differential cases: %d, both toggles", cases)
}

func TestR3SavedOperationCosts(t *testing.T) {
	root := os.Getenv("GTT_R3_SAVED_INPUTS")
	if root == "" {
		t.Skip("owned decoded-member gate only")
	}
	previous := r3OperationSwitch
	defer func() { r3OperationSwitch = previous }()
	var rows []map[string]any
	for _, seed := range []string{"742031889", "742031890"} {
		raw, e := os.ReadFile(filepath.Join(root, seed, "member.json"))
		if e != nil {
			t.Fatal(e)
		}
		member, e := DecodeSeedMember(raw)
		if e != nil {
			t.Fatal(e)
		}
		for _, enabled := range []bool{false, true} {
			r3OperationSwitch = enabled
			runtime.GC()
			var before, after runtime.MemStats
			runtime.ReadMemStats(&before)
			start := time.Now()
			prior := make(map[uint32]struct{}, len(member.Nodes))
			for _, node := range member.Nodes {
				if enabled {
					e = node.validate("members[0]", prior)
				} else {
					e = node.r3FrozenNodeValidate("members[0]", prior)
				}
				if e != nil {
					t.Fatal(e)
				}
				prior[node.NodeID] = struct{}{}
			}
			wall := time.Since(start)
			runtime.ReadMemStats(&after)
			runtime.KeepAlive(member)
			runtime.KeepAlive(prior)
			rows = append(rows, map[string]any{"seed": seed, "switch": enabled, "nodes": len(member.Nodes),
				"wall_ms": float64(wall) / float64(time.Millisecond), "alloc_bytes": after.TotalAlloc - before.TotalAlloc,
				"allocations": after.Mallocs - before.Mallocs, "gc_cycles": after.NumGC - before.NumGC,
				"gc_pause_ms": float64(after.PauseTotalNs-before.PauseTotalNs) / float64(time.Millisecond),
				"scope":       "one node-validator pass over already-decoded real saved member, including identical prior-ID index; no channel/sidecar/decode/search work timed"})
		}
	}
	raw, e := json.MarshalIndent(rows, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(root, "operation-costs.json"), raw, 0600); e != nil {
		t.Fatal(e)
	}
}

func TestR3OperationValidatorAllocations(t *testing.T) {
	previous := r3OperationSwitch
	defer func() { r3OperationSwitch = previous }()
	node := IRNode{NodeID: 1, Operation: "constant", Inputs: []IRInput{}, Value: "1"}
	prior := map[uint32]struct{}{}
	frozen := testing.AllocsPerRun(64, func() {
		if e := node.r3FrozenNodeValidate("members[0]", prior); e != nil {
			panic(e)
		}
	})
	r3OperationSwitch = false
	disabled := testing.AllocsPerRun(64, func() {
		if e := node.validate("members[0]", prior); e != nil {
			panic(e)
		}
	})
	r3OperationSwitch = true
	enabled := testing.AllocsPerRun(64, func() {
		if e := node.validate("members[0]", prior); e != nil {
			panic(e)
		}
	})
	t.Logf("allocations per valid constant node: frozen=%g disabled=%g switch=%g", frozen, disabled, enabled)
	if enabled > frozen {
		t.Fatal("switch increased allocations")
	}
}

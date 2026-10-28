package engineclient

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"
)

func TestR5SavedStreamingHashCosts(t *testing.T) {
	root, path := os.Getenv("GTT_R5_SAVED_INPUTS"), os.Getenv("GTT_R5_HASH_BINARY")
	if root == "" || path == "" {
		t.Skip("owned retained-input gate only")
	}
	const expected = "f1e076b7fa9d292d0bab83aed9d3db0ec917437b288dcc6798cd69f4718f9b93"
	old := func() error {
		payload, err := os.ReadFile(path)
		if err != nil {
			return err
		}
		digest := sha256.Sum256(payload)
		if hex.EncodeToString(digest[:]) != expected {
			return fmt.Errorf("saved binary changed")
		}
		return nil
	}
	var rows []map[string]any
	for _, arm := range []string{"R4_ReadFile", "R5_streaming"} {
		runtime.GC()
		var before, after runtime.MemStats
		runtime.ReadMemStats(&before)
		cpu, available := r3ProcessCPU()
		start := time.Now()
		var err error
		if arm == "R4_ReadFile" {
			err = old()
		} else {
			err = verifyFileSHA256(path, expected)
		}
		elapsed := time.Since(start)
		cpuAfter, availableAfter := r3ProcessCPU()
		runtime.ReadMemStats(&after)
		if err != nil {
			t.Fatal(err)
		}
		row := map[string]any{"arm": arm, "wall_ms": float64(elapsed) / float64(time.Millisecond),
			"allocated_bytes": after.TotalAlloc - before.TotalAlloc, "allocations": after.Mallocs - before.Mallocs,
			"cpu_available": available && availableAfter, "verified_sha256": expected}
		if available && availableAfter {
			row["process_cpu_ms"] = float64(cpuAfter-cpu) / 1e6
		}
		rows = append(rows, row)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	result := map[string]any{"rows": rows, "file_bytes": info.Size(), "checks_per_arm": 1,
		"scope": "Read-only installed unchanged producer bytes; no engine invocation. Every required integrity check retained. One warm-order pair, not attribution of the final outer timer."}
	raw, err := json.MarshalIndent(result, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(root, "r5-stream-hash-costs.json"), append(raw, '\n'), 0600); err != nil {
		t.Fatal(err)
	}
}

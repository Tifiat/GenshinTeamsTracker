package contracts

import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"testing"
	"time"
)

func TestR4SavedPanelAndOwnedHashCosts(t *testing.T) {
	root := os.Getenv("GTT_R4_SAVED_INPUTS")
	if root == "" {
		t.Skip("owned real-input measurement only")
	}
	members := []IRSeedMember{}
	var raws [][]byte
	for _, seed := range []string{"742031889", "742031890"} {
		raw, e := os.ReadFile(filepath.Join(root, seed, "member.json"))
		if e != nil {
			t.Fatal(e)
		}
		member, e := DecodeSeedMember(raw)
		if e != nil {
			t.Fatal(e)
		}
		members = append(members, member)
		raws = append(raws, raw)
	}
	var rows []map[string]any
	var expected []byte
	for _, typed := range []bool{false, true} {
		runtime.GC()
		var before, after runtime.MemStats
		runtime.ReadMemStats(&before)
		start := time.Now()
		var raw []byte
		var err error
		if typed {
			raw, err = CanonicalSeedMembersJSON(members)
		} else {
			raw, err = CanonicalJSON(members)
		}
		if err != nil {
			t.Fatal(err)
		}
		digest := BytesSHA256(raw)
		wall := time.Since(start)
		runtime.ReadMemStats(&after)
		if !typed {
			expected = raw
		} else if !bytes.Equal(expected, raw) {
			t.Fatal("saved canonical panel byte parity differs")
		}
		rows = append(rows, map[string]any{"operation": "canonical_panel", "typed": typed, "members": len(members), "output_bytes": len(raw), "sha256": digest, "wall_ms": float64(wall) / float64(time.Millisecond), "alloc_bytes": after.TotalAlloc - before.TotalAlloc, "allocations": after.Mallocs - before.Mallocs})
	}
	for index, raw := range raws {
		var expected string
		for _, reuse := range []bool{false, true} {
			runtime.GC()
			var before, after runtime.MemStats
			runtime.ReadMemStats(&before)
			start := time.Now()
			binding, result := BytesSHA256(raw), ""
			if reuse {
				result = binding
			} else {
				result = BytesSHA256(raw)
			}
			wall := time.Since(start)
			runtime.ReadMemStats(&after)
			if binding != result || (!reuse && expected != "") {
				t.Fatal("raw binding/result digest differs")
			}
			expected = result
			rows = append(rows, map[string]any{"operation": "owned_raw_digest", "member_index": index, "reuse": reuse, "input_bytes": len(raw), "hash_calls": map[bool]int{false: 2, true: 1}[reuse], "sha256": result, "wall_ms": float64(wall) / float64(time.Millisecond), "alloc_bytes": after.TotalAlloc - before.TotalAlloc, "allocations": after.Mallocs - before.Mallocs})
		}
	}
	data, e := json.MarshalIndent(rows, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(root, "r4-canonical-hash-costs.json"), data, 0600); e != nil {
		t.Fatal(e)
	}
}

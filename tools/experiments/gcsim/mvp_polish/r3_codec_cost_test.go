package contracts

// Bounded saved-data component measurements; never invoked by a product run.
import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"testing"
	"time"
)

func TestR3SavedCodecCosts(t *testing.T) {
	root := os.Getenv("GTT_R3_SAVED_INPUTS")
	if root == "" {
		t.Skip("owned saved-data gate only")
	}
	var rows []map[string]any
	for index, seed := range []string{"742031889", "742031890"} {
		raw, err := os.ReadFile(filepath.Join(root, seed, "member.json"))
		if err != nil {
			t.Fatal(err)
		}
		var first IRSeedMember
		order := []bool{false, true}
		if index == 1 {
			order = []bool{true, false}
		}
		for at, typed := range order {
			runtime.GC()
			var before, after, retained runtime.MemStats
			runtime.ReadMemStats(&before)
			start := time.Now()
			row := map[string]any{"seed": seed, "typed": typed, "input_bytes": len(raw)}
			mark := start
			step := func(name string) {
				now := time.Now()
				row[name] = float64(now.Sub(mark)) / float64(time.Millisecond)
				mark = now
			}
			var member IRSeedMember
			decoder := json.NewDecoder(bytes.NewReader(raw))
			decoder.DisallowUnknownFields()
			if err = decoder.Decode(&member); err != nil {
				t.Fatal(err)
			}
			var tail any
			if err = decoder.Decode(&tail); err != io.EOF {
				t.Fatal("trailing contract", err)
			}
			step("typed_decode_eof_ms")
			inputCanonical, e := canonicalizeRawJSON(raw)
			if e != nil {
				t.Fatal(e)
			}
			step("raw_canonical_ms")
			var typedCanonical []byte
			if typed {
				typedCanonical, e = canonicalDecodedContract(member)
			} else {
				typedCanonical, e = CanonicalJSON(member)
			}
			if e != nil {
				t.Fatal(e)
			}
			step("typed_canonical_ms")
			if !bytes.Equal(inputCanonical, typedCanonical) {
				t.Fatal("canonical comparison differs")
			}
			step("canonical_compare_ms")
			if e = ValidateSeedMember(member); e != nil {
				t.Fatal(e)
			}
			step("semantic_validation_ms")
			row["decode_total_ms"] = float64(time.Since(start)) / float64(time.Millisecond)
			runtime.ReadMemStats(&after)
			digest := sha256.Sum256(typedCanonical)
			row["canonical_sha256"] = hex.EncodeToString(digest[:])
			inputCanonical = nil
			typedCanonical = nil
			decoder = nil
			runtime.GC()
			runtime.ReadMemStats(&retained)
			runtime.KeepAlive(member)
			runtime.KeepAlive(raw)
			row["alloc_bytes"] = after.TotalAlloc - before.TotalAlloc
			row["allocations"] = after.Mallocs - before.Mallocs
			row["heap_after_work_bytes"] = after.HeapAlloc
			row["retained_member_delta_bytes"] = int64(retained.HeapAlloc) - int64(before.HeapAlloc)
			row["nodes"] = len(member.Nodes)
			if at == 0 {
				first = member
			} else if !reflect.DeepEqual(first, member) {
				t.Fatal("saved codec value parity failed")
			}
			// Actual public decoder is checked separately from this timed
			// decomposition; semantic data must agree with the measured path.
			setting := "0"
			if typed {
				setting = "1"
			}
			t.Setenv("GTT_R3_TYPED_CANONICAL", setting)
			actual, e := DecodeSeedMember(raw)
			if e != nil || !reflect.DeepEqual(actual, member) {
				t.Fatal("component path differs from public decoder", e)
			}
			rows = append(rows, row)
		}
	}
	encoded, err := json.MarshalIndent(rows, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(root, "codec-costs.json"), encoded, 0600); err != nil {
		t.Fatal(err)
	}
	fmt.Println("R3 saved codec rows:", len(rows))
}

package contracts

// Overlay-only same-payload comparison of the removed redundant JSON round
// trip. No engine calls. This does not relax strict fields or graph validation.
import (
	"bytes"
	"encoding/json"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestAllSetsCanonicalReadBenchmark(t *testing.T) {
	raw, err := os.ReadFile(os.Getenv("GTT_CANONICAL_INPUT"))
	if err != nil {
		t.Fatal(err)
	}
	if _, err = DecodeSeedMember(raw); err != nil {
		t.Fatal(err)
	}
	oldMS, newMS := []float64{}, []float64{}
	for i := 0; i < 3; i++ {
		started := time.Now()
		decoder := json.NewDecoder(bytes.NewReader(raw))
		decoder.UseNumber()
		var generic any
		if err = decoder.Decode(&generic); err != nil {
			t.Fatal(err)
		}
		old, err := CanonicalJSON(generic)
		if err != nil {
			t.Fatal(err)
		}
		oldMS = append(oldMS, float64(time.Since(started))/float64(time.Millisecond))
		started = time.Now()
		current, err := canonicalizeRawJSON(raw)
		if err != nil {
			t.Fatal(err)
		}
		newMS = append(newMS, float64(time.Since(started))/float64(time.Millisecond))
		if !bytes.Equal(old, current) {
			t.Fatal("canonical byte identity changed")
		}
	}
	out := map[string]any{"scope": "same saved compact member, raw canonical comparison substep only, three sequential repetitions", "input_sha256": TextSHA256(string(raw)), "input_bytes": len(raw), "old_ms": oldMS, "new_ms": newMS, "canonical_bytes_identical": true, "strict_member_decode_passed": true, "new_engine_calls": 0}
	data, err := json.MarshalIndent(out, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(os.Getenv("GTT_CANONICAL_OUTPUT"), "canonical-read-benchmark.json"), data, 0600); err != nil {
		t.Fatal(err)
	}
	t.Logf("old ms %v; direct ms %v", oldMS, newMS)
}

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestProgressEmitterWritesStrictMonotonicRecords(t *testing.T) {
	var buffer bytes.Buffer
	emitter := newProgressEmitter(&buffer, strings.Repeat("a", 64))
	if err := emitter.emit("searching", 1, 5, false); err != nil {
		t.Fatal(err)
	}
	if err := emitter.emit("completed", 5, 5, false); err != nil {
		t.Fatal(err)
	}
	decoder := json.NewDecoder(&buffer)
	for expectedSequence := int64(0); expectedSequence < 2; expectedSequence++ {
		var record contracts.ProgressRecord
		if err := decoder.Decode(&record); err != nil {
			t.Fatal(err)
		}
		if err := record.Validate(); err != nil {
			t.Fatal(err)
		}
		if record.Sequence != expectedSequence {
			t.Fatalf("sequence = %d, want %d", record.Sequence, expectedSequence)
		}
	}
}

func TestCancelledContextStopsBeforeReadingRequest(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	err := run(ctx, []string{"validate-request", "missing.json"})
	if err == nil || !strings.Contains(err.Error(), "cancelled") {
		t.Fatalf("cancelled context should stop command, got %v", err)
	}
}

func containsString(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func productFixtures(t *testing.T) (contracts.OptimizerRequest, contracts.CompactIR) {
	t.Helper()
	_, filename, _, _ := runtime.Caller(0)
	directory := filepath.Join(filepath.Dir(filename), "..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	requestPayload, err := os.ReadFile(filepath.Join(directory, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	compactPayload, err := os.ReadFile(filepath.Join(directory, "compact_ir_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	request, err := contracts.DecodeRequest(requestPayload)
	if err != nil {
		t.Fatal(err)
	}
	compact, err := contracts.DecodeCompactIR(compactPayload)
	if err != nil {
		t.Fatal(err)
	}
	return request, compact
}

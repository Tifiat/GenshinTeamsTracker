package main

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAllSetsCommandRejectsSourceEnvelopeBeforeEngine(t *testing.T) {
	root := filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1")
	dir := t.TempDir()
	source := filepath.Join(dir, "source.json")
	if e := os.WriteFile(source, []byte(`{"schema_version":1,"untrusted_flag":true}`), 0600); e != nil {
		t.Fatal(e)
	}
	runRoot := filepath.Join(dir, "run")
	e := run(context.Background(), []string{"optimize-all-sets", filepath.Join(root, "request_v1.json"), source, runRoot})
	if e == nil || !strings.Contains(e.Error(), "unknown field") {
		t.Fatal(e)
	}
	if _, e = os.Stat(runRoot); !os.IsNotExist(e) {
		t.Fatal("engine/run mutation before source validation")
	}
}

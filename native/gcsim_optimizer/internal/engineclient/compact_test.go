package engineclient

import (
	"context"
	"os"
	"path/filepath"
	"testing"
)

func TestCompactCancellationAndExistingDirectoryDoNotLaunch(t *testing.T) {
	bound := BoundEngine{binaryPath: "must-not-be-started"}
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	path := filepath.Join(t.TempDir(), "cancelled")
	if _, err := bound.RunCompact(ctx, "config", path, 1, true); err == nil {
		t.Fatal("cancel ignored")
	}
	if _, err := os.Stat(path); !os.IsNotExist(err) {
		t.Fatal("cancel created capture directory")
	}
	if _, err := bound.RunCompact(context.Background(), "config", t.TempDir(), 1, true); err == nil {
		t.Fatal("existing directory accepted")
	}
}

package setcontext

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestProviderPreservesExplicitEnergyAndRejectsAmbiguity(t *testing.T) {
	for _, mode := range []string{"true", "false"} {
		v, e := explicitEnergy("options iteration=100 ignore_burst_energy=" + mode + ";\n")
		if e != nil || v != (mode == "true") {
			t.Fatal(v, e)
		}
	}
	for _, s := range []string{"options iteration=100;", "options ignore_burst_energy=true ignore_burst_energy=false;", "options ignore_burst_energy=invalid;", "options ignore_burst_energy=true;\noptions iteration=1;"} {
		if _, e := explicitEnergy(s); e == nil {
			t.Fatal("ambiguous energy accepted")
		}
	}
}

func TestProviderRejectsBindingDriftBeforeProcessAndCloses(t *testing.T) {
	c := fixtureContext(t)
	root := t.TempDir()
	binary := filepath.Join(root, "not-run.exe")
	bytes := []byte("verified test executable; never run")
	if e := os.WriteFile(binary, bytes, 0600); e != nil {
		t.Fatal(e)
	}
	b := c.binding
	b.Engine.BinaryPath = binary
	b.Engine.ArtifactSHA256 = contracts.TextSHA256(string(bytes))
	p, e := NewEngineProvider(b, root)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = p.Capture(context.Background(), c); e == nil || !strings.Contains(e.Error(), "binding changed") {
		t.Fatal(e)
	}
	if e = p.Close(); e != nil {
		t.Fatal(e)
	}
	matching, e := New(b, c.text)
	if e != nil {
		t.Fatal(e)
	}
	if _, e = p.Capture(context.Background(), matching); e == nil {
		t.Fatal("closed provider ran")
	}
	b.Seeds = b.Seeds[:1]
	if _, e = NewEngineProvider(b, root); e == nil {
		t.Fatal("n1 product capture accepted")
	}
	for _, seeds := range [][]uint64{{2, 1}, {1, 1}} {
		b.Seeds = seeds
		if _, e = NewEngineProvider(b, root); e == nil {
			t.Fatal("noncanonical seed panel accepted")
		}
	}
}

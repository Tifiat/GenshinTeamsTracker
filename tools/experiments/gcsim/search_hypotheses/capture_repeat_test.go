package main

// Copied into managed source only. Reproduce the product's canonical neutral
// capture twice; no inventory search or ordinary finalist simulations.
import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/allsets"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

func TestHypothesisCaptureRepeat(t *testing.T) {
	root := os.Getenv("GTT_CAPTURE_REPEAT")
	if root == "" || root != os.Getenv("GTT_SCRATCH_DIR") {
		t.Fatal("owned managed capture scope required")
	}
	req, sources, err := readSetSources(filepath.Join(root, "request.json"), filepath.Join(root, "set-sources.json"))
	if err != nil {
		t.Fatal(err)
	}
	requestSHA, err := contracts.CanonicalSHA256(req)
	if err != nil {
		t.Fatal(err)
	}
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: sources.CatalogSHA256, ReferenceStatsSHA256: requestSHA, Seeds: req.Stochastic.Seeds}
	base, err := setcontext.New(binding, req.Context.PreparedConfig.Text)
	if err != nil {
		t.Fatal(err)
	}
	index, err := domain.Build(req, nil)
	if err != nil {
		t.Fatal(err)
	}
	_, index, base, err = allsets.CanonicalReference(req, index, base, binding)
	if err != nil {
		t.Fatal(err)
	}
	changes := map[string][]setcontext.Set{}
	for _, wearer := range index.Wearers {
		changes[wearer.WearerKey] = nil
	}
	neutral, err := base.Replace(changes)
	if err != nil {
		t.Fatal(err)
	}
	if neutral.Key() != os.Getenv("GTT_CAPTURE_CONTEXT") {
		t.Fatal("canonical context differs", neutral.Key())
	}
	for _, name := range []string{"first", "second"} {
		dir := filepath.Join(root, name)
		if err = os.Mkdir(dir, 0700); err != nil {
			t.Fatal(err)
		}
		provider, err := setcontext.NewEffectEngineProvider(binding, dir)
		if err != nil {
			t.Fatal(err)
		}
		_, captureErr := provider.Capture(context.Background(), neutral)
		closeErr := provider.Close()
		if captureErr != nil {
			t.Fatal(captureErr)
		}
		if closeErr != nil {
			t.Fatal(closeErr)
		}
	}
}

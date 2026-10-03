package main

// Research overlay: copied into cmd/gtt-optimizer only in managed scratch.
// No engine process or installed consumer is used by this replay provider.
import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

type hypothesisProvider struct{ binding setcontext.Binding }

func newHypothesisProvider(binding setcontext.Binding, root string) (*hypothesisProvider, error) {
	return &hypothesisProvider{binding}, nil
}
func (p *hypothesisProvider) Close() error                        { return nil }
func (p *hypothesisProvider) Timings() []setcontext.CaptureTiming { return nil }
func (p *hypothesisProvider) Capture(ctx context.Context, target *setcontext.Context) (setcontext.Capture, error) {
	out := setcontext.Capture{ContextSHA256: target.Key(), ConfigSHA256: target.ConfigSHA256(), EngineBindingSHA256: p.binding.Engine.BindingSHA256}
	for _, seed := range p.binding.Seeds {
		matches, err := filepath.Glob(filepath.Join(os.Getenv("GTT_HYPOTHESIS_SAVED"), "verification", "contexts", "context-*", fmt.Sprintf("seed-%d", seed), "member.json.effects.json"))
		if err != nil {
			return out, err
		}
		found := false
		for _, path := range matches {
			if err := ctx.Err(); err != nil {
				return out, err
			}
			data, err := os.ReadFile(path)
			if err != nil {
				return out, err
			}
			var sidecar contracts.EffectInputsOutput
			if err = json.Unmarshal(data, &sidecar); err != nil {
				return out, err
			}
			if sidecar.InputConfigSHA256 != target.ConfigSHA256() {
				continue
			}
			if found {
				return out, fmt.Errorf("ambiguous saved capture")
			}
			if sidecar.SourceManifestBodySHA256 != p.binding.Engine.SourceManifestSHA256 || sidecar.Seed != fmt.Sprint(seed) {
				return out, fmt.Errorf("saved capture binding mismatch")
			}
			memberBytes, err := os.ReadFile(filepath.Join(filepath.Dir(path), "member.json"))
			if err != nil {
				return out, err
			}
			if fmt.Sprintf("%x", sha256.Sum256(memberBytes)) != sidecar.MemberContentSHA256 {
				return out, fmt.Errorf("saved member hash mismatch")
			}
			member, err := contracts.DecodeSeedMember(memberBytes)
			if err != nil {
				return out, err
			}
			if member.Seed != seed {
				return out, fmt.Errorf("saved member seed mismatch")
			}
			out.Members = append(out.Members, member)
			out.Effects = append(out.Effects, sidecar)
			found = true
		}
		if !found {
			return out, fmt.Errorf("no exact saved capture for config %s seed %d; engine fallback forbidden", target.ConfigSHA256(), seed)
		}
	}
	return out, nil
}

func TestHypothesisReplay(t *testing.T) {
	saved, work := os.Getenv("GTT_HYPOTHESIS_SAVED"), os.Getenv("GTT_HYPOTHESIS_WORK")
	if saved == "" || work == "" {
		t.Fatal("managed replay paths required")
	}
	defer func() {
		var memory runtime.MemStats
		runtime.ReadMemStats(&memory)
		data, err := json.Marshal(map[string]any{"heap_alloc_bytes": memory.HeapAlloc, "heap_sys_bytes": memory.HeapSys, "total_alloc_bytes": memory.TotalAlloc, "gc_count": memory.NumGC, "gc_pause_ns": memory.PauseTotalNs})
		if err != nil {
			t.Error(err)
			return
		}
		if err = os.WriteFile(filepath.Join(filepath.Dir(work), "memory.json"), data, 0600); err != nil {
			t.Error(err)
		}
	}()
	data, err := os.ReadFile(filepath.Join(saved, "request.json"))
	if err != nil {
		t.Fatal(err)
	}
	req, err := contracts.DecodeRequest(data)
	if err != nil {
		t.Fatal(err)
	}
	if !req.EffectiveResultOptions().FastMode {
		t.Fatal("replay forbids ordinary engine verification")
	}
	output, err := os.Create(filepath.Join(filepath.Dir(work), "product-stdout.json"))
	if err != nil {
		t.Fatal(err)
	}
	previous := os.Stdout
	os.Stdout = output
	defer func() { os.Stdout = previous; output.Close() }()
	if err = optimizeAllSets(context.Background(), filepath.Join(saved, "request.json"), filepath.Join(saved, "set-sources.json"), work); err != nil {
		t.Fatal(err)
	}
}

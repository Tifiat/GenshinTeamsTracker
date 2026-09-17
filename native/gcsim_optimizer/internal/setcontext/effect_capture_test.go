package setcontext

import (
	"context"
	"strconv"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestEffectSnapshotsOnlyForExactSourceContext(t *testing.T) {
	base := fixtureContext(t)
	provider := func(_ context.Context, c *Context) (Capture, error) {
		out := syntheticCapture(c, "100")
		for _, m := range out.Members {
			out.Effects = append(out.Effects, contracts.EffectInputsOutput{
				SchemaVersion: 1, Capability: contracts.EffectInputsCapability, ContextSHA256: c.configSHA,
				InputConfigSHA256: c.configSHA, SourceManifestBodySHA256: c.binding.Engine.SourceManifestSHA256,
				Seed: strconv.FormatUint(m.Seed, 10), CharacterKeys: c.Actors(),
			})
		}
		return out, nil
	}
	s, _ := NewSession(provider, 2)
	h, e := s.Resolve(context.Background(), base, nil, nil)
	if e != nil {
		t.Fatal(e)
	}
	n := 0
	visit := func(m contracts.IRSeedMember, out contracts.EffectInputsOutput) error { n++; return nil }
	if e = h.VisitEffectSnapshots(visit); e != nil || n != len(base.binding.Seeds) {
		t.Fatal(n, e)
	}
	target := replaced(t, base, []Set{{UID: "new", Count: 2}})
	biased, e := s.Resolve(context.Background(), target, h, syntheticProof(base, target, h.GraphSHA256()))
	if e != nil {
		t.Fatal(e)
	}
	if biased.VisitEffectSnapshots(visit) == nil {
		t.Fatal("old effect guide exposed for substituted context")
	}
	capture, _ := provider(context.Background(), base)
	capture.Effects[0].CharacterKeys[0] = "another"
	if _, e = compileCapture(base, capture); e == nil {
		t.Fatal("wrong owner accepted")
	}
	capture, _ = provider(context.Background(), base)
	capture.Effects = capture.Effects[:1]
	if _, e = compileCapture(base, capture); e == nil {
		t.Fatal("incomplete effects accepted")
	}
	if _, e = NewEffectEngineProvider(base.binding, t.TempDir()); e == nil {
		t.Fatal("legacy engine accepted for effect guide")
	}
}

package seteffects

// Opt-in parity on an existing product tape. Compiler output belongs to the
// managed experiment job; no new captures or account writes are performed.
import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

func savedSymbolicBinding(t *testing.T) (*NeutralBinding, contracts.OptimizerRequest) {
	t.Helper()
	run := os.Getenv("GTT_SAVED_INITIAL_RUN")
	if run == "" {
		t.Skip("explicit saved product tape required")
	}
	job := os.Getenv("GTT_SCRATCH_DIR")
	if job == "" || filepath.Dir(os.Getenv("GOCACHE")) != job {
		t.Fatal("managed job required")
	}
	read := func(path string, out any) {
		t.Helper()
		data, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err := json.Unmarshal(data, out); err != nil {
			t.Fatal(err)
		}
	}
	var req contracts.OptimizerRequest
	var bundle SourceBundle
	read(filepath.Join(run, "request.json"), &req)
	read(filepath.Join(run, "set-sources.json"), &bundle)
	if err := req.Validate(); err != nil {
		t.Fatal(err)
	}
	binary, err := os.ReadFile(req.Engine.BinaryPath)
	if err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(binary)
	if hex.EncodeToString(digest[:]) != req.Engine.ArtifactSHA256 {
		t.Fatal("saved engine differs")
	}
	catalog, err := CompileSourceBundleForInventory(bundle, req.Engine, bundle.CatalogSHA256, req.Artifacts)
	if err != nil {
		t.Fatal(err)
	}
	paths, err := filepath.Glob(filepath.Join(run, "verification", "contexts", "context-*", "seed-*", "member.json.effects.json"))
	if err != nil || len(paths) != len(req.Stochastic.Seeds) {
		t.Fatal("unexpected saved panel", err, len(paths))
	}
	var sidecars []contracts.EffectInputsOutput
	for _, path := range paths {
		var s contracts.EffectInputsOutput
		read(path, &s)
		data, err := os.ReadFile(filepath.Join(filepath.Dir(path), "member.json"))
		if err != nil {
			t.Fatal(err)
		}
		digest := sha256.Sum256(data)
		if hex.EncodeToString(digest[:]) != s.MemberContentSHA256 {
			t.Fatal("sidecar identity differs")
		}
		sidecars = append(sidecars, s)
	}
	b, err := NewNeutralBinding(catalog, sidecars)
	if err != nil {
		t.Fatal(err)
	}
	return b, req
}

func TestSavedSymbolicPreparationTriggers(t *testing.T) {
	b, _ := savedSymbolicBinding(t)
	for owner, actor := range b.members[0].neutral.Context.Characters {
		for _, set := range b.catalog.Sets {
			for _, pieces := range []int{2, 4} {
				choice := RuleChoice{owner, set.Key, pieces}
				out := b.compilePackagesJoint([]RuleChoice{choice})
				if out.footprint.statDependent {
					t.Logf("SYMBOLIC_TRIGGER actor=%s choice=%+v complete=%v boundaries=%v", actor.Key, choice, out.Complete(), out.Boundaries)
				}
			}
		}
	}
	t.Logf("SYMBOLIC_STATS %+v", b.PreparationStats())
}

func evaluateSavedEffect(t *testing.T, x *formula.InputExpression, reads map[string]float64, scale float64) float64 {
	t.Helper()
	if x == nil {
		t.Fatal("missing expression")
	}
	switch x.Operation {
	case "constant":
		return x.Value
	case "read":
		value, ok := reads[x.Key]
		if !ok {
			t.Fatal("unbound read", x.Key)
		}
		return value * scale
	}
	a := evaluateSavedEffect(t, x.Inputs[0], reads, scale)
	bb := evaluateSavedEffect(t, x.Inputs[1], reads, scale)
	switch x.Operation {
	case "add":
		return a + bb
	case "subtract":
		return a - bb
	case "multiply":
		return a * bb
	case "divide":
		return a / bb
	case "min":
		return math.Min(a, bb)
	case "max":
		return math.Max(a, bb)
	case "select_lt":
		if a < bb {
			return evaluateSavedEffect(t, x.Inputs[2], reads, scale)
		}
		return evaluateSavedEffect(t, x.Inputs[3], reads, scale)
	}
	t.Fatal("unsupported saved expression", x.Operation)
	return 0
}

func TestSavedSymbolicCompositionParity(t *testing.T) {
	b, _ := savedSymbolicBinding(t)
	reads := map[string]float64{}
	for _, read := range b.Reads() {
		reads[read.Key] = read.Observed
	}
	var cases [][]RuleChoice
	for owner := range b.members[0].neutral.Context.Characters {
		for _, key := range []string{"noblesseoblige", "tenacityofthemillelith", "goldentroupe", "scrolloftheheroofcindercity", "emblemofseveredfate"} {
			for other := range b.members[0].neutral.Context.Characters {
				if other != owner {
					cases = append(cases, []RuleChoice{{owner, "emblemofseveredfate", 4}, {other, key, 4}})
				}
			}
		}
	}
	var fast, full time.Duration
	for _, choices := range cases {
		start := time.Now()
		got := b.CompilePackagesCompact(choices)
		fast += time.Since(start)
		start = time.Now()
		want := b.compilePackagesJoint(choices)
		full += time.Since(start)
		if got.Complete() != want.Complete() {
			t.Fatalf("boundary parity: %v got=%v want=%v", choices, got.Boundaries, want.Boundaries)
		}
		if !got.Complete() {
			continue
		}
		for _, scale := range []float64{.25, 1, 4} {
			for i, key := range b.Keys() {
				var a float64
				if got.Constants != nil {
					a = got.Constants[i]
				} else {
					a = evaluateSavedEffect(t, got.Effects[key], reads, scale)
				}
				bb := evaluateSavedEffect(t, want.Effects[key], reads, scale)
				if math.IsNaN(a) || math.Abs(a-bb) > 1e-10*math.Max(1, math.Abs(bb)) {
					t.Fatalf("effect parity %v %s scale=%v: got=%.17g want=%.17g", choices, key, scale, a, bb)
				}
			}
		}
	}
	t.Logf("SYMBOLIC_PARITY cases=%d fast_seconds=%.6f full_seconds=%.6f stats=%+v", len(cases), fast.Seconds(), full.Seconds(), b.PreparationStats())
	if b.stats.SymbolicCompositions == 0 {
		t.Fatal("symbolic reuse never exercised")
	}
}

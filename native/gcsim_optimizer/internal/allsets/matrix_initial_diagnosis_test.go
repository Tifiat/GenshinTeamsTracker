package allsets

// Initial-package diagnosis only. Two neutral captures, no item search/ordinary
// verification, all output owned by the managed caller. Retire with startup gate.
import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"reflect"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func TestMatrixInitialDiagnosis(t *testing.T) {
	run := os.Getenv("GTT_MATRIX_INITIAL_RUN")
	if run == "" {
		t.Skip("explicit managed initial-only diagnosis")
	}
	job := os.Getenv("GTT_SCRATCH_DIR")
	if job == "" || filepath.Dir(run) != job || filepath.Dir(os.Getenv("GOCACHE")) != job {
		t.Fatal("managed job required")
	}
	read := func(name string, value any) {
		data, err := os.ReadFile(filepath.Join(run, name))
		if err != nil {
			t.Fatal(err)
		}
		if err := json.Unmarshal(data, value); err != nil {
			t.Fatal(err)
		}
	}
	var req contracts.OptimizerRequest
	var bundle seteffects.SourceBundle
	read("request.json", &req)
	read("set-sources.json", &bundle)
	if err := req.Validate(); err != nil {
		t.Fatal(err)
	}
	sha, err := contracts.CanonicalSHA256(req)
	if err != nil {
		t.Fatal(err)
	}
	sources, err := seteffects.CompileSourceBundleForInventory(bundle, req.Engine, bundle.CatalogSHA256, req.Artifacts)
	if err != nil {
		t.Fatal(err)
	}
	bind := setcontext.Binding{Engine: req.Engine, CatalogSHA256: bundle.CatalogSHA256, ReferenceStatsSHA256: sha, Seeds: req.Stochastic.Seeds}
	base, err := setcontext.New(bind, req.Context.PreparedConfig.Text)
	if err != nil {
		t.Fatal(err)
	}
	changes := map[string][]setcontext.Set{}
	for _, w := range req.Wearers {
		changes[w.WearerKey] = nil
	}
	neutral, err := base.Replace(changes)
	if err != nil {
		t.Fatal(err)
	}
	root := filepath.Join(run, "captures")
	if err := os.Mkdir(root, 0700); err != nil {
		t.Fatal(err)
	}
	provider, err := setcontext.NewEffectEngineProvider(bind, root)
	if err != nil {
		t.Fatal(err)
	}
	defer provider.Close()
	session, err := setcontext.NewSession(provider.Capture, len(req.Stochastic.Seeds))
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 120*time.Second)
	defer cancel()
	h, err := session.Resolve(ctx, neutral, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	var sidecars []contracts.EffectInputsOutput
	err = h.VisitEffectSnapshots(func(member contracts.IRSeedMember, s contracts.EffectInputsOutput) error {
		sidecars = append(sidecars, s)
		counts := map[string]int{}
		shown := 0
		for _, stat := range s.Neutral.Stats {
			if stat.Point.Order == 0 {
				counts[stat.Owner+":"+stat.Stat+":"+stat.Point.Mode]++
				if shown < 3 {
					t.Logf("INITIAL_ZERO_STAT seed=%s value=%+v", s.Seed, stat)
					shown++
				}
			}
		}
		t.Logf("INITIAL_ZERO_COUNTS seed=%s counts=%v", s.Seed, counts)
		for _, effect := range s.Neutral.Effects {
			if effect.Order == 0 {
				t.Logf("INITIAL_ZERO_EFFECT seed=%s value=%+v", s.Seed, effect)
			}
		}
		hits := map[uint64]contracts.NeutralHitPoint{}
		for _, hit := range s.Neutral.Hits {
			hits[hit.HitID] = hit
		}
		for _, port := range s.ResistanceInputs {
			if hits[port.HitID].Point.HitOrder == 0 {
				t.Logf("INITIAL_ZERO_RESISTANCE seed=%s port=%+v hit=%+v", s.Seed, port, hits[port.HitID])
			}
		}
		return nil
	})
	if err != nil {
		t.Fatal(err)
	}
	b, err := seteffects.NewNeutralBinding(sources, sidecars)
	if err != nil {
		t.Fatal(err)
	}
	var choices []seteffects.RuleChoice
	for owner, ch := range sidecars[0].Neutral.Context.Characters {
		for _, w := range req.Wearers {
			if w.WearerKey == ch.Key {
				for _, set := range w.SetRequirements() {
					choices = append(choices, seteffects.RuleChoice{Owner: owner, Key: set.SetUID, Pieces: set.Count})
				}
			}
		}
	}
	for _, c := range [][]seteffects.RuleChoice{nil, choices} {
		old, now := b.CompilePackages(c), b.CompilePackagesCompact(c)
		t.Logf("INITIAL_PACKAGE choices=%v map_complete=%v dense_complete=%v boundaries=%v/%v", c, old.Complete(), now.Complete(), old.Boundaries, now.Boundaries)
		if !reflect.DeepEqual(old.Boundaries, now.Boundaries) {
			t.Fatal("representation changes startup boundary")
		}
	}
}

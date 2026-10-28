package allsets

// Opt-in two-winner diagnosis, not a new optimizer path. All captures/compiler
// files are owned by managed scratch; compact output goes into the dated receipt.
import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func TestMatrixCandidateDiagnosis(t *testing.T) {
	run := os.Getenv("GTT_MATRIX_CANDIDATE_RUN")
	if run == "" {
		t.Skip("explicit managed two-candidate diagnosis only")
	}
	job := os.Getenv("GTT_SCRATCH_DIR")
	if job == "" || filepath.Dir(run) != job || filepath.Dir(os.Getenv("GOCACHE")) != job {
		t.Fatal("managed workspace required")
	}
	read := func(path string, value any) {
		t.Helper()
		b, err := os.ReadFile(path)
		if err != nil {
			t.Fatal(err)
		}
		if err = json.Unmarshal(b, value); err != nil {
			t.Fatal(err)
		}
	}
	var req contracts.OptimizerRequest
	var bundle seteffects.SourceBundle
	var cases []struct {
		Name       string
		Assignment domain.Assignment
		Expected   *float64
	}
	read(filepath.Join(run, "request.json"), &req)
	read(filepath.Join(run, "set-sources.json"), &bundle)
	read(filepath.Join(run, "cases.json"), &cases)
	if len(cases) != 2 {
		t.Fatal("exactly two saved winners required")
	}
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
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: bundle.CatalogSHA256, ReferenceStatsSHA256: sha, Seeds: req.Stochastic.Seeds}
	base, err := setcontext.New(binding, req.Context.PreparedConfig.Text)
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
	captureRoot := filepath.Join(run, "captures")
	if err := os.Mkdir(captureRoot, 0700); err != nil {
		t.Fatal(err)
	}
	provider, err := setcontext.NewEffectEngineProvider(binding, captureRoot)
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
	model, err := setcontext.NewNeutralModel(h, sources)
	if err != nil {
		t.Fatal(err)
	}
	index, err := domain.Build(req, nil)
	if err != nil {
		t.Fatal(err)
	}
	for _, test := range cases {
		var packs [4]domain.Package
		for actor, w := range req.Wearers {
			counts := map[string]int{}
			for _, id := range test.Assignment[actor] {
				uid, ok := index.ArtifactSetUID(id)
				if !ok {
					t.Fatal("missing physical ID", id)
				}
				counts[uid]++
			}
			changes[w.WearerKey] = nil
			keys := []string{}
			for key := range counts {
				keys = append(keys, key)
			}
			sort.Strings(keys)
			for _, uid := range keys {
				count := counts[uid]
				if count < 2 {
					continue
				}
				if count >= 4 {
					count = 4
				} else {
					count = 2
				}
				packs[actor].Sets = append(packs[actor].Sets, contracts.SetRequirement{SetUID: uid, Count: count})
				changes[w.WearerKey] = append(changes[w.WearerKey], setcontext.Set{UID: uid, Count: count})
			}
		}
		target, err := base.Replace(changes)
		if err != nil {
			t.Fatal(err)
		}
		h, codes, err := model.Resolve(target)
		if err != nil || h == nil {
			t.Fatalf("%s model: %v %v", test.Name, err, codes)
		}
		panel, err := h.SearchPanel()
		if err != nil {
			t.Fatal(err)
		}
		view, err := index.ForPackages(packs, test.Assignment, panel.Coordinates())
		if err != nil {
			t.Fatal(err)
		}
		x, err := view.DenseDeltas(test.Assignment)
		if err != nil {
			t.Fatal(err)
		}
		score, err := panel.EvaluateDPS(x)
		if err != nil {
			t.Fatal(err)
		}
		if test.Expected != nil && math.Abs(score-*test.Expected) > 1e-6 {
			t.Fatalf("saved winner formula changed: %.12f vs %.12f", score, *test.Expected)
		}
		out, _ := json.Marshal(map[string]any{"name": test.Name, "formula_dps": score, "assignment": test.Assignment, "packages": packageIdentity(packs), "boundaries": codes})
		fmt.Printf("MATRIX_FORMULA %s\n", out)
	}
}

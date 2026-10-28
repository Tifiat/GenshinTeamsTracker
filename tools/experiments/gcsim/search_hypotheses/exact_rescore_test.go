package main

import (
	"context"
	"encoding/json"
	"genshinteamstracker/native/gcsim_optimizer/internal/allsets"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"math"
	"os"
	"path/filepath"
	"sort"
	"testing"
)

func TestHypothesisExactRescore(t *testing.T) {
	if os.Getenv("GTT_HYPOTHESIS_UPTIME") != "" {
		t.Fatal("oracle must disable approximation in a fresh process")
	}
	ctx := context.Background()
	saved, work := os.Getenv("GTT_HYPOTHESIS_SAVED"), os.Getenv("GTT_HYPOTHESIS_WORK")
	req, sources, err := readSetSources(filepath.Join(saved, "request.json"), filepath.Join(saved, "set-sources.json"))
	if err != nil {
		t.Fatal(err)
	}
	sha, err := contracts.CanonicalSHA256(req)
	if err != nil {
		t.Fatal(err)
	}
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: sources.CatalogSHA256, ReferenceStatsSHA256: sha, Seeds: req.Stochastic.Seeds}
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
	actors := map[string]int{}
	for i, w := range index.Wearers {
		changes[w.WearerKey] = nil
		actors[w.WearerKey] = i
	}
	neutral, err := base.Replace(changes)
	if err != nil {
		t.Fatal(err)
	}
	provider, _ := newHypothesisProvider(binding, "")
	session, err := setcontext.NewSession(provider.Capture, len(req.Stochastic.Seeds))
	if err != nil {
		t.Fatal(err)
	}
	handle, err := session.Resolve(ctx, neutral, nil, nil)
	if err != nil {
		t.Fatal(err)
	}
	model, err := setcontext.NewNeutralModel(handle, sources)
	if err != nil {
		t.Fatal(err)
	}
	var output struct {
		Product struct {
			Candidates []struct {
				Group string      `json:"set_group_key"`
				Rank  int         `json:"alternative_rank"`
				DPS   json.Number `json:"formula_dps"`
				Items []struct {
					Wearer string `json:"wearer_key"`
					Slot   string `json:"slot"`
					ID     int64  `json:"artifact_id"`
				} `json:"artifacts"`
			} `json:"candidates"`
		} `json:"product_result"`
	}
	data, err := os.ReadFile(filepath.Join(work, "all-sets-result.json"))
	if err != nil {
		t.Fatal(err)
	}
	if err = json.Unmarshal(data, &output); err != nil {
		t.Fatal(err)
	}
	slots := map[string]int{"flower": 0, "plume": 1, "sands": 2, "goblet": 3, "circlet": 4}
	rows := []map[string]any{}
	pointChecks := 0
	for _, row := range output.Product.Candidates {
		storedDPS, err := row.DPS.Float64()
		if err != nil {
			t.Fatal(err)
		}
		var assignment domain.Assignment
		var packs [4]domain.Package
		for _, item := range row.Items {
			assignment[actors[item.Wearer]][slots[item.Slot]] = item.ID
		}
		for actor, ids := range assignment {
			counts := map[string]int{}
			for _, id := range ids {
				uid, ok := index.ArtifactSetUID(id)
				if !ok {
					t.Fatal("unknown ID")
				}
				counts[uid]++
			}
			keys := []string{}
			for key, n := range counts {
				if n >= 2 {
					keys = append(keys, key)
				}
			}
			sort.Strings(keys)
			changes[index.Wearers[actor].WearerKey] = nil
			for _, key := range keys {
				count := 2
				if counts[key] >= 4 {
					count = 4
				}
				packs[actor].Sets = append(packs[actor].Sets, contracts.SetRequirement{SetUID: key, Count: count})
				changes[index.Wearers[actor].WearerKey] = append(changes[index.Wearers[actor].WearerKey], setcontext.Set{UID: key, Count: count})
			}
		}
		target, err := base.Replace(changes)
		if err != nil {
			t.Fatal(err)
		}
		h, codes, err := model.Resolve(target)
		if err != nil || h == nil {
			t.Fatalf("exact model: %v %v", err, codes)
		}
		panel, err := h.SearchPanel()
		if err != nil {
			t.Fatal(err)
		}
		view, err := index.ForPackages(packs, assignment, panel.Coordinates())
		if err != nil {
			t.Fatal(err)
		}
		point, err := view.DenseDeltas(assignment)
		if err != nil {
			t.Fatal(err)
		}
		value, err := panel.EvaluateDPS(point)
		if err != nil {
			t.Fatal(err)
		}
		if probe, ok := any(model).(interface {
			HypothesisConstantPoint(*setcontext.Context, []string, []float64) (float64, bool, error)
		}); ok {
			got, available, err := probe.HypothesisConstantPoint(target, view.Coordinates, point)
			if err != nil {
				t.Fatal(err)
			}
			if available {
				pointChecks++
				if math.Abs(got-value) > 1e-9*(1+math.Abs(value)) {
					t.Fatalf("unbound point mismatch: %.12g vs %.12g", got, value)
				}
			}
		}
		rows = append(rows, map[string]any{"group": row.Group, "rank": row.Rank, "approximate_dps": storedDPS, "exact_dps": value, "error": storedDPS - value})
	}
	data, err = json.Marshal(rows)
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(filepath.Join(filepath.Dir(work), "exact-rescore.json"), data, 0600); err != nil {
		t.Fatal(err)
	}
	if _, ok := any(model).(interface {
		HypothesisConstantPoint(*setcontext.Context, []string, []float64) (float64, bool, error)
	}); ok {
		if pointChecks == 0 {
			t.Fatal("no scalar point parity exercised")
		}
		t.Logf("HYPOTHESIS_POINT_PARITY checked=%d", pointChecks)
	}
}

// Research-only replay of one bounded coordinator receipt. Actual ordinary
// measurements use the shared product verifier, not duplicated simulation code.
package allsets

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

func TestCoordinatorOrdinaryFinalists(t *testing.T) {
	root, guideDir, transportDir, captureDir, coordDir, out := os.Getenv("GTT_VERIFY_ROOT"), os.Getenv("GTT_VERIFY_GUIDE"), os.Getenv("GTT_VERIFY_TRANSPORT"), os.Getenv("GTT_VERIFY_CAPTURE"), os.Getenv("GTT_VERIFY_COORDINATOR"), os.Getenv("GTT_VERIFY_OUTPUT")
	read := func(path string) []byte {
		b, e := os.ReadFile(path)
		if e != nil {
			t.Fatal(e)
		}
		return b
	}
	decode := func(path string, v any) {
		if e := json.Unmarshal(read(path), v); e != nil {
			t.Fatal(e)
		}
	}
	var engine contracts.EngineBinding
	decode(filepath.Join(guideDir, "engine.json"), &engine)
	var bundle struct {
		CatalogSHA256 string `json:"catalog_sha256"`
	}
	decode(filepath.Join(guideDir, "sources.json"), &bundle)
	raw := read(filepath.Join(root, ".codex_tmp/selected-2plus2-20260916/run/request.json"))
	req, e := contracts.DecodeRequest(raw)
	if e != nil {
		t.Fatal(e)
	}
	index, e := domain.Build(req, nil)
	if e != nil {
		t.Fatal(e)
	}
	req.Engine = engine
	req.Context.PreparedConfig.Text = string(read(filepath.Join(transportDir, "bloom/config.txt")))
	binding := setcontext.Binding{Engine: engine, CatalogSHA256: bundle.CatalogSHA256, ReferenceStatsSHA256: contracts.TextSHA256(string(raw)), Seeds: req.Stochastic.Seeds}
	base, e := setcontext.New(binding, req.Context.PreparedConfig.Text)
	if e != nil {
		t.Fatal(e)
	}
	var receipt struct {
		Selected  float64 `json:"selected_formula_dps"`
		Finalists []struct {
			DPS        float64 `json:"formula_dps"`
			Packages   []string
			Assignment domain.Assignment
			Context    string `json:"context_sha256"`
		}
	}
	decode(filepath.Join(coordDir, "coordinator-receipt.json"), &receipt)
	dirsFor := func(key string, seed uint64) string {
		if key == base.Key() {
			if seed == binding.Seeds[0] {
				return filepath.Join(transportDir, "bloom")
			}
			return filepath.Join(captureDir, "baseline-"+strconv.FormatUint(seed, 10))
		}
		suffix := filepath.Join("context-"+key, "seed-"+strconv.FormatUint(seed, 10))
		if _, e := os.Stat(filepath.Join(coordDir, suffix)); e == nil {
			return filepath.Join(coordDir, suffix)
		}
		return filepath.Join(captureDir, suffix)
	}
	provider := func(ctx context.Context, c *setcontext.Context) (setcontext.Capture, error) {
		cap := setcontext.Capture{ContextSHA256: c.Key(), ConfigSHA256: c.ConfigSHA256(), EngineBindingSHA256: engine.BindingSHA256}
		for _, seed := range binding.Seeds {
			dir := dirsFor(c.Key(), seed)
			data := read(filepath.Join(dir, "member.json"))
			m, e := contracts.DecodeSeedMember(data)
			if e != nil {
				return cap, e
			}
			var sidecar contracts.EffectInputsOutput
			decode(filepath.Join(dir, "member.json.effects.json"), &sidecar)
			if string(read(filepath.Join(dir, "config.txt"))) != c.Config() || sidecar.MemberContentSHA256 != contracts.TextSHA256(string(data)) {
				return cap, fmt.Errorf("saved finalist context binding changed")
			}
			cap.Members = append(cap.Members, m)
			cap.Effects = append(cap.Effects, sidecar)
		}
		return cap, nil
	}
	session, e := setcontext.NewSession(provider, 8)
	if e != nil {
		t.Fatal(e)
	}
	start := time.Now()
	ctx, cancel := context.WithTimeout(context.Background(), 180*time.Second)
	defer cancel()
	candidates := []Candidate{}
	scores := []search.ScoredAssignment{}
	for _, row := range receipt.Finalists {
		c, e := setcontext.New(binding, string(read(filepath.Join(dirsFor(row.Context, binding.Seeds[0]), "config.txt"))))
		if e != nil || c.Key() != row.Context {
			t.Fatal("context mismatch", e)
		}
		h, e := session.Resolve(ctx, c, nil, nil)
		if e != nil {
			t.Fatal(e)
		}
		panel, e := h.SearchPanel()
		if e != nil {
			t.Fatal(e)
		}
		var packages [4]domain.Package
		for i, key := range row.Packages {
			for _, term := range strings.Split(key, "+") {
				parts := strings.Split(term, ":")
				if len(parts) != 2 {
					t.Fatal("bad package")
				}
				n, e := strconv.Atoi(parts[1])
				if e != nil {
					t.Fatal(e)
				}
				packages[i].Sets = append(packages[i].Sets, contracts.SetRequirement{SetUID: parts[0], Count: n})
			}
		}
		view, e := index.ForPackages(packages, row.Assignment, panel.Coordinates())
		if e != nil {
			t.Fatal(e)
		}
		delta, e := view.DenseDeltas(row.Assignment)
		if e != nil {
			t.Fatal(e)
		}
		dps, e := panel.EvaluateDPS(delta)
		if e != nil || math.Abs(dps-row.DPS) > 1e-8 {
			t.Fatal("formula replay mismatch", dps, row.DPS, e)
		}
		score := search.ScoredAssignment{Assignment: row.Assignment, DPS: row.DPS, Source: "all_sets_context_finalist"}
		scores = append(scores, score)
		candidates = append(candidates, Candidate{score, c, h, view, packages})
	}
	renderer, e := FinalistRenderer(req, base, candidates)
	if e != nil {
		t.Fatal(e)
	}
	replaySeconds := time.Since(start).Seconds()
	screen, e := finalists.VerifyDynamicWavesWithRenderer(ctx, req, scores, renderer, filepath.Join(out, "screen-n128"), 128, 4, runtime.NumCPU())
	if e != nil {
		t.Fatal(e)
	}
	result, e := finalists.VerifyAdaptiveWithRenderer(ctx, req, scores, renderer, filepath.Join(out, "adaptive"), 500, 1000, 4, runtime.NumCPU(), 3, 4)
	if e != nil {
		t.Fatal(e)
	}
	selected := finalists.MeasuredCandidate{}
	for _, row := range result.Candidates {
		if row.FormulaDPS == receipt.Selected {
			selected = row
		}
	}
	if selected.Iterations == 0 {
		t.Fatal("lost Selected baseline")
	}
	payload := map[string]any{"status": "bounded_All_Sets_ordinary_finalists_not_product_UI_acceptance", "new_n1_calls": 0, "replay_seconds": replaySeconds, "screen": screen, "verification": result, "selected": selected, "total_seconds": time.Since(start).Seconds()}
	b, e := json.MarshalIndent(payload, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(out, "ordinary-receipt.json"), b, 0600); e != nil {
		t.Fatal(e)
	}
	t.Log("winner", result.Winner.MeasuredDPS, "formula", result.Winner.FormulaDPS, "Selected", selected.MeasuredDPS, "status", result.Adaptive.Status, "seconds", time.Since(start).Seconds())
}

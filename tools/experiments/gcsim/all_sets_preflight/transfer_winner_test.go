// Research-only controls for the two-context joint-transfer receipt. No product
// default or name-based gameplay logic; replace with ordinary finalist gates.
package allsets

import (
	"context"
	"encoding/json"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
)

func TestJointWinnerResponse(t *testing.T) {
	root, guideDir, captureDir, out := os.Getenv("GTT_TRANSFER_ROOT"), os.Getenv("GTT_TRANSFER_GUIDE"), os.Getenv("GTT_TRANSFER_CAPTURE"), os.Getenv("GTT_TRANSFER_OUTPUT")
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
	req, e := contracts.DecodeRequest(read(filepath.Join(root, ".codex_tmp/selected-2plus2-20260916/run/request.json")))
	if e != nil {
		t.Fatal(e)
	}
	var engine contracts.EngineBinding
	decode(filepath.Join(guideDir, "engine.json"), &engine)
	var report struct {
		Rows []struct {
			Packages []string
			Context  string  `json:"context_sha256"`
			DPS      float64 `json:"formula_dps"`
			Winner   domain.Assignment
		}
	}
	decode(filepath.Join(captureDir, "transfer-capture-receipt.json"), &report)
	if len(report.Rows) != 2 || len(req.Stochastic.Seeds) != 2 {
		t.Fatal("unexpected bounded fixture")
	}
	best := report.Rows[0]
	if report.Rows[1].DPS > best.DPS {
		best = report.Rows[1]
	}
	var packages [4]domain.Package
	for i, key := range best.Packages {
		for _, term := range strings.Split(key, "+") {
			parts := strings.Split(term, ":")
			if len(parts) != 2 {
				t.Fatal("invalid package")
			}
			n, e := strconv.Atoi(parts[1])
			if e != nil {
				t.Fatal(e)
			}
			packages[i].Sets = append(packages[i].Sets, contracts.SetRequirement{SetUID: parts[0], Count: n})
		}
	}
	index, e := domain.Build(req, nil)
	if e != nil {
		t.Fatal(e)
	}
	view, e := index.ForPackages(packages, best.Winner, nil)
	if e != nil {
		t.Fatal(e)
	}
	req.Context.PreparedConfig.Text = string(read(filepath.Join(captureDir, "context-"+best.Context, "seed-"+strconv.FormatUint(req.Stochastic.Seeds[0], 10), "config.txt")))
	for i := range req.Wearers {
		req.Wearers[i].SelectedSetUID = ""
		req.Wearers[i].SelectedSets = packages[i].Sets
	}
	rendered, e := finalists.RenderConfig(req, view, best.Winner, 1, 1)
	if e != nil {
		t.Fatal(e)
	}
	bound, e := engineclient.BindEngine(contracts.OptimizerRequest{Engine: engine})
	if e != nil {
		t.Fatal(e)
	}
	defer func() {
		if e := bound.VerifyUnchanged(); e != nil {
			t.Error(e)
		}
	}()
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	started := time.Now()
	actual := 0.0
	values := []float64{}
	for _, seed := range req.Stochastic.Seeds {
		result, e := bound.RunCompact(ctx, rendered.Text, filepath.Join(out, "winner-"+strconv.FormatUint(seed, 10)), seed, true)
		if e != nil {
			t.Fatal(e)
		}
		damage := 0.0
		for _, ch := range result.Member.Channels {
			d, e := strconv.ParseFloat(ch.BaselineDamage, 64)
			if e != nil {
				t.Fatal(e)
			}
			damage += d
		}
		dps := damage * 1000 / float64(result.Member.DurationMS)
		values = append(values, dps)
		actual += dps / float64(len(req.Stochastic.Seeds))
	}
	residual := math.Abs(actual-best.DPS) / math.Max(1, math.Abs(actual))
	receipt := map[string]any{"formula_dps": best.DPS, "fresh_expected_dps": actual, "per_seed_expected_dps": values, "relative_residual": residual, "new_n1_calls": 2, "ordinary_calls": 0, "wall_seconds": time.Since(started).Seconds(), "context_sha256": best.Context, "packages": best.Packages}
	b, e := json.MarshalIndent(receipt, "", "  ")
	if e != nil {
		t.Fatal(e)
	}
	if e = os.WriteFile(filepath.Join(out, "winner-response-receipt.json"), b, 0600); e != nil {
		t.Fatal(e)
	}
	t.Log(best.DPS, actual, residual)
	if residual > 1e-9 {
		t.Fatal("winner response differs; diagnose before promotion")
	}
}

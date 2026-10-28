package allsets

import (
	"context"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestFinalistsRenderTheirOwnPackagesAndKeepCommonFrame(t *testing.T) {
	index, base, sources, provider, cfg := coordinatorFixture(t)
	result, e := Run(context.Background(), index, base, sources, provider, cfg)
	if e != nil {
		t.Fatal(e)
	}
	bytes, e := os.ReadFile(filepath.Join("..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1", "request_v1.json"))
	if e != nil {
		t.Fatal(e)
	}
	req, e := contracts.DecodeRequest(bytes)
	if e != nil {
		t.Fatal(e)
	}
	req.Context.PreparedConfig.Text = base.Config()
	renderer, e := FinalistRenderer(req, base, result.Finalists)
	if e != nil {
		t.Fatal(e)
	}
	distinct := map[string]bool{}
	for _, c := range result.Finalists {
		rendered, e := renderer(c.Score, 128, 2)
		if e != nil {
			t.Fatal(e)
		}
		if !strings.Contains(rendered.Text, "iteration=128 workers=2") || !strings.Contains(rendered.Text, "# rotation sentinel") || !strings.Contains(rendered.Text, "ignore_burst_energy=true") {
			t.Fatal("frame/options lost")
		}
		for i, p := range c.Packages {
			for _, s := range p.Sets {
				if !strings.Contains(rendered.Text, c.Index.Wearers[i].WearerKey+" add set=\""+s.SetUID+"\"") {
					t.Fatal("wrong set context")
				}
			}
		}
		if contracts.TextSHA256(rendered.Text) != rendered.SHA256 {
			t.Fatal("wrong rendered identity")
		}
		distinct[c.Context.Key()] = true
	}
	if len(distinct) < 2 {
		t.Fatal("test did not cover changed sets")
	}
	bad := result.Finalists[0].Score
	bad.DPS++
	if _, e = renderer(bad, 128, 2); e == nil {
		t.Fatal("modified formula accepted")
	}
	bad = result.Finalists[0].Score
	bad.Assignment[0][0] = -1
	if _, e = renderer(bad, 128, 2); e == nil {
		t.Fatal("unbound assignment accepted")
	}
	req.Engine.ArtifactSHA256 = strings.Repeat("f", 64)
	if _, e = FinalistRenderer(req, base, result.Finalists); e == nil {
		t.Fatal("different engine accepted")
	}
}

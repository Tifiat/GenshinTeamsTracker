// Research-only supplied-account pilot, with explicit saved-byte provenance.
// Never imported by the installed optimizer; no personal item IDs in source.
package allsets

import (
	"context"
	"encoding/json"
	"os"
	"path/filepath"
	"strconv"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

func TestBoundedCoordinatorPilot(t *testing.T) {
	root, guideDir, transportDir, captureDir, out := os.Getenv("GTT_COORD_ROOT"), os.Getenv("GTT_COORD_GUIDE"), os.Getenv("GTT_COORD_TRANSPORT"), os.Getenv("GTT_COORD_CAPTURE"), os.Getenv("GTT_COORD_OUTPUT")
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
	write := func(name string, v any) {
		b, e := json.MarshalIndent(v, "", "  ")
		if e != nil {
			t.Fatal(e)
		}
		if e = os.WriteFile(filepath.Join(out, name), b, 0600); e != nil {
			t.Fatal(e)
		}
	}
	var engine contracts.EngineBinding
	decode(filepath.Join(guideDir, "engine.json"), &engine)
	var bundle seteffects.SourceBundle
	decode(filepath.Join(guideDir, "sources.json"), &bundle)
	sources, e := seteffects.CompileSourceBundle(bundle, engine, bundle.CatalogSHA256)
	if e != nil {
		t.Fatal(e)
	}
	raw := read(filepath.Join(root, ".codex_tmp/selected-2plus2-20260916/run/request.json"))
	req, e := contracts.DecodeRequest(raw)
	if e != nil {
		t.Fatal(e)
	}
	config := string(read(filepath.Join(transportDir, "bloom/config.txt")))
	binding := setcontext.Binding{Engine: engine, CatalogSHA256: bundle.CatalogSHA256, ReferenceStatsSHA256: contracts.TextSHA256(string(raw)), Seeds: req.Stochastic.Seeds}
	base, e := setcontext.New(binding, config)
	if e != nil {
		t.Fatal(e)
	}
	saved := map[string][]string{base.Key(): {filepath.Join(transportDir, "bloom"), filepath.Join(captureDir, "baseline-"+strconv.FormatUint(binding.Seeds[1], 10))}}
	var receipt struct {
		Rows []struct {
			Context string `json:"context_sha256"`
		}
	}
	decode(filepath.Join(captureDir, "transfer-capture-receipt.json"), &receipt)
	for _, row := range receipt.Rows {
		for _, seed := range binding.Seeds {
			saved[row.Context] = append(saved[row.Context], filepath.Join(captureDir, "context-"+row.Context, "seed-"+strconv.FormatUint(seed, 10)))
		}
	}
	actual, e := setcontext.NewEffectEngineProvider(binding, out)
	if e != nil {
		t.Fatal(e)
	}
	defer func() {
		if e := actual.Close(); e != nil {
			t.Error(e)
		}
	}()
	newCalls, reused := 0, 0
	provider := func(ctx context.Context, c *setcontext.Context) (setcontext.Capture, error) {
		dirs, ok := saved[c.Key()]
		if !ok {
			newCalls += len(binding.Seeds)
			return actual.Capture(ctx, c)
		}
		result := setcontext.Capture{ContextSHA256: c.Key(), ConfigSHA256: c.ConfigSHA256(), EngineBindingSHA256: engine.BindingSHA256}
		for i, dir := range dirs {
			configBytes := read(filepath.Join(dir, "config.txt"))
			memberBytes := read(filepath.Join(dir, "member.json"))
			member, e := contracts.DecodeSeedMember(memberBytes)
			if e != nil {
				return result, e
			}
			var sidecar contracts.EffectInputsOutput
			decode(filepath.Join(dir, "member.json.effects.json"), &sidecar)
			if string(configBytes) != c.Config() || sidecar.MemberContentSHA256 != contracts.TextSHA256(string(memberBytes)) || sidecar.InputConfigSHA256 != c.ConfigSHA256() || sidecar.SourceManifestBodySHA256 != engine.SourceManifestSHA256 || member.Seed != binding.Seeds[i] {
				t.Fatal("saved panel identity drift")
			}
			result.Members = append(result.Members, member)
			result.Effects = append(result.Effects, sidecar)
			reused++
		}
		return result, nil
	}
	index, e := domain.Build(req, nil)
	if e != nil {
		t.Fatal(e)
	}
	cfg := CoordinatorConfig{MaxContexts: 4, MaxGuides: 3, SingleQueue: 16, TransferQueue: 6, FinalistLimit: 7, MaxSearchExpansions: 640000, SearchTime: 300 * time.Second, Search: search.DefaultConfig()}
	result, e := Run(context.Background(), index, base, sources, provider, cfg)
	rows := []any{}
	for i, c := range result.Finalists {
		keys := []string{}
		renderReq := req
		renderReq.Wearers = append([]contracts.Wearer(nil), req.Wearers...)
		for actor, p := range c.Packages {
			keys = append(keys, p.Key())
			renderReq.Wearers[actor].SelectedSetUID = ""
			renderReq.Wearers[actor].SelectedSets = p.Sets
		}
		renderReq.Context.PreparedConfig.Text = c.Context.Config()
		rendered, re := finalists.RenderConfig(renderReq, c.Index, c.Score.Assignment, 1, 1)
		if re != nil {
			t.Fatal(re)
		}
		if re = os.WriteFile(filepath.Join(out, "finalist-"+strconv.Itoa(i+1)+".txt"), []byte(rendered.Text), 0600); re != nil {
			t.Fatal(re)
		}
		rows = append(rows, map[string]any{"formula_dps": c.Score.DPS, "packages": keys, "assignment": c.Score.Assignment, "context_sha256": c.Context.Key(), "config_sha256": rendered.SHA256})
	}
	failure := ""
	if e != nil {
		failure = e.Error()
	}
	write("coordinator-receipt.json", map[string]any{"error": failure, "status": "bounded_coordinator_not_ordinary_or_UI_acceptance", "new_n1_calls": newCalls, "reused_members": reused, "selected_formula_dps": result.Selected.Score.DPS, "best_formula_dps": result.Leader.Score.DPS, "stop_reason": result.StopReason, "capture_members": result.CaptureMembers, "search_expansions": result.SearchExpansions, "guides": result.Guides, "queued": result.Queued, "pending": result.Pending, "duplicates": result.SkippedDuplicate, "guide_seconds": result.GuideSeconds, "proposal_seconds": result.ProposalSeconds, "total_seconds": result.TotalSeconds, "work": result.Work, "provider_timings": actual.Timings(), "finalists": rows})
	if e != nil {
		t.Fatal(e)
	}
	if newCalls > 6 || result.CaptureMembers > 8 || result.Leader.Score.DPS < result.Selected.Score.DPS {
		t.Fatal("budget or baseline regression")
	}
	t.Log(result.Selected.Score.DPS, result.Leader.Score.DPS, result.StopReason, result.TotalSeconds, "new", newCalls, "reused", reused)
}

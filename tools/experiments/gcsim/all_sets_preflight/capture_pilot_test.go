package setcontext

// Research-only two-package pilot from the copied bloom fixture. Names below
// select diagnostic witnesses, never product ranking/routing. Search limits are
// intentionally small; this is not account-scale or UI acceptance. Eight new
// compact calls total, with two saved baseline members reused.
import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"reflect"
	"strconv"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
)

func TestAllSetsCapturePilot(t *testing.T) {
	started := time.Now()
	source, matrix, output, repo := os.Getenv("GTT_ALLSETS_SOURCE"), os.Getenv("GTT_ALLSETS_MATRIX"), os.Getenv("GTT_ALLSETS_OUTPUT"), os.Getenv("GTT_ALLSETS_REPO")
	if source == "" || matrix == "" || output == "" || repo == "" {
		t.Fatal("explicit evidence paths required")
	}
	read := func(path string) []byte {
		t.Helper()
		b, e := os.ReadFile(path)
		if e != nil {
			t.Fatal(e)
		}
		return b
	}
	decode := func(path string, out any) {
		t.Helper()
		if e := json.Unmarshal(read(path), out); e != nil {
			t.Fatal(e)
		}
	}
	check := func(e error) {
		t.Helper()
		if e != nil {
			t.Fatal(e)
		}
	}
	ms := func(start time.Time) float64 { return float64(time.Since(start)) / float64(time.Millisecond) }
	var req contracts.OptimizerRequest
	decode(filepath.Join(source, "request.json"), &req)
	check(req.Validate())
	if len(req.Stochastic.Seeds) != 2 {
		t.Fatal("fixture panel changed")
	}
	var catalog struct {
		CatalogFingerprint string `json:"catalog_fingerprint"`
		EngineSHA          string `json:"engine_sha256"`
		Descriptors        []struct {
			SetKey string `json:"set_key"`
		}
	}
	decode(filepath.Join(matrix, "catalog.json"), &catalog)
	if catalog.EngineSHA != req.Engine.ArtifactSHA256 {
		t.Fatal("catalog engine drift")
	}
	var preflight struct {
		Inventory struct {
			Four []string `json:"slot_feasible_4p_keys"`
		} `json:"inventory"`
	}
	decode(filepath.Join(repo, "tests/fixtures/gcsim_optimizer_go_v1/all_sets_preflight_receipt_v1.json"), &preflight)
	four := map[string]bool{}
	for _, s := range preflight.Inventory.Four {
		four[s] = true
	}
	caps := []domain.SetCapability{}
	for _, d := range catalog.Descriptors {
		caps = append(caps, domain.SetCapability{UID: d.SetKey, TwoPiece: true, FourPiece: four[d.SetKey]})
	}
	original := string(read(filepath.Join(source, "prepared-config.txt")))
	if original != req.Context.PreparedConfig.Text {
		t.Fatal("prepared context differs from request")
	}
	var refs []string
	for _, line := range strings.Split(original, "\n") {
		if strings.Contains(line, " add stats ") {
			refs = append(refs, line)
		}
	}
	if len(refs) != 4 {
		t.Fatal("expected four reference rows")
	}
	binding := Binding{Engine: req.Engine, CatalogSHA256: catalog.CatalogFingerprint, ReferenceStatsSHA256: contracts.TextSHA256(strings.Join(refs, "\n")), Seeds: req.Stochastic.Seeds}
	base, err := New(binding, original)
	check(err)
	provider, err := NewEngineProvider(binding, output)
	check(err)
	defer func() { check(provider.Close()) }()
	replayCount := 0
	session, err := NewSession(func(ctx context.Context, c *Context) (Capture, error) {
		if c.Key() != base.Key() {
			return provider.Capture(ctx, c)
		}
		capture := Capture{ContextSHA256: c.Key(), ConfigSHA256: c.ConfigSHA256(), EngineBindingSHA256: req.Engine.BindingSHA256}
		for _, seed := range binding.Seeds {
			suffix := strconv.FormatUint(seed, 10)
			var cr struct {
				ContextSHA string `json:"context_sha256"`
				Seed       string
			}
			decode(filepath.Join(source, "compact-request-"+suffix+".json"), &cr)
			// Selected's saved request binds the full trace-context envelope rather
			// than config bytes alone. req.Validate and the byte check above retain
			// that chain; do not conflate these two valid hash namespaces.
			if cr.ContextSHA != req.Context.TraceContextSHA256 || cr.Seed != suffix {
				t.Fatal("saved baseline binding mismatch")
			}
			member, e := contracts.DecodeSeedMember(read(filepath.Join(source, "compact-member-"+suffix+".json")))
			if e != nil {
				return Capture{}, e
			}
			capture.Members = append(capture.Members, member)
			replayCount++
		}
		return capture, nil
	}, 6)
	check(err)
	ctx, cancel := context.WithTimeout(context.Background(), 210*time.Second)
	defer cancel()
	tick := time.Now()
	baseline, err := session.Resolve(ctx, base, nil, nil)
	check(err)
	baselineMS := ms(tick)
	panel, err := baseline.SearchPanel()
	check(err)
	tick = time.Now()
	index, err := domain.Build(req, panel.Coordinates())
	check(err)
	feasible, err := index.FeasiblePackages(caps, nil)
	check(err)
	domainMS := ms(tick)
	if len(feasible) != 492 {
		t.Fatalf("fixture feasible package count changed: %d", len(feasible))
	}
	var packages [4]domain.Package
	for i, w := range index.Wearers {
		packages[i] = domain.Package{Sets: w.SelectedSets}
	}
	originalIDs := index.Incumbent
	originalDPS, err := panel.EvaluateDPS(make([]float64, len(panel.Coordinates())))
	check(err)
	bound, err := engineclient.BindEngine(req)
	check(err)
	defer func() { check(bound.VerifyUnchanged()) }()
	rows := []map[string]any{}
	for n, witness := range []struct{ Actor, Set string }{{"lauma", "gildeddreams"}, {"kukishinobu", "flowerofparadiselost"}} {
		actor := -1
		for i, w := range index.Wearers {
			if w.WearerKey == witness.Actor {
				actor = i
			}
		}
		if actor < 0 {
			t.Fatal("fixture wearer missing")
		}
		targetPackage := domain.Package{Sets: []contracts.SetRequirement{{SetUID: witness.Set, Count: 4}}}
		tick = time.Now()
		seed, e := index.PackageSeed(index.Incumbent, actor, targetPackage, nil)
		check(e)
		nextPackages := packages
		nextPackages[actor] = targetPackage
		view, e := index.ForPackages(nextPackages, seed, panel.Coordinates())
		check(e)
		counts, e := view.SelectedSetCounts(seed)
		check(e)
		changes := []Set{}
		for _, s := range counts[actor] {
			changes = append(changes, Set{UID: s.SetUID, Count: s.Count})
		}
		target, e := base.Replace(map[string][]Set{witness.Actor: changes})
		check(e)
		proposalMS := ms(tick)
		tick = time.Now()
		h, e := session.Resolve(ctx, target, baseline, nil)
		check(e)
		resolveMS := ms(tick)
		if h.Route() != FreshCapture {
			t.Fatal("unproved set reused graph")
		}
		targetPanel, e := h.SearchPanel()
		check(e)
		view, e = index.ForPackages(nextPackages, seed, targetPanel.Coordinates())
		check(e)
		cfg := search.DefaultConfig()
		cfg.MaxExpandedPerActor = 1000
		solver, e := search.New(view, targetPanel, cfg)
		check(e)
		tick = time.Now()
		step, e := solver.RefineWearer(ctx, seed, actor)
		check(e)
		searchMS := ms(tick)
		if len(step.Finalists) == 0 {
			t.Fatal("empty package search")
		}
		winner := step.Finalists[0]
		for _, v := range step.Finalists {
			if v.DPS > winner.DPS {
				winner = v
			}
		}
		check(view.ValidateAssignment(winner.Assignment))
		for i := range originalIDs {
			if i != actor && winner.Assignment[i] != originalIDs[i] {
				t.Fatal("changed reserved wearer")
			}
		}
		if index.Incumbent != originalIDs {
			t.Fatal("mutated original index")
		}
		// Renderer-only shallow request view. Not presented as a newly validated
		// wire request: engine/context/reference identities stay in the context API.
		renderedReq := req
		renderedReq.Context.PreparedConfig.Text = target.Config()
		renderedReq.Wearers = append([]contracts.Wearer(nil), req.Wearers...)
		for i := range renderedReq.Wearers {
			renderedReq.Wearers[i].SelectedSetUID = ""
			renderedReq.Wearers[i].SelectedSets = nextPackages[i].Sets
		}
		finalConfig, e := finalists.RenderConfig(renderedReq, view, winner.Assignment, 1, 1)
		check(e)
		candidateBinding := binding
		var finalRefs []string
		for _, line := range strings.Split(finalConfig.Text, "\n") {
			if strings.Contains(line, " add stats ") {
				finalRefs = append(finalRefs, line)
			}
		}
		candidateBinding.ReferenceStatsSHA256 = contracts.TextSHA256(strings.Join(finalRefs, "\n"))
		candidateContext, e := New(candidateBinding, finalConfig.Text)
		check(e)
		if !reflect.DeepEqual(candidateContext.Actors(), base.Actors()) {
			t.Fatal("changed initialization order")
		}
		expected := 0.0
		verificationMS := 0.0
		candidateSHA := []string{}
		for _, s := range binding.Seeds {
			energy, e := explicitEnergy(finalConfig.Text)
			check(e)
			tick = time.Now()
			capture, e := bound.RunCompact(ctx, finalConfig.Text, filepath.Join(output, fmt.Sprintf("verify-%d-%d", n, s)), s, energy)
			check(e)
			verificationMS += ms(tick)
			candidateSHA = append(candidateSHA, capture.ResultSHA256)
			sum := 0.0
			for _, ch := range capture.Member.Channels {
				v, e := strconv.ParseFloat(ch.BaselineDamage, 64)
				check(e)
				sum += v
			}
			expected += sum / (float64(capture.Member.DurationMS) / 1000) / float64(len(binding.Seeds))
		}
		cached, e := session.Resolve(ctx, target, baseline, nil)
		check(e)
		if cached.Route() != IdentityReuse {
			t.Fatal("cache missed")
		}
		residual := (winner.DPS - expected) / expected
		rows = append(rows, map[string]any{"actor": witness.Actor, "package": targetPackage.Key(), "context_sha256": target.Key(), "route": h.Route(), "proposal_ms": proposalMS, "capture_compile_ms": resolveMS, "search_ms": searchMS, "verification_ms": verificationMS, "step": step, "winner": winner, "observed_two_seed_expected_dps": expected, "relative_response_residual": residual, "response_within_one_percent": math.Abs(residual) <= .01, "candidate_member_sha256": candidateSHA, "context_hits": h.HitCount(), "opaque_reasons": targetPanel.OpaqueReasons(), "cached_reuse": true})
		t.Logf("%s %s: capture+compile %.0fms, search %.0fms; formula %.2f, fresh %.2f, residual %+.4f%%", witness.Actor, witness.Set, resolveMS, searchMS, winner.DPS, expected, 100*residual)
	}
	if replayCount != 2 || len(provider.Timings()) != 4 || session.AttemptedCaptureMembers() != 6 {
		t.Fatal("call budget mismatch")
	}
	receipt := map[string]any{"schema_version": 1, "date": "2026-09-16", "authority": "docs/handoff/GCSIM_GOB11_GP3_CHECKPOINT.md", "status": "bounded_capture_domain_search_pilot_completed", "engine_sha256": req.Engine.ArtifactSHA256, "catalog_sha256": catalog.CatalogFingerprint, "request_sha256": contracts.TextSHA256(string(read(filepath.Join(source, "request.json")))), "source_inventory_scope": "saved original 2+2 bloom account fixture, not live DB", "feasible_packages": len(feasible), "baseline_dps": originalDPS, "baseline_decode_compile_ms": baselineMS, "domain_build_feasibility_ms": domainMS, "new_engine_calls": 8, "context_capture_members": 4, "candidate_response_members": 4, "replayed_baseline_members": 2, "max_expanded_per_actor": 1000, "context_timings": provider.Timings(), "cases": rows, "elapsed_seconds": time.Since(started).Seconds(), "installed_binary_ui_energy_changed": false, "product_acceptance": false}
	payload, err := json.MarshalIndent(receipt, "", "  ")
	check(err)
	check(os.WriteFile(filepath.Join(output, "capture-pilot-receipt.json"), payload, 0600))
}

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"runtime"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/allsets"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
)

// All Sets is a coarse process boundary: one request/source bundle in, measured
// builds out. It does not run the Selected pipeline for each candidate. UI and
// installation gates are tracked separately in the GP-3 checkpoint.
func optimizeAllSets(ctx context.Context, requestPath, sourcePath, runRoot string) error {
	payload, e := os.ReadFile(requestPath)
	if e != nil {
		return e
	}
	req, e := contracts.DecodeRequest(payload)
	if e != nil {
		return e
	}
	sourceBytes, e := os.ReadFile(sourcePath)
	if e != nil {
		return e
	}
	var bundle seteffects.SourceBundle
	decoder := json.NewDecoder(bytes.NewReader(sourceBytes))
	decoder.DisallowUnknownFields()
	if e = decoder.Decode(&bundle); e != nil {
		return e
	}
	var trailing any
	if decoder.Decode(&trailing) != io.EOF {
		return fmt.Errorf("trailing source envelope data")
	}
	sources, e := seteffects.CompileSourceBundle(bundle, req.Engine, bundle.CatalogSHA256)
	if e != nil {
		return e
	}
	requestSHA, e := contracts.CanonicalSHA256(req)
	if e != nil {
		return e
	}
	progress := newProgressEmitter(os.Stderr, requestSHA)
	if e = progress.emit("validating_request", 0, 5, false); e != nil {
		return e
	}
	if e = os.Mkdir(runRoot, 0700); e != nil {
		return e
	}
	started := time.Now()
	overall, cancel := context.WithTimeout(ctx, time.Duration(req.Budgets.ProductTimeoutMS)*time.Millisecond)
	defer cancel()
	// The outer adapter includes input/source preparation in the600s wall budget.
	// Reserve150s for a single shared finalist panel; search never renews it.
	searchTime := min(420*time.Second, time.Duration(req.Budgets.ProductTimeoutMS)*time.Millisecond-150*time.Second)
	if searchTime <= 0 {
		return fmt.Errorf("All Sets needs time reserved for ordinary finalists")
	}
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: bundle.CatalogSHA256, ReferenceStatsSHA256: requestSHA, Seeds: req.Stochastic.Seeds}
	base, e := setcontext.New(binding, req.Context.PreparedConfig.Text)
	if e != nil {
		return e
	}
	captureRoot := filepath.Join(runRoot, "contexts")
	if e = os.Mkdir(captureRoot, 0700); e != nil {
		return e
	}
	provider, e := setcontext.NewEffectEngineProvider(binding, captureRoot)
	if e != nil {
		return e
	}
	defer provider.Close()
	index, e := domain.Build(req, nil)
	if e != nil {
		return e
	}
	cfg := allsets.CoordinatorConfig{MaxContexts: 8, MaxGuides: 3, SingleQueue: 16, TransferQueue: 6, FinalistLimit: 7, MaxSearchExpansions: 1280000, SearchTime: searchTime, Search: search.DefaultConfig()}
	if e = progress.emit("searching", 1, 5, false); e != nil {
		return e
	}
	result, e := allsets.Run(overall, index, base, sources, provider.Capture, cfg)
	if e != nil {
		return e
	}
	if len(result.Finalists) == 0 {
		return fmt.Errorf("All Sets did not produce a completed formula context")
	}
	renderer, e := allsets.FinalistRenderer(req, base, result.Finalists)
	if e != nil {
		return e
	}
	scores := []search.ScoredAssignment{}
	identities := []any{}
	opaque := []string{}
	for _, c := range result.Finalists {
		scores = append(scores, c.Score)
		identities = append(identities, struct {
			ContextSHA256, GraphSHA256 string
			Assignment                 domain.Assignment
		}{c.Context.Key(), c.Handle.GraphSHA256(), c.Score.Assignment})
		panel, e := c.Handle.SearchPanel()
		if e != nil {
			return e
		}
		opaque = append(opaque, panel.OpaqueReasons()...)
	}
	evidenceSHA, e := contracts.CanonicalSHA256(identities)
	if e != nil {
		return e
	}
	if e = progress.emit("simulating_finalists", 2, 5, false); e != nil {
		return e
	}
	screen, e := finalists.VerifyDynamicWavesWithRenderer(overall, req, scores, renderer, filepath.Join(runRoot, "screen-n128"), 128, 4, runtime.NumCPU())
	if e != nil {
		return e
	}
	if e = progress.emit("validating_finalists", 3, 5, false); e != nil {
		return e
	}
	verification, e := finalists.VerifyAdaptiveWithRenderer(overall, req, scores, renderer, filepath.Join(runRoot, "final-adaptive"), 500, 1000, 4, runtime.NumCPU(), 3, 4)
	if e != nil {
		return e
	}
	if e = provider.Close(); e != nil {
		return e
	}
	warnings := []string{"all_sets_bounded_search"}
	if result.StopReason != "proposal_queue_exhausted" {
		warnings = append(warnings, "all_sets_search_budget_limited")
	}
	if len(result.Boundaries) > 0 {
		warnings = append(warnings, "all_sets_unknown_effects_present")
	}
	path, e := filepath.Abs(filepath.Join(runRoot, "all-sets-result.json"))
	if e != nil {
		return e
	}
	product, e := buildMeasuredProductResult(req, "", evidenceSHA, opaque, warnings, verification, path)
	if e != nil {
		return e
	}
	// Do not serialize raw graphs/handles into the product/debug wrapper. Their
	// exact member files and identities already live in the context directories.
	wrapper := map[string]any{"mode": "all_sets", "product_result": product, "screening": screen, "verification": verification, "context_panel": identities, "search_config": cfg, "search_work": result.Work, "search_stop_reason": result.StopReason, "capture_members": result.CaptureMembers, "search_expansions": result.SearchExpansions, "guides": result.Guides, "queued": result.Queued, "unqueued_across_guides": result.Unqueued, "pending": result.Pending, "guide_seconds": result.GuideSeconds, "proposal_seconds": result.ProposalSeconds, "search_seconds": result.TotalSeconds, "provider_timings": provider.Timings(), "total_elapsed_ms": float64(time.Since(started)) / float64(time.Millisecond)}
	output, e := json.MarshalIndent(wrapper, "", "  ")
	if e != nil {
		return e
	}
	if e = os.WriteFile(path, output, 0600); e != nil {
		return e
	}
	if e = progress.emit("simulating_finalists", 5, 5, false); e != nil {
		return e
	}
	_, e = fmt.Fprintln(os.Stdout, string(output))
	return e
}

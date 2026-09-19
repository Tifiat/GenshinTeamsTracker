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
	"sort"
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
	req, sources, e := readSetSources(requestPath, sourcePath)
	if e != nil {
		return e
	}
	requestSHA, e := contracts.CanonicalSHA256(req)
	if e != nil {
		return e
	}
	return runAllSets(ctx, req, sources, requestSHA, runRoot)
}

func readSetSources(requestPath, sourcePath string) (contracts.OptimizerRequest, *seteffects.SourceCatalog, error) {
	payload, e := os.ReadFile(requestPath)
	if e != nil {
		return contracts.OptimizerRequest{}, nil, e
	}
	req, e := contracts.DecodeRequest(payload)
	if e != nil {
		return contracts.OptimizerRequest{}, nil, e
	}
	sources, e := readSourceCatalog(sourcePath, req.Engine)
	return req, sources, e
}

func readTheorySetSources(requestPath, sourcePath string) (contracts.OptimizerRequest, contracts.OptimizerRequest, *seteffects.SourceCatalog, error) {
	payload, e := os.ReadFile(requestPath)
	if e != nil {
		return contracts.OptimizerRequest{}, contracts.OptimizerRequest{}, nil, e
	}
	raw, expanded, e := contracts.DecodeTheoryRequest(payload)
	if e != nil {
		return contracts.OptimizerRequest{}, contracts.OptimizerRequest{}, nil, e
	}
	sources, e := readSourceCatalog(sourcePath, expanded.Engine)
	return raw, expanded, sources, e
}

func readSourceCatalog(sourcePath string, engine contracts.EngineBinding) (*seteffects.SourceCatalog, error) {
	sourceBytes, e := os.ReadFile(sourcePath)
	if e != nil {
		return nil, e
	}
	var bundle seteffects.SourceBundle
	decoder := json.NewDecoder(bytes.NewReader(sourceBytes))
	decoder.DisallowUnknownFields()
	if e = decoder.Decode(&bundle); e != nil {
		return nil, e
	}
	var trailing any
	if decoder.Decode(&trailing) != io.EOF {
		return nil, fmt.Errorf("trailing source envelope data")
	}
	return seteffects.CompileSourceBundle(bundle, engine, bundle.CatalogSHA256)
}

type setSourceAuditRow struct {
	Key               string   `json:"key"`
	FourPieceModeled  bool     `json:"four_piece_modeled"`
	Recipes           int      `json:"recipes"`
	Terms             int      `json:"terms"`
	UnresolvedRecipes int      `json:"unresolved_recipes"`
	DiscoveryError    string   `json:"discovery_error,omitempty"`
	EffectKinds       []string `json:"effect_kinds"`
}

func summarizeSetSources(sources *seteffects.SourceCatalog) []setSourceAuditRow {
	rows := make([]setSourceAuditRow, 0, len(sources.Sets))
	for _, item := range sources.Sets {
		row := setSourceAuditRow{Key: item.Key, FourPieceModeled: item.FourPieceModeled, Recipes: len(item.Recipes), DiscoveryError: item.Unresolved}
		kinds := map[string]bool{}
		for _, recipe := range item.Recipes {
			row.Terms += len(recipe.Terms)
			if len(recipe.Unresolved) > 0 {
				row.UnresolvedRecipes++
			}
			if recipe.Effect.Kind != "" {
				kinds[recipe.Effect.Kind] = true
			}
		}
		for kind := range kinds {
			row.EffectKinds = append(row.EffectKinds, kind)
		}
		sort.Strings(row.EffectKinds)
		rows = append(rows, row)
	}
	return rows
}

func auditSetSources(requestPath, sourcePath string) error {
	_, sources, e := readSetSources(requestPath, sourcePath)
	if e != nil {
		return e
	}
	output, e := json.MarshalIndent(map[string]any{
		"schema_version":     1,
		"schema_kind":        "gtt_gcsim_optimizer_set_source_audit_v1",
		"sets":               summarizeSetSources(sources),
		"catalog_boundaries": sources.Boundaries,
	}, "", "  ")
	if e != nil {
		return e
	}
	_, e = fmt.Fprintln(os.Stdout, string(output))
	return e
}

func runAllSets(ctx context.Context, req contracts.OptimizerRequest, sources *seteffects.SourceCatalog, requestSHA, runRoot string) error {
	var e error
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
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: sources.CatalogSHA256, ReferenceStatsSHA256: requestSHA, Seeds: req.Stochastic.Seeds}
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
	scout := search.DefaultConfig()
	scout.FirstFrontierWidth = 16
	scout.RecheckFrontierWidth = 4
	scout.MaxExpandedPerActor = 4000
	scout.FinalistLimit = 6
	scout.MaxCycles = 1
	scout.PairFinalistLimit = 12
	cfg := allsets.CoordinatorConfig{MaxContexts: 6, MaxGuides: 3, SingleQueue: 16, TransferQueue: 6, FinalistLimit: 7, DeepContextLimit: 2, MaxSearchExpansions: 1280000, SearchTime: searchTime, Search: search.DefaultConfig(), Scout: scout}
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
	if result.Leader.Energy != nil && !result.Leader.Energy.Feasible {
		return fmt.Errorf("All Sets found no energy-feasible inventory assignment; remaining shortage %.6f", result.Leader.Energy.MaximumShortage)
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
	if result.Leader.Energy != nil {
		var winnerEnergy *contracts.EnergyResult
		for _, candidate := range result.Finalists {
			if candidate.Score.Assignment == verification.Winner.Assignment && candidate.EnergyModel != nil {
				assessment, assessmentErr := candidate.EnergyModel.Assess(candidate.Score.Assignment)
				if assessmentErr != nil {
					return fmt.Errorf("assess measured All Sets winner energy: %w", assessmentErr)
				}
				winnerEnergy = energyProductResult(assessment)
				break
			}
		}
		if winnerEnergy == nil {
			return fmt.Errorf("measured All Sets winner lost its energy assessment")
		}
		product.Energy = winnerEnergy
		if e = product.Validate(); e != nil {
			return fmt.Errorf("validate All Sets energy product result: %w", e)
		}
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

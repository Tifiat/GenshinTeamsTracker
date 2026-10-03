package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
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
	"genshinteamstracker/native/gcsim_optimizer/internal/searchcontrol"
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
	sources, e := readInventorySourceCatalog(sourcePath, req)
	return req, sources, e
}

func readInventorySourceCatalog(path string, req contracts.OptimizerRequest) (*seteffects.SourceCatalog, error) {
	neutral, e := useNeutralAllSets(req, true)
	if e != nil || !neutral {
		return readSourceCatalog(path, req.Engine)
	}
	data, e := os.ReadFile(path)
	if e != nil {
		return nil, e
	}
	var bundle seteffects.SourceBundle
	decoder := json.NewDecoder(bytes.NewReader(data))
	decoder.DisallowUnknownFields()
	if e = decoder.Decode(&bundle); e != nil {
		return nil, e
	}
	var trailing any
	if decoder.Decode(&trailing) != io.EOF {
		return nil, fmt.Errorf("trailing source envelope data")
	}
	return seteffects.CompileSourceBundleCached(bundle, req.Engine, bundle.CatalogSHA256, req.Artifacts, true, configuredRuleCache())
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
	return readSourceCatalogCached(sourcePath, engine, configuredRuleCache())
}

func readSourceCatalogCached(sourcePath string, engine contracts.EngineBinding, cache *seteffects.RuleParseCache) (*seteffects.SourceCatalog, error) {
	bundle, e := readSourceBundle(sourcePath)
	if e != nil {
		return nil, e
	}
	return seteffects.CompileSourceBundleCached(bundle, engine, bundle.CatalogSHA256, nil, false, cache)
}

func readSourceCatalogForCacheWarming(sourcePath string, engine contracts.EngineBinding, cache *seteffects.RuleParseCache) (*seteffects.SourceCatalog, error) {
	bundle, e := readSourceBundle(sourcePath)
	if e != nil {
		return nil, e
	}
	return seteffects.CompileSourceBundleForCacheWarming(bundle, engine, bundle.CatalogSHA256, cache)
}

func readSourceBundle(sourcePath string) (seteffects.SourceBundle, error) {
	sourceBytes, e := os.ReadFile(sourcePath)
	if e != nil {
		return seteffects.SourceBundle{}, e
	}
	var bundle seteffects.SourceBundle
	decoder := json.NewDecoder(bytes.NewReader(sourceBytes))
	decoder.DisallowUnknownFields()
	if e = decoder.Decode(&bundle); e != nil {
		return seteffects.SourceBundle{}, e
	}
	var trailing any
	if decoder.Decode(&trailing) != io.EOF {
		return seteffects.SourceBundle{}, fmt.Errorf("trailing source envelope data")
	}
	return bundle, nil
}

// Distribution preparation uses every source entry, not a particular account's
// inventory. Gameplay/rotation state is deliberately absent from this cache.
func warmSetCache(requestPath, sourcePath, target string) error {
	data, err := os.ReadFile(requestPath)
	if err != nil {
		return err
	}
	req, err := contracts.DecodeRequest(data)
	if err != nil {
		return err
	}
	catalog, err := readSourceCatalogForCacheWarming(sourcePath, req.Engine, seteffects.NewRuleParseCache("", target))
	if err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(map[string]any{
		"engine_sha256": catalog.EngineSHA256, "source_manifest_sha256": catalog.SourceManifestSHA256,
		"catalog_sha256": catalog.CatalogSHA256, "sets": len(catalog.Sets), "rule_parse_cache": catalog.ParseCache,
		"schedule_requirements":      catalog.ScheduleCaptureMetadata(),
		"source_preparation_seconds": catalog.PreparationSeconds,
	})
}

func configuredRuleCache() *seteffects.RuleParseCache {
	return seteffects.NewRuleParseCache(os.Getenv("GTT_RULE_BUNDLED_CACHE_DIR"), os.Getenv("GTT_RULE_CACHE_DIR"))
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
	data, e := os.ReadFile(requestPath)
	if e != nil {
		return e
	}
	req, e := contracts.DecodeRequest(data)
	if e != nil {
		return e
	}
	// Audits explicitly inspect the legacy description too; the neutral product
	// deliberately no longer prepares that unused representation.
	sources, e := readSourceCatalog(sourcePath, req.Engine)
	if e != nil {
		return e
	}
	output, e := json.MarshalIndent(map[string]any{
		"schema_version":     1,
		"schema_kind":        "gtt_gcsim_optimizer_set_source_audit_v1",
		"sets":               summarizeSetSources(sources),
		"catalog_boundaries": sources.Boundaries,
		"rule_parse_cache":   sources.ParseCache,
	}, "", "  ")
	if e != nil {
		return e
	}
	_, e = fmt.Fprintln(os.Stdout, string(output))
	return e
}

func runAllSets(ctx context.Context, req contracts.OptimizerRequest, sources *seteffects.SourceCatalog, requestSHA, runRoot string) error {
	var e error
	neutral, e := useNeutralAllSets(req, sources.HasNeutralRules())
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
	options := req.EffectiveResultOptions()
	overall, cancel := productContext(ctx, req.Budgets.ProductTimeoutMS)
	defer cancel()
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
	searchRequest, canonicalIndex, canonicalBase, e := allsets.CanonicalReference(req, index, base, binding)
	if e != nil {
		return fmt.Errorf("canonical inventory reference: %w", e)
	}
	index, base = canonicalIndex, canonicalBase
	scout := search.DefaultConfig()
	scout.FirstFrontierWidth = 16
	scout.RecheckFrontierWidth = 4
	scout.MaxExpandedPerActor = 12000
	scout.FinalistLimit = 6
	scout.MaxCycles = 1
	scout.PairFinalistLimit = 12
	cfg := allsets.CoordinatorConfig{MaxContexts: 48, MaxGuides: 12, SingleQueue: 0, TransferQueue: 0, FinalistLimit: 7, DeepContextLimit: 3, MaxSearchExpansions: 8000000, SearchTime: 0, Search: search.DefaultConfig(), Scout: scout}
	cfg.ResultGroups, cfg.ResultAlternatives = options.SetGroupLimit, options.BuildsPerGroup
	cfg.Progress = func(stage string, completed, total int) {
		_ = progress.emit(stage, int64(completed), int64(total), false)
	}
	if e = progress.emit("searching", 1, 5, false); e != nil {
		return e
	}
	searchRoute := allsets.Run
	algorithm := "context_capture"
	if neutral {
		searchRoute = allsets.RunNeutral
		algorithm = "neutral_event_effects"
	}
	searchCtx, closeSearch := searchcontrol.Begin(overall)
	result, e := searchRoute(searchCtx, index, base, sources, provider.Capture, cfg)
	closeSearch()
	finishedEarly := searchcontrol.Requested(searchCtx)
	if overall.Err() != nil {
		return overall.Err()
	}
	if finishedEarly && (e == nil || errors.Is(e, context.Canceled)) {
		result.StopReason = "user_requested_finish"
		e = nil
	}
	if e != nil {
		return e
	}
	if len(result.Finalists) == 0 {
		if finishedEarly {
			return fmt.Errorf("finish_no_result: search stopped before a complete feasible build was found")
		}
		return fmt.Errorf("All Sets did not produce a completed formula context")
	}
	if finishedEarly {
		if e = progress.emit("finalizing", 2, 5, false); e != nil {
			return e
		}
	}
	if result.Leader.Energy != nil && !result.Leader.Energy.Feasible {
		if finishedEarly {
			return fmt.Errorf("search finished by user before an energy-feasible complete build was found; no partial build will be reported as verified")
		}
		return fmt.Errorf("All Sets found no energy-feasible inventory assignment; remaining shortage %.6f", result.Leader.Energy.MaximumShortage)
	}
	if !finishedEarly {
		if e = progress.emit("preparing_replacements", 2, 5, false); e != nil {
			return e
		}
		result.Finalists, e = allSetReplacements(overall, result.Finalists, options.BuildsPerGroup-1)
		if e != nil {
			return e
		}
	}
	renderer, e := allsets.FinalistRenderer(searchRequest, base, result.Finalists)
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
	finalStage := "simulating_finalists"
	if options.FastMode {
		finalStage = "validating_finalists"
	}
	if e = progress.emit(finalStage, 2, 5, false); e != nil {
		return e
	}
	// One common-fidelity measurement per finalist. The old n128 pass did not
	// select rows, and the user removed the mandatory128/500/1000 ladder.
	// Near ties retain measured uncertainty; do not silently simulate again.
	var verification *finalists.VerificationResult
	if !options.FastMode {
		measured, err := finalists.VerifyDynamicWavesWithRenderer(overall, req, scores, renderer, filepath.Join(runRoot, "final-n500"), 500, 4, runtime.NumCPU())
		if err != nil {
			return err
		}
		verification = &measured
	}
	if e = progress.emit("validating_finalists", 3, 5, false); e != nil {
		return e
	}
	if e = provider.Close(); e != nil {
		return e
	}
	warnings := []string{"all_sets_bounded_search"}
	if finishedEarly {
		warnings = append(warnings, "search_finished_by_user")
	}
	if result.ReservationDeferred > 0 {
		warnings = append(warnings, "all_sets_joint_reservations_unresolved")
	}
	for _, work := range result.Work {
		if work.BudgetUnexpanded > 0 {
			warnings = append(warnings, "all_sets_inventory_budget_limited")
			break
		}
	}
	if result.StopReason != "proposal_queue_exhausted" {
		warnings = append(warnings, "all_sets_search_budget_limited")
	}
	if allSetsHasUnknownEffectBoundary(result.Boundaries, result.NeutralModel.Unavailable) {
		warnings = append(warnings, "all_sets_unknown_effects_present")
	}
	path, e := filepath.Abs(filepath.Join(runRoot, "all-sets-result.json"))
	if e != nil {
		return e
	}
	product, e := buildGroupedProductResult(req, "", evidenceSHA, opaque, warnings, scores, verification, path)
	if e != nil {
		return e
	}
	if result.Leader.Energy != nil {
		var winnerEnergy *contracts.EnergyResult
		winnerAssignment := productWinnerAssignment(req, product)
		for _, candidate := range result.Finalists {
			if candidate.Score.Assignment == winnerAssignment && candidate.EnergyModel != nil {
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
	wrapper := map[string]any{"mode": "all_sets", "product_result": product, "verification": verification, "context_panel": identities, "search_config": cfg, "search_work": result.Work, "search_stop_reason": result.StopReason, "capture_members": result.CaptureMembers, "search_expansions": result.SearchExpansions, "guides": result.Guides, "queued": result.Queued, "unqueued_across_guides": result.Unqueued, "pending": result.Pending, "guide_seconds": result.GuideSeconds, "proposal_seconds": result.ProposalSeconds, "search_seconds": result.TotalSeconds, "provider_timings": provider.Timings(), "total_elapsed_ms": float64(time.Since(started)) / float64(time.Millisecond)}
	wrapper["reservation_deferred"] = result.ReservationDeferred
	wrapper["rule_parse_cache"] = sources.ParseCache
	wrapper["source_preparation_seconds"] = sources.PreparationSeconds
	wrapper["search_algorithm"] = algorithm
	if neutral {
		wrapper["neutral_cycles"] = result.NeutralCycles
		wrapper["neutral_model"] = result.NeutralModel
		wrapper["neutral_joint_seconds"] = result.NeutralJointSeconds
		wrapper["neutral_package_joint"] = result.NeutralPackageJoint
		wrapper["neutral_stabilization"] = result.NeutralStabilization
		wrapper["effect_boundaries"] = result.Boundaries
	}
	output, e := json.MarshalIndent(wrapper, "", "  ")
	if e != nil {
		return e
	}
	if e = overall.Err(); e != nil {
		return e
	}
	if e = os.WriteFile(path, output, 0600); e != nil {
		return e
	}
	if e = progress.emit("completed", 5, 5, false); e != nil {
		return e
	}
	_, e = fmt.Fprintln(os.Stdout, string(output))
	return e
}

func useNeutralAllSets(req contracts.OptimizerRequest, hasRules bool) (bool, error) {
	infinite, err := setcontext.IgnoreBurstEnergy(req.Context.PreparedConfig.Text)
	if err != nil {
		return false, err
	}
	hasObserver := false
	for _, c := range req.Engine.Capabilities {
		hasObserver = hasObserver || c == contracts.NeutralInputsCapability
	}
	if !infinite || !hasObserver {
		return false, nil // existing energy-aware / installed-engine route
	}
	if !hasRules {
		return false, fmt.Errorf("neutral All Sets requires bound source-rule libraries")
	}
	return true, nil
}

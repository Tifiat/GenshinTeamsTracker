package main

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/allsets"
	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/theory"
)

const (
	theoryResultKind         = "gtt_gcsim_optimizer_theory_result_v1"
	theoryCandidateContexts  = 16
	theoryMarginalCandidates = 6
	theoryMarginalContexts   = theoryMarginalCandidates * 4
	theoryTotalContextLimit  = theoryCandidateContexts + theoryMarginalContexts
)

type theoryPackageRow struct {
	WearerKey string                     `json:"wearer_key"`
	Sets      []contracts.SetRequirement `json:"sets"`
}

type theoryCandidate struct {
	Rank                 int                       `json:"rank"`
	ContextSHA256        string                    `json:"context_sha256"`
	FormulaDPS           float64                   `json:"formula_dps"`
	Packages             []theoryPackageRow        `json:"packages"`
	Allocations          []theory.WearerAllocation `json:"allocations"`
	FormulaEvaluations   int                       `json:"formula_evaluations"`
	MainLayoutsEvaluated int                       `json:"main_layouts_evaluated"`
	Source               string                    `json:"source"`
	OpaqueReasons        []string                  `json:"opaque_reasons"`
	UndistinguishedSlots []string                  `json:"undistinguished_set_slots,omitempty"`
}

type theoryCoverage struct {
	CatalogSets         int `json:"catalog_sets"`
	PackagesConsidered  int `json:"packages_considered"`
	PackagesShortlisted int `json:"packages_shortlisted"`
	ContextsEvaluated   int `json:"contexts_evaluated"`
	ContextsLimit       int `json:"contexts_limit"`
	MarginalContexts    int `json:"marginal_contexts_evaluated"`
	UnqueuedPackages    int `json:"unqueued_packages"`
}

type theoryProductResult struct {
	SchemaVersion    int               `json:"schema_version"`
	SchemaKind       string            `json:"schema_kind"`
	Status           string            `json:"status"`
	RequestSHA256    string            `json:"request_sha256"`
	Candidates       []theoryCandidate `json:"candidates"`
	Coverage         theoryCoverage    `json:"coverage"`
	Warnings         []string          `json:"warnings"`
	Rules            map[string]any    `json:"rules"`
	DebugReceiptPath string            `json:"debug_receipt_path"`
}

type theoryContextSpec struct {
	packages [4]domain.Package
	source   string
}

func optimizeTheory(ctx context.Context, requestPath, sourcePath, runRoot string) error {
	rawRequest, req, sources, err := readTheorySetSources(requestPath, sourcePath)
	if err != nil {
		return err
	}
	requestSHA, err := contracts.CanonicalSHA256(rawRequest)
	if err != nil {
		return err
	}
	progress := newProgressEmitter(os.Stderr, requestSHA)
	if err = progress.emit("validating_request", 0, 4, false); err != nil {
		return err
	}
	if err = os.Mkdir(runRoot, 0700); err != nil {
		return err
	}
	started := time.Now()
	deadline := time.Duration(req.Budgets.ProductTimeoutMS) * time.Millisecond
	if deadline > 300*time.Second {
		deadline = 300 * time.Second
	}
	runCtx, cancel := context.WithTimeout(ctx, deadline)
	defer cancel()
	binding := setcontext.Binding{Engine: req.Engine, CatalogSHA256: sources.CatalogSHA256, ReferenceStatsSHA256: requestSHA, Seeds: req.Stochastic.Seeds}
	base, err := setcontext.New(binding, req.Context.PreparedConfig.Text)
	if err != nil {
		return err
	}
	captureRoot := filepath.Join(runRoot, "contexts")
	if err = os.Mkdir(captureRoot, 0700); err != nil {
		return err
	}
	provider, err := setcontext.NewEffectEngineProvider(binding, captureRoot)
	if err != nil {
		return err
	}
	closed := false
	defer func() {
		if !closed {
			_ = provider.Close()
		}
	}()
	// Spend the same bounded forty-context envelope on a wider primary
	// shortlist and exact marginal checks for the five displayed rows plus one
	// guard candidate. The former 8+32 split often proved an approximate
	// source-guide false positive four times, but never reached the next
	// sensible set for that wearer (for example Golden Troupe or Flower of
	// Paradise Lost). 16+24 explores three diversity rounds per wearer while
	// still proving every package that can reach the UI.
	// Candidate contexts are additional to the neutral base capture. The old
	// limit counted only the candidates and therefore failed on the final legal
	// context after already spending one seed panel on the base.
	session, err := setcontext.NewSession(
		provider.Capture,
		theoryCaptureBudget(theoryTotalContextLimit, len(base.Seeds())),
	)
	if err != nil {
		return err
	}
	if err = progress.emit("compiling_formula", 1, 4, false); err != nil {
		return err
	}
	baseHandle, err := session.Resolve(runCtx, base, nil, nil)
	if err != nil {
		return err
	}
	basePanel, err := baseHandle.SearchPanel()
	if err != nil {
		return err
	}
	index, err := domain.BuildTheory(req, basePanel.Coordinates())
	if err != nil {
		return err
	}
	guide, err := allsets.BuildGuide(runCtx, index, baseHandle, sources)
	if err != nil {
		return err
	}
	catalog := make([]domain.SetCapability, 0, len(sources.Sets))
	for _, set := range sources.Sets {
		catalog = append(catalog, domain.SetCapability{UID: set.Key, TwoPiece: true, FourPiece: set.FourPieceModeled})
	}
	proposals, err := guide.ProposeTheory(runCtx, index, baseHandle, catalog, 32)
	if err != nil {
		return err
	}
	current := currentTheoryPackages(index)
	joint := current
	jointActors := 0
	for actor := 0; actor < 4; actor++ {
		for _, row := range proposals.Queue {
			if row.Wearer == actor {
				joint[actor] = row.Package
				jointActors++
				break
			}
		}
	}
	if jointActors != 4 {
		return fmt.Errorf("theory shortlist did not produce a set package for every wearer")
	}
	specs := []theoryContextSpec{{packages: joint, source: "joint_best_per_wearer"}}
	for _, row := range proposals.Queue {
		if len(specs) >= theoryCandidateContexts {
			break
		}
		if row.Package.Key() == joint[row.Wearer].Key() {
			continue
		}
		packages := joint
		packages[row.Wearer] = row.Package
		specs = append(specs, theoryContextSpec{packages: packages, source: row.Lane})
	}
	if err = progress.emit("searching", 2, 4, false); err != nil {
		return err
	}
	candidates := make([]theoryCandidate, 0, len(specs))
	seen := map[string]bool{}
	candidateByContext := map[string]theoryCandidate{}
	evaluate := func(packages [4]domain.Package, source string) (theoryCandidate, error) {
		target, targetErr := theoryContext(base, current, packages, req.Wearers)
		if targetErr != nil {
			return theoryCandidate{}, targetErr
		}
		if cached, ok := candidateByContext[target.Key()]; ok {
			cached.Source = source
			return cached, nil
		}
		handle := baseHandle
		if target.Key() != base.Key() {
			handle, targetErr = session.Resolve(runCtx, target, baseHandle, nil)
			if targetErr != nil {
				return theoryCandidate{}, targetErr
			}
		}
		panel, panelErr := handle.SearchPanel()
		if panelErr != nil {
			return theoryCandidate{}, panelErr
		}
		solved, solveErr := theory.Solve(panel, req, theory.DefaultConfig())
		if solveErr != nil {
			return theoryCandidate{}, solveErr
		}
		row := theoryCandidate{
			ContextSHA256: target.Key(), FormulaDPS: solved.FormulaDPS,
			Packages: theoryPackageRows(req.Wearers, packages), Allocations: solved.Allocations,
			FormulaEvaluations: solved.FormulaEvaluations, MainLayoutsEvaluated: solved.MainLayoutsEvaluated,
			Source: source, OpaqueReasons: panel.OpaqueReasons(),
		}
		candidateByContext[target.Key()] = row
		seen[target.Key()] = true
		return row, nil
	}
	for _, spec := range specs {
		if err = runCtx.Err(); err != nil {
			break
		}
		target, targetErr := theoryContext(base, current, spec.packages, req.Wearers)
		if targetErr != nil {
			return targetErr
		}
		if seen[target.Key()] {
			continue
		}
		candidate, candidateErr := evaluate(spec.packages, spec.source)
		if candidateErr != nil {
			if errors.Is(candidateErr, context.DeadlineExceeded) {
				break
			}
			return candidateErr
		}
		candidates = append(candidates, candidate)
	}
	if len(candidates) == 0 {
		return fmt.Errorf("theory produced no completed formula context: %w", runCtx.Err())
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].FormulaDPS != candidates[j].FormulaDPS {
			return candidates[i].FormulaDPS > candidates[j].FormulaDPS
		}
		return candidates[i].ContextSHA256 < candidates[j].ContextSHA256
	})
	if len(candidates) > theoryMarginalCandidates {
		candidates = candidates[:theoryMarginalCandidates]
	}
	primaryContexts := len(candidateByContext)
	deadlineExhausted := false
	for i := range candidates {
		minimized, minimizeErr := minimizeTheoryCandidate(
			candidates[i],
			packagesFromRows(candidates[i].Packages),
			req.Wearers,
			func(packages [4]domain.Package) (theoryCandidate, error) {
				return evaluate(packages, "marginal_set_check")
			},
		)
		if minimizeErr != nil {
			if errors.Is(minimizeErr, context.DeadlineExceeded) {
				// Do not surface untouched or only partly checked contexts as if
				// every set package had passed the exact marginal proof. Keep the
				// fully checked prefix. If even rank one cannot finish, retain its
				// proven partial state so the product can still return useful data
				// with the explicit partial-coverage warning.
				if i == 0 {
					candidates[0] = minimized
					candidates = candidates[:1]
				} else {
					candidates = candidates[:i]
				}
				deadlineExhausted = true
				break
			}
			return minimizeErr
		}
		candidates[i] = minimized
	}
	sort.Slice(candidates, func(i, j int) bool {
		if candidates[i].FormulaDPS != candidates[j].FormulaDPS {
			return candidates[i].FormulaDPS > candidates[j].FormulaDPS
		}
		if len(candidates[i].UndistinguishedSlots) != len(candidates[j].UndistinguishedSlots) {
			return len(candidates[i].UndistinguishedSlots) > len(candidates[j].UndistinguishedSlots)
		}
		return candidates[i].ContextSHA256 < candidates[j].ContextSHA256
	})
	unique := candidates[:0]
	seenFinal := map[string]bool{}
	for _, candidate := range candidates {
		if seenFinal[candidate.ContextSHA256] {
			continue
		}
		seenFinal[candidate.ContextSHA256] = true
		unique = append(unique, candidate)
	}
	candidates = unique
	evaluatedContexts := len(candidateByContext)
	if len(candidates) > maxProductCandidates {
		candidates = candidates[:maxProductCandidates]
	}
	for i := range candidates {
		candidates[i].Rank = i + 1
	}
	if err = provider.Close(); err != nil {
		return err
	}
	closed = true
	path, err := filepath.Abs(filepath.Join(runRoot, "theory-result.json"))
	if err != nil {
		return err
	}
	warnings := []string{"theory_guidance_not_owned_artifacts", "bounded_set_shortlist_not_global_optimum"}
	if runCtx.Err() != nil || deadlineExhausted {
		warnings = append(warnings, "theory_context_budget_exhausted_partial_result")
	}
	if len(guide.Boundaries) > 0 {
		warnings = append(warnings, "unknown_set_effect_boundaries_present")
	}
	product := theoryProductResult{
		SchemaVersion: 1, SchemaKind: theoryResultKind, Status: "success", RequestSHA256: requestSHA,
		Candidates: candidates, Coverage: theoryCoverage{len(sources.Sets), proposals.PackagesConsidered, len(proposals.Queue), evaluatedContexts, theoryTotalContextLimit, evaluatedContexts - primaryContexts, proposals.Unqueued},
		Warnings: warnings, Rules: theory.RulesReceipt(), DebugReceiptPath: path,
	}
	wrapper := map[string]any{"mode": "theory", "product_result": product, "proposal_report": proposals, "provider_timings": provider.Timings(), "total_elapsed_ms": float64(time.Since(started)) / float64(time.Millisecond)}
	payload, err := json.MarshalIndent(wrapper, "", "  ")
	if err != nil {
		return err
	}
	if err = os.WriteFile(path, payload, 0600); err != nil {
		return err
	}
	if err = progress.emit("completed", 4, 4, false); err != nil {
		return err
	}
	_, err = fmt.Fprintln(os.Stdout, string(payload))
	return err
}

func packagesFromRows(rows []theoryPackageRow) [4]domain.Package {
	var out [4]domain.Package
	for i := range out {
		if i < len(rows) {
			out[i] = domain.Package{Sets: append([]contracts.SetRequirement(nil), rows[i].Sets...)}
		}
	}
	return out
}

const theoryMarginalRelativeTolerance = 5e-4

// minimizeTheoryCandidate removes a wearer's set package when a fresh engine
// context proves that its marginal contribution is practically
// indistinguishable (at most 0.05% of the candidate DPS). Besides truly
// inactive packages, the small tolerance absorbs compact-formula numerical
// jitter: without it, redundant non-stacking team buffs can survive as a
// misleading farming recommendation because of a few synthetic DPS.
func minimizeTheoryCandidate(
	best theoryCandidate,
	packages [4]domain.Package,
	wearers []contracts.Wearer,
	evaluate func([4]domain.Package) (theoryCandidate, error),
) (theoryCandidate, error) {
	if len(wearers) != 4 || evaluate == nil {
		return theoryCandidate{}, fmt.Errorf("invalid theory marginal minimization input")
	}
	for actor := range packages {
		if len(packages[actor].Sets) == 0 {
			continue
		}
		trial := packages
		trial[actor] = domain.Package{}
		candidate, err := evaluate(trial)
		if err != nil {
			return best, err
		}
		tolerance := math.Max(1e-6, math.Abs(best.FormulaDPS)*theoryMarginalRelativeTolerance)
		if candidate.FormulaDPS+tolerance < best.FormulaDPS {
			continue
		}
		packages = trial
		candidate.Source = best.Source + "+marginal_minimized"
		candidate.UndistinguishedSlots = append(
			append([]string(nil), best.UndistinguishedSlots...),
			wearers[actor].WearerKey,
		)
		best = candidate
	}
	return best, nil
}

func theoryCaptureBudget(candidateContexts, seedCount int) int {
	return (candidateContexts + 1) * seedCount
}

func currentTheoryPackages(index *domain.Index) [4]domain.Package {
	var out [4]domain.Package
	for i, wearer := range index.Wearers {
		out[i] = domain.Package{Sets: append([]contracts.SetRequirement(nil), wearer.SelectedSets...)}
	}
	return out
}

func theoryContext(base *setcontext.Context, current, target [4]domain.Package, wearers []contracts.Wearer) (*setcontext.Context, error) {
	changes := map[string][]setcontext.Set{}
	for actor := 0; actor < 4; actor++ {
		if target[actor].Key() == current[actor].Key() {
			continue
		}
		sets := make([]setcontext.Set, 0, len(target[actor].Sets))
		for _, set := range target[actor].Sets {
			sets = append(sets, setcontext.Set{UID: set.SetUID, Count: set.Count})
		}
		changes[wearers[actor].WearerKey] = sets
	}
	if len(changes) == 0 {
		return base, nil
	}
	return base.Replace(changes)
}

func theoryPackageRows(wearers []contracts.Wearer, packages [4]domain.Package) []theoryPackageRow {
	rows := make([]theoryPackageRow, 4)
	for i := range rows {
		rows[i] = theoryPackageRow{wearers[i].WearerKey, append([]contracts.SetRequirement(nil), packages[i].Sets...)}
	}
	return rows
}

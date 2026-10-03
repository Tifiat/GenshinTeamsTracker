// Command gtt-optimizer owns fixed-panel evaluation and bounded searches.
// Selected reports grouped search results; ordinary runs add one final
// measurement panel, while fast mode remains formula-only. verify-fgbs controls
// remain a development command.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/energy"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/searchcontrol"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	"genshinteamstracker/native/gcsim_optimizer/internal/stochastic"
	"genshinteamstracker/native/gcsim_optimizer/internal/theory"
)

const maxProductCandidates = 5

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	if err := run(ctx, os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(ctx context.Context, arguments []string) error {
	finishProfile, err := startManagedProfile(arguments)
	if err != nil {
		return err
	}
	defer finishProfile()
	if len(arguments) >= 3 && arguments[len(arguments)-2] == "--finish-file" {
		if arguments[0] != "verify-fgbs" && arguments[0] != "optimize-all-sets" {
			return fmt.Errorf("finish-file is supported only for Selected/All Sets")
		}
		ctx = searchcontrol.WithFile(ctx, arguments[len(arguments)-1])
		arguments = arguments[:len(arguments)-2]
	}
	if len(arguments) == 4 && arguments[0] == "aggregate-fixed-panel" {
		return aggregateFixedPanel(ctx, arguments[1], arguments[2], arguments[3])
	}
	if len(arguments) == 5 && arguments[0] == "benchmark-fixed-panel" {
		return benchmarkFixedPanel(ctx, arguments[1], arguments[2], arguments[3], arguments[4])
	}
	if len(arguments) == 4 && arguments[0] == "audit-indexed-panel" {
		return auditIndexedPanel(ctx, arguments[1], arguments[2], arguments[3])
	}
	if len(arguments) == 3 && arguments[0] == "search-fgbs" {
		return searchFGBS(ctx, arguments[1], arguments[2])
	}
	if len(arguments) == 5 && arguments[0] == "verify-fgbs" {
		return verifyFGBS(ctx, arguments[1], arguments[2], arguments[3], arguments[4])
	}
	if len(arguments) == 4 && arguments[0] == "optimize-all-sets" {
		return optimizeAllSets(ctx, arguments[1], arguments[2], arguments[3])
	}
	if len(arguments) == 4 && arguments[0] == "optimize-theory" {
		return optimizeTheory(ctx, arguments[1], arguments[2], arguments[3])
	}
	if len(arguments) == 3 && arguments[0] == "audit-set-sources" {
		return auditSetSources(arguments[1], arguments[2])
	}
	if len(arguments) == 4 && arguments[0] == "warm-set-cache" {
		return warmSetCache(arguments[1], arguments[2], arguments[3])
	}
	if len(arguments) >= 4 && arguments[0] == "audit-theory-panel" {
		return auditTheoryPanel(arguments[1], arguments[2:])
	}
	if len(arguments) >= 4 && arguments[0] == "audit-energy-ledger" {
		return auditEnergyLedger(arguments[1], arguments[2:])
	}
	if len(arguments) != 2 || (arguments[0] != "validate-request" && arguments[0] != "validate-theory-request" && arguments[0] != "validate-seed-member") {
		return fmt.Errorf("usage: gtt-optimizer (validate-request|validate-theory-request|validate-seed-member) INPUT.json | audit-set-sources REQUEST.json SOURCES.json | (aggregate-fixed-panel|benchmark-fixed-panel) REQUEST.json COMPACT.json DELTAS.json [REPEATS] | search-fgbs REQUEST.json COMPACT.json | verify-fgbs REQUEST.json COMPACT.json RUN_ROOT (controls|all) | (optimize-all-sets|optimize-theory) REQUEST.json SOURCES.json RUN_ROOT")
	}
	select {
	case <-ctx.Done():
		return fmt.Errorf("validation cancelled: %w", ctx.Err())
	default:
	}

	payload, err := os.ReadFile(arguments[1])
	if err != nil {
		return fmt.Errorf("read input: %w", err)
	}
	var validated any
	switch arguments[0] {
	case "validate-request":
		request, err := contracts.DecodeRequest(payload)
		if err != nil {
			return fmt.Errorf("validate request: %w", err)
		}
		validated = request
	case "validate-theory-request":
		raw, request, err := contracts.DecodeTheoryRequest(payload)
		if err != nil {
			return fmt.Errorf("validate theory request: %w", err)
		}
		validated = map[string]any{"raw": raw, "expanded": request}
	case "validate-seed-member":
		member, err := contracts.DecodeSeedMember(payload)
		if err != nil {
			return fmt.Errorf("validate seed member: %w", err)
		}
		if err := stochastic.ValidateZeroDeltaBaseline(member); err != nil {
			return fmt.Errorf("validate seed member baseline: %w", err)
		}
		validated = member
	}
	select {
	case <-ctx.Done():
		return fmt.Errorf("validation cancelled: %w", ctx.Err())
	default:
	}

	identity, err := contracts.CanonicalSHA256(validated)
	if err != nil {
		return fmt.Errorf("identify input: %w", err)
	}
	fmt.Fprintln(os.Stdout, identity)
	return nil
}

func auditEnergyLedger(requestPath string, memberPaths []string) error {
	payload, err := os.ReadFile(requestPath)
	if err != nil {
		return err
	}
	request, err := contracts.DecodeRequest(payload)
	if err != nil {
		return err
	}
	if len(memberPaths) != len(request.Stochastic.Seeds) {
		return fmt.Errorf("one member path required per request seed")
	}
	members := make([]contracts.IRSeedMember, len(memberPaths))
	for index, path := range memberPaths {
		memberPayload, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		members[index], readErr = contracts.DecodeSeedMember(memberPayload)
		if readErr != nil {
			return readErr
		}
	}
	artifactIndex, err := domain.Build(request, nil)
	if err != nil {
		return err
	}
	model, err := energy.Compile(artifactIndex, members)
	if err != nil {
		return err
	}
	assessment, err := model.Assess(artifactIndex.Incumbent)
	if err != nil {
		return err
	}
	return json.NewEncoder(os.Stdout).Encode(assessment)
}

func auditTheoryPanel(requestPath string, memberPaths []string) error {
	payload, err := os.ReadFile(requestPath)
	if err != nil {
		return err
	}
	request, err := contracts.DecodeRequest(payload)
	if err != nil {
		return err
	}
	if len(memberPaths) != len(request.Stochastic.Seeds) {
		return fmt.Errorf("one member path required per request seed")
	}
	members := make([]contracts.IRSeedMember, len(memberPaths))
	for i, path := range memberPaths {
		memberPayload, readErr := os.ReadFile(path)
		if readErr != nil {
			return readErr
		}
		members[i], readErr = contracts.DecodeSeedMember(memberPayload)
		if readErr != nil {
			return readErr
		}
	}
	actors := make([]string, len(request.Wearers))
	for i, wearer := range request.Wearers {
		actors[i] = wearer.WearerKey
	}
	panel, err := evaluator.CompileMembers(actors, request.Stochastic.Seeds, members)
	if err != nil {
		return err
	}
	started := time.Now()
	result, err := theory.Solve(panel, request, theory.DefaultConfig())
	if err != nil {
		return err
	}
	output, err := json.MarshalIndent(map[string]any{"elapsed_ms": float64(time.Since(started)) / float64(time.Millisecond), "coordinates": len(panel.Coordinates()), "result": result}, "", "  ")
	if err != nil {
		return err
	}
	_, err = fmt.Fprintln(os.Stdout, string(output))
	return err
}

func verifyFGBS(ctx context.Context, requestPath, compactPath, runRoot, mode string) error {
	if mode != "controls" && mode != "all" {
		return fmt.Errorf("verify-fgbs mode must be controls or all")
	}
	requestPayload, err := os.ReadFile(requestPath)
	if err != nil {
		return fmt.Errorf("read request: %w", err)
	}
	request, err := contracts.DecodeRequest(requestPayload)
	if err != nil {
		return fmt.Errorf("decode request: %w", err)
	}
	requestSHA256, err := contracts.CanonicalSHA256(request)
	if err != nil {
		return fmt.Errorf("identify request: %w", err)
	}
	progress := newProgressEmitter(os.Stderr, requestSHA256)
	if err := progress.emit("validating_request", 0, 5, false); err != nil {
		return err
	}
	compactPayload, err := os.ReadFile(compactPath)
	if err != nil {
		return fmt.Errorf("read compact IR: %w", err)
	}
	compact, err := contracts.DecodeCompactIR(compactPayload)
	if err != nil {
		return fmt.Errorf("decode compact IR: %w", err)
	}
	if err := progress.emit("compiling_formula", 0, 5, false); err != nil {
		return err
	}
	overall, cancel := productContext(ctx, request.Budgets.ProductTimeoutMS)
	defer cancel()
	compileStarted := time.Now()
	panel, err := evaluator.Compile(request, compact)
	if err != nil {
		return fmt.Errorf("compile panel: %w", err)
	}
	artifactIndex, err := domain.Build(request, panel.Coordinates())
	if err != nil {
		return fmt.Errorf("build artifact index: %w", err)
	}
	energyModel, err := compileEnergyConstraint(request, artifactIndex, compact.Members)
	if err != nil {
		return fmt.Errorf("compile energy constraint: %w", err)
	}
	compileElapsed := time.Since(compileStarted)
	searchStarted := time.Now()
	options := request.EffectiveResultOptions()
	if err := progress.emit("searching", 1, 5, false); err != nil {
		return err
	}
	searchCtx, closeSearch := searchcontrol.Begin(overall)
	searchResult, fixedSearch, err := runSelectedSearch(searchCtx, artifactIndex, panel, energyModel, options.BuildsPerGroup)
	closeSearch()
	finishedEarly := searchcontrol.Requested(searchCtx)
	if overall.Err() != nil {
		return overall.Err()
	}
	if finishedEarly && (err == nil || errors.Is(err, context.Canceled)) {
		searchResult.StopReason = "user_requested_finish"
		err = nil
	}
	if err != nil {
		return fmt.Errorf("FGBS search: %w", err)
	}
	if finishedEarly {
		if len(searchResult.Finalists) == 0 {
			return fmt.Errorf("finish_no_result: search stopped before a complete feasible build was found")
		}
		if err := progress.emit("finalizing", 1, 5, false); err != nil {
			return err
		}
	}
	if energyModel != nil && (searchResult.Energy == nil || !searchResult.Energy.Feasible) {
		if finishedEarly {
			return fmt.Errorf("search finished by user before an energy-feasible complete build was found; no partial build will be reported as verified")
		}
		shortage := 0.0
		if searchResult.Energy != nil {
			shortage = searchResult.Energy.MaximumShortage
		}
		return fmt.Errorf("FGBS found no energy-feasible inventory assignment; remaining artifact ER deficit %.6f", shortage)
	}
	searchElapsed := time.Since(searchStarted)
	candidates := searchResult.Finalists
	var screening *finalists.VerificationResult
	verificationPolicy := "controls_n1000"
	if mode == "controls" {
		candidates = controlCandidates(searchResult)
	} else {
		candidates = fixedSelectedFinalists(searchResult)
		if !finishedEarly && len(candidates) > 0 {
			alternatives, e := search.SingleReplacements(overall, artifactIndex, panel, candidates[0], options.BuildsPerGroup-1, energyModel)
			if e != nil {
				return e
			}
			candidates = append(candidates[:1:1], alternatives...)
		}
		if len(candidates) > options.BuildsPerGroup {
			candidates = candidates[:options.BuildsPerGroup]
		}
		verificationPolicy = "single_n500"
	}
	if err := os.Mkdir(runRoot, 0o700); err != nil {
		return err
	}
	var verification *finalists.VerificationResult
	finalStage := "simulating_finalists"
	if options.FastMode {
		finalStage = "validating_finalists"
	}
	if err := progress.emit(finalStage, 2, 5, false); err != nil {
		return err
	}
	if options.FastMode {
		verificationPolicy = "formula_only"
	} else {
		iterations := 500
		if mode == "controls" {
			iterations = 1000
		}
		measured, verifyErr := finalists.VerifyDynamicWaves(overall, request, artifactIndex, candidates, filepath.Join(runRoot, "final-n500"), iterations, 4, runtime.NumCPU())
		if verifyErr != nil {
			return verifyErr
		}
		verification = &measured
	}
	if err := progress.emit(finalStage, 4, 5, false); err != nil {
		return err
	}
	debugReceiptPath, err := filepath.Abs(filepath.Join(runRoot, "gob7-result.json"))
	if err != nil {
		return fmt.Errorf("resolve debug receipt path: %w", err)
	}
	compactSHA, err := contracts.CanonicalSHA256(compact)
	if err != nil {
		return err
	}
	productResult, err := buildGroupedProductResult(request, compactSHA, "", searchResult.OpaqueReasons, nil, candidates, verification, debugReceiptPath)
	if err != nil {
		return err
	}
	if energyModel != nil {
		winner := productWinnerAssignment(request, productResult)
		assessment, e := energyModel.Assess(winner)
		if e != nil {
			return e
		}
		productResult.Energy = energyProductResult(assessment)
	}
	productResult.Warnings = append(productResult.Warnings, fixedSelectedWarnings(searchResult, fixedSearch)...)
	if finishedEarly {
		productResult.Warnings = append(productResult.Warnings, "search_finished_by_user")
	}
	sort.Strings(productResult.Warnings)
	if err := productResult.Validate(); err != nil {
		return fmt.Errorf("validate Selected search warnings: %w", err)
	}
	payload := struct {
		Mode               string                        `json:"mode"`
		Search             search.Result                 `json:"search"`
		Screening          *finalists.VerificationResult `json:"screening,omitempty"`
		Verification       *finalists.VerificationResult `json:"verification,omitempty"`
		ProductResult      contracts.OptimizerResult     `json:"product_result"`
		CompileElapsedMS   float64                       `json:"compile_elapsed_ms"`
		SearchElapsedMS    float64                       `json:"search_elapsed_ms"`
		TotalElapsedMS     float64                       `json:"total_elapsed_ms"`
		FixedSearch        *selectedSearchReceipt        `json:"fixed_search,omitempty"`
		VerificationPolicy string                        `json:"verification_policy"`
	}{mode, searchResult, screening, verification, productResult, float64(compileElapsed) / float64(time.Millisecond), float64(searchElapsed) / float64(time.Millisecond), float64(compileElapsed+searchElapsed) / float64(time.Millisecond), fixedSearch, verificationPolicy}
	if verification != nil {
		payload.TotalElapsedMS += verification.TotalElapsedMS
	}
	if screening != nil {
		payload.TotalElapsedMS += screening.TotalElapsedMS
	}
	receipt, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return fmt.Errorf("encode verification receipt: %w", err)
	}
	receipt = append(receipt, '\n')
	if err := overall.Err(); err != nil {
		return err
	}
	if err := os.WriteFile(filepath.Join(runRoot, "gob7-result.json"), receipt, 0o600); err != nil {
		return fmt.Errorf("write verification receipt: %w", err)
	}
	if err := progress.emit("completed", 5, 5, false); err != nil {
		return err
	}
	_, err = os.Stdout.Write(receipt)
	return err
}

type progressEmitter struct {
	writer        io.Writer
	requestSHA256 string
	started       time.Time
	sequence      int64
}

func newProgressEmitter(writer io.Writer, requestSHA256 string) *progressEmitter {
	return &progressEmitter{writer: writer, requestSHA256: requestSHA256, started: time.Now()}
}

func (emitter *progressEmitter) emit(stage string, completed, total int64, cancelled bool) error {
	record := contracts.ProgressRecord{
		SchemaVersion:         contracts.SchemaVersion,
		SchemaKind:            contracts.ProgressSchemaKind,
		RequestSHA256:         emitter.requestSHA256,
		Sequence:              emitter.sequence,
		Stage:                 stage,
		CompletedWork:         completed,
		TotalWork:             total,
		ElapsedMS:             time.Since(emitter.started).Milliseconds(),
		CancellationRequested: cancelled,
	}
	if err := record.Validate(); err != nil {
		return fmt.Errorf("validate progress: %w", err)
	}
	emitter.sequence++
	if err := json.NewEncoder(emitter.writer).Encode(record); err != nil {
		return fmt.Errorf("write progress: %w", err)
	}
	return nil
}

func productWinnerAssignment(request contracts.OptimizerRequest, result contracts.OptimizerResult) domain.Assignment {
	var assignment domain.Assignment
	for i, wearer := range request.Wearers {
		for j, slot := range wearer.CurrentArtifacts {
			for _, item := range result.Winner {
				if item.WearerKey == wearer.WearerKey && item.Slot == slot.Slot {
					assignment[i][j] = item.ArtifactID
					break
				}
			}
		}
	}
	return assignment
}

func productAssignments(request contracts.OptimizerRequest, assignment domain.Assignment) []contracts.ArtifactAssignment {
	result := make([]contracts.ArtifactAssignment, 0, 20)
	for wearerIndex, wearer := range request.Wearers {
		for slotIndex, current := range wearer.CurrentArtifacts {
			result = append(result, contracts.ArtifactAssignment{
				WearerKey:  wearer.WearerKey,
				Slot:       current.Slot,
				ArtifactID: assignment[wearerIndex][slotIndex],
			})
		}
	}
	return result
}

func compileEnergyConstraint(request contracts.OptimizerRequest, index *domain.Index, members []contracts.IRSeedMember) (*energy.Model, error) {
	ignore, err := setcontext.IgnoreBurstEnergy(request.Context.PreparedConfig.Text)
	if err != nil {
		return nil, err
	}
	if ignore {
		return nil, nil
	}
	found := false
	for _, capability := range request.Engine.Capabilities {
		found = found || capability == "gtt_energy_ledger_v1"
	}
	if !found {
		return nil, fmt.Errorf("finite energy requires gtt_energy_ledger_v1")
	}
	return energy.Compile(index, members)
}

func energyProductResult(assessment energy.Assessment) *contracts.EnergyResult {
	result := &contracts.EnergyResult{
		Feasible: assessment.Feasible, MaximumShortage: decimalText(assessment.MaximumShortage),
		Wearers: make([]contracts.EnergyWearerResult, 0, len(assessment.Wearers)),
	}
	for _, wearer := range assessment.Wearers {
		row := contracts.EnergyWearerResult{
			WearerKey: wearer.WearerKey, ArtifactER: decimalText(wearer.ArtifactER),
			RequiredArtifactER: decimalText(wearer.RequiredArtifactER), Margin: decimalText(wearer.Margin),
			Feasible: wearer.Feasible, MaximumShortage: decimalText(wearer.MaximumShortage),
			BurstDeadlines:   wearer.BurstDeadlines,
			UncertaintyCodes: append([]string(nil), wearer.UncertaintyCodes...),
			Sources:          make([]contracts.EnergySourceResult, 0, len(wearer.Sources)),
		}
		for _, source := range wearer.Sources {
			row.Sources = append(row.Sources, contracts.EnergySourceResult{
				Source: source.Source, ParticleRaw: decimalText(source.ParticleRaw), FlatObserved: decimalText(source.FlatObserved),
			})
		}
		result.Wearers = append(result.Wearers, row)
	}
	return result
}

func decimalText(value float64) string {
	return strconv.FormatFloat(value, 'f', -1, 64)
}

func uniqueCandidates(rows []search.ScoredAssignment) []search.ScoredAssignment {
	output := make([]search.ScoredAssignment, 0, len(rows))
	seen := make(map[domain.Assignment]struct{}, len(rows))
	for _, row := range rows {
		if _, exists := seen[row.Assignment]; exists {
			continue
		}
		seen[row.Assignment] = struct{}{}
		output = append(output, row)
	}
	return output
}

func minInt(values ...int) int {
	value := values[0]
	for _, candidate := range values[1:] {
		if candidate < value {
			value = candidate
		}
	}
	return value
}

func maxInt(a, b int) int {
	if a > b {
		return a
	}
	return b
}

func controlCandidates(result search.Result) []search.ScoredAssignment {
	rows := []search.ScoredAssignment{
		{Assignment: result.Initial.Assignment, DPS: result.Initial.DPS, Source: "control_current"},
		{Assignment: result.Leader.Assignment, DPS: result.Leader.DPS, Source: "control_go_leader"},
	}
	if len(result.Finalists) > 0 {
		tail := result.Finalists[len(result.Finalists)-1]
		tail.Source = "control_formula_tail"
		rows = append(rows, tail)
	}
	output := rows[:0]
	seen := make(map[domain.Assignment]struct{}, len(rows))
	for _, row := range rows {
		if _, exists := seen[row.Assignment]; exists {
			continue
		}
		seen[row.Assignment] = struct{}{}
		output = append(output, row)
	}
	return output
}

func searchFGBS(ctx context.Context, requestPath, compactPath string) error {
	requestPayload, err := os.ReadFile(requestPath)
	if err != nil {
		return fmt.Errorf("read request: %w", err)
	}
	request, err := contracts.DecodeRequest(requestPayload)
	if err != nil {
		return fmt.Errorf("decode request: %w", err)
	}
	compactPayload, err := os.ReadFile(compactPath)
	if err != nil {
		return fmt.Errorf("read compact IR: %w", err)
	}
	compact, err := contracts.DecodeCompactIR(compactPayload)
	if err != nil {
		return fmt.Errorf("decode compact IR: %w", err)
	}
	preparedAt := time.Now()
	panel, err := evaluator.Compile(request, compact)
	if err != nil {
		return fmt.Errorf("compile panel: %w", err)
	}
	artifactIndex, err := domain.Build(request, panel.Coordinates())
	if err != nil {
		return fmt.Errorf("build artifact index: %w", err)
	}
	energyModel, err := compileEnergyConstraint(request, artifactIndex, compact.Members)
	if err != nil {
		return fmt.Errorf("compile energy constraint: %w", err)
	}
	engine, err := search.New(artifactIndex, panel, search.DefaultConfig(), energyModel)
	if err != nil {
		return err
	}
	compileElapsed := time.Since(preparedAt)
	searchContext, cancel := productContext(ctx, request.Budgets.ProductTimeoutMS)
	defer cancel()
	searchStarted := time.Now()
	result, err := engine.Run(searchContext)
	searchElapsed := time.Since(searchStarted)
	if err != nil {
		return fmt.Errorf("FGBS search after %s: %w", searchElapsed, err)
	}
	return json.NewEncoder(os.Stdout).Encode(struct {
		Result           search.Result `json:"result"`
		CompileElapsedMS float64       `json:"compile_elapsed_ms"`
		SearchElapsedMS  float64       `json:"search_elapsed_ms"`
		TotalElapsedMS   float64       `json:"total_elapsed_ms"`
	}{result, float64(compileElapsed) / float64(time.Millisecond), float64(searchElapsed) / float64(time.Millisecond), float64(compileElapsed+searchElapsed) / float64(time.Millisecond)})
}

type indexedAuditScore struct {
	Assignment [4][5]int64 `json:"assignment"`
	MeanDPS    float64     `json:"mean_dps"`
}

func auditIndexedPanel(ctx context.Context, requestPath, compactPath, repeatText string) error {
	repeats, err := strconv.Atoi(repeatText)
	if err != nil || repeats < 1 || repeats > 10000 {
		return fmt.Errorf("indexed audit repeats must be between 1 and 10000")
	}
	requestPayload, err := os.ReadFile(requestPath)
	if err != nil {
		return fmt.Errorf("read request: %w", err)
	}
	request, err := contracts.DecodeRequest(requestPayload)
	if err != nil {
		return fmt.Errorf("decode request: %w", err)
	}
	compactPayload, err := os.ReadFile(compactPath)
	if err != nil {
		return fmt.Errorf("read compact IR: %w", err)
	}
	compact, err := contracts.DecodeCompactIR(compactPayload)
	if err != nil {
		return fmt.Errorf("decode compact IR: %w", err)
	}
	compileStarted := time.Now()
	panel, err := evaluator.Compile(request, compact)
	if err != nil {
		return fmt.Errorf("compile panel: %w", err)
	}
	artifactIndex, err := domain.Build(request, panel.Coordinates())
	if err != nil {
		return fmt.Errorf("build artifact index: %w", err)
	}
	compileElapsed := time.Since(compileStarted)
	incumbentDeltas, err := artifactIndex.DenseDeltas(artifactIndex.Incumbent)
	if err != nil {
		return err
	}
	incumbent, err := panel.Evaluate(incumbentDeltas)
	if err != nil {
		return err
	}

	broad := make([]float64, len(panel.Coordinates()))
	for index := range broad {
		broad[index] = 0.01
	}
	broadScore, err := panel.Evaluate(broad)
	if err != nil {
		return err
	}
	swaps := make([]indexedAuditScore, 0, 20)
	for wearerIndex := 0; wearerIndex < 4; wearerIndex++ {
		for slotIndex := 0; slotIndex < 5; slotIndex++ {
			for _, artifactID := range artifactIndex.CandidateIDsBySlot[slotIndex] {
				if artifactID == artifactIndex.Incumbent[wearerIndex][slotIndex] {
					continue
				}
				assignment := artifactIndex.Incumbent
				assignment[wearerIndex][slotIndex] = artifactID
				if artifactIndex.ValidateAssignment(assignment) != nil {
					continue
				}
				deltas, err := artifactIndex.DenseDeltas(assignment)
				if err != nil {
					return err
				}
				score, err := panel.Evaluate(deltas)
				if err != nil {
					return err
				}
				swaps = append(swaps, indexedAuditScore{Assignment: assignment, MeanDPS: score.MeanDPS})
				break
			}
		}
	}
	hotStarted := time.Now()
	for index := 0; index < repeats; index++ {
		select {
		case <-ctx.Done():
			return fmt.Errorf("indexed audit cancelled: %w", ctx.Err())
		default:
		}
		if _, err := panel.Evaluate(incumbentDeltas); err != nil {
			return err
		}
	}
	hotElapsed := time.Since(hotStarted)
	return json.NewEncoder(os.Stdout).Encode(struct {
		ArtifactCount       int                 `json:"artifact_count"`
		CoordinateCount     int                 `json:"coordinate_count"`
		SingleSwaps         []indexedAuditScore `json:"single_swaps"`
		IncumbentDPS        float64             `json:"incumbent_dps"`
		BroadProfileDPS     float64             `json:"broad_profile_dps"`
		CompileElapsedMS    float64             `json:"compile_elapsed_ms"`
		Repeats             int                 `json:"repeats"`
		HotElapsedMS        float64             `json:"hot_elapsed_ms"`
		MeanHotEvaluationMS float64             `json:"mean_hot_evaluation_ms"`
	}{
		ArtifactCount: len(artifactIndex.Artifacts), CoordinateCount: len(panel.Coordinates()),
		SingleSwaps: swaps, IncumbentDPS: incumbent.MeanDPS, BroadProfileDPS: broadScore.MeanDPS,
		CompileElapsedMS: float64(compileElapsed) / float64(time.Millisecond), Repeats: repeats,
		HotElapsedMS: float64(hotElapsed) / float64(time.Millisecond), MeanHotEvaluationMS: float64(hotElapsed) / float64(time.Millisecond) / float64(repeats),
	})
}

func aggregateFixedPanel(ctx context.Context, requestPath, compactPath, deltasPath string) error {
	select {
	case <-ctx.Done():
		return fmt.Errorf("aggregation cancelled: %w", ctx.Err())
	default:
	}
	request, compact, deltas, err := loadPanel(requestPath, compactPath, deltasPath)
	if err != nil {
		return err
	}
	result, err := stochastic.AggregateFixedPanel(request, compact, deltas)
	if err != nil {
		return fmt.Errorf("aggregate fixed panel: %w", err)
	}
	select {
	case <-ctx.Done():
		return fmt.Errorf("aggregation cancelled: %w", ctx.Err())
	default:
	}
	encoder := json.NewEncoder(os.Stdout)
	encoder.SetEscapeHTML(false)
	if err := encoder.Encode(result); err != nil {
		return fmt.Errorf("encode aggregate result: %w", err)
	}
	return nil
}

func loadPanel(requestPath, compactPath, deltasPath string) (contracts.OptimizerRequest, contracts.CompactIR, map[string]float64, error) {
	requestPayload, err := os.ReadFile(requestPath)
	if err != nil {
		return contracts.OptimizerRequest{}, contracts.CompactIR{}, nil, fmt.Errorf("read request: %w", err)
	}
	request, err := contracts.DecodeRequest(requestPayload)
	if err != nil {
		return contracts.OptimizerRequest{}, contracts.CompactIR{}, nil, fmt.Errorf("decode request: %w", err)
	}
	compactPayload, err := os.ReadFile(compactPath)
	if err != nil {
		return contracts.OptimizerRequest{}, contracts.CompactIR{}, nil, fmt.Errorf("read compact IR: %w", err)
	}
	compact, err := contracts.DecodeCompactIR(compactPayload)
	if err != nil {
		return contracts.OptimizerRequest{}, contracts.CompactIR{}, nil, fmt.Errorf("decode compact IR: %w", err)
	}
	deltasPayload, err := os.ReadFile(deltasPath)
	if err != nil {
		return contracts.OptimizerRequest{}, contracts.CompactIR{}, nil, fmt.Errorf("read artifact deltas: %w", err)
	}
	var deltas map[string]float64
	decoder := json.NewDecoder(bytes.NewReader(deltasPayload))
	if err := decoder.Decode(&deltas); err != nil {
		return contracts.OptimizerRequest{}, contracts.CompactIR{}, nil, fmt.Errorf("decode artifact deltas: %w", err)
	}
	if deltas == nil {
		return contracts.OptimizerRequest{}, contracts.CompactIR{}, nil, fmt.Errorf("artifact deltas must be an object")
	}
	var trailing any
	if err := decoder.Decode(&trailing); err != io.EOF {
		return contracts.OptimizerRequest{}, contracts.CompactIR{}, nil, fmt.Errorf("decode artifact deltas trailing data")
	}
	return request, compact, deltas, nil
}

func benchmarkFixedPanel(ctx context.Context, requestPath, compactPath, deltasPath, repeatText string) error {
	repeats, err := strconv.Atoi(repeatText)
	if err != nil || repeats < 1 || repeats > 1000 {
		return fmt.Errorf("benchmark repeats must be between 1 and 1000")
	}
	loadStarted := time.Now()
	request, compact, deltas, err := loadPanel(requestPath, compactPath, deltasPath)
	if err != nil {
		return err
	}
	loadElapsed := time.Since(loadStarted)
	evaluationStarted := time.Now()
	var result stochastic.FixedPanelResult
	for index := 0; index < repeats; index++ {
		select {
		case <-ctx.Done():
			return fmt.Errorf("benchmark cancelled: %w", ctx.Err())
		default:
		}
		result, err = stochastic.AggregateFixedPanel(request, compact, deltas)
		if err != nil {
			return fmt.Errorf("benchmark aggregate %d: %w", index, err)
		}
	}
	evaluationElapsed := time.Since(evaluationStarted)
	return json.NewEncoder(os.Stdout).Encode(struct {
		Repeats                 int     `json:"repeats"`
		LoadElapsedMS           float64 `json:"load_elapsed_ms"`
		EvaluationElapsedMS     float64 `json:"evaluation_elapsed_ms"`
		MeanEvaluationElapsedMS float64 `json:"mean_evaluation_elapsed_ms"`
		CandidateMeanDPS        float64 `json:"candidate_mean_dps"`
	}{
		Repeats:                 repeats,
		LoadElapsedMS:           float64(loadElapsed) / float64(time.Millisecond),
		EvaluationElapsedMS:     float64(evaluationElapsed) / float64(time.Millisecond),
		MeanEvaluationElapsedMS: float64(evaluationElapsed) / float64(time.Millisecond) / float64(repeats),
		CandidateMeanDPS:        result.CandidateMeanDPS,
	})
}

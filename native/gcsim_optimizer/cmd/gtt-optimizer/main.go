// Command gtt-optimizer owns the accepted fixed-panel, indexed evaluation,
// bounded FGBS and staged common-context finalist verification boundaries.
// Product UI binding remains a later gate.
package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"sort"
	"strconv"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	"genshinteamstracker/native/gcsim_optimizer/internal/search"
	"genshinteamstracker/native/gcsim_optimizer/internal/stochastic"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	if err := run(ctx, os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run(ctx context.Context, arguments []string) error {
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
	if len(arguments) != 2 || (arguments[0] != "validate-request" && arguments[0] != "validate-seed-member") {
		return fmt.Errorf("usage: gtt-optimizer (validate-request|validate-seed-member) INPUT.json | (aggregate-fixed-panel|benchmark-fixed-panel) REQUEST.json COMPACT.json DELTAS.json [REPEATS] | search-fgbs REQUEST.json COMPACT.json | verify-fgbs REQUEST.json COMPACT.json RUN_ROOT (controls|all)")
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
	overall, cancel := context.WithTimeout(ctx, time.Duration(request.Budgets.ProductTimeoutMS)*time.Millisecond)
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
	engine, err := search.New(artifactIndex, panel, search.DefaultConfig())
	if err != nil {
		return err
	}
	compileElapsed := time.Since(compileStarted)
	searchStarted := time.Now()
	searchResult, err := engine.Run(overall)
	if err != nil {
		return fmt.Errorf("FGBS search: %w", err)
	}
	searchElapsed := time.Since(searchStarted)
	if err := progress.emit("searching", 1, 5, false); err != nil {
		return err
	}
	candidates := searchResult.Finalists
	var screening *finalists.VerificationResult
	parallelism := 1
	workersPerProcess := runtime.NumCPU()
	if mode == "controls" {
		candidates = controlCandidates(searchResult)
	} else {
		if err := os.Mkdir(runRoot, 0o700); err != nil {
			return fmt.Errorf("create GOB-7 run root: %w", err)
		}
		screenCandidates := append([]search.ScoredAssignment{searchResult.Initial}, searchResult.Finalists...)
		screenCandidates = uniqueCandidates(screenCandidates)
		screenParallelism := minInt(4, len(screenCandidates), runtime.NumCPU())
		screenWorkers := maxInt(1, runtime.NumCPU()/screenParallelism)
		if err := progress.emit("simulating_finalists", 2, 5, false); err != nil {
			return err
		}
		screenResult, err := finalists.Verify(overall, request, artifactIndex, screenCandidates, filepath.Join(runRoot, "screen-n128"), 128, screenWorkers, screenParallelism)
		if err != nil {
			return fmt.Errorf("GOB-7 n128 screen: %w", err)
		}
		screening = &screenResult
		if err := progress.emit("validating_finalists", 3, 5, false); err != nil {
			return err
		}
		candidates = boundedN1000Finalists(screenResult, searchResult, 5)
		parallelism = minInt(3, len(candidates), runtime.NumCPU())
		workersPerProcess = maxInt(1, runtime.NumCPU()/parallelism)
	}
	verificationRoot := runRoot
	if mode == "all" {
		verificationRoot = filepath.Join(runRoot, "final-adaptive")
	}
	var verification finalists.VerificationResult
	if mode == "all" {
		verification, err = finalists.VerifyAdaptive(overall, request, artifactIndex, candidates, verificationRoot, 500, 1000, 4, runtime.NumCPU(), 3, 4)
	} else {
		verification, err = finalists.Verify(overall, request, artifactIndex, candidates, verificationRoot, 1000, workersPerProcess, parallelism)
	}
	if err != nil {
		return err
	}
	if err := progress.emit("simulating_finalists", 4, 5, false); err != nil {
		return err
	}
	debugReceiptPath, err := filepath.Abs(filepath.Join(runRoot, "gob7-result.json"))
	if err != nil {
		return fmt.Errorf("resolve debug receipt path: %w", err)
	}
	productResult, err := buildProductResult(request, compact, searchResult, verification, debugReceiptPath)
	if err != nil {
		return err
	}
	payload := struct {
		Mode             string                        `json:"mode"`
		Search           search.Result                 `json:"search"`
		Screening        *finalists.VerificationResult `json:"screening,omitempty"`
		Verification     finalists.VerificationResult  `json:"verification"`
		ProductResult    contracts.OptimizerResult     `json:"product_result"`
		CompileElapsedMS float64                       `json:"compile_elapsed_ms"`
		SearchElapsedMS  float64                       `json:"search_elapsed_ms"`
		TotalElapsedMS   float64                       `json:"total_elapsed_ms"`
	}{mode, searchResult, screening, verification, productResult, float64(compileElapsed) / float64(time.Millisecond), float64(searchElapsed) / float64(time.Millisecond), float64(compileElapsed+searchElapsed)/float64(time.Millisecond) + verification.TotalElapsedMS}
	if screening != nil {
		payload.TotalElapsedMS += screening.TotalElapsedMS
	}
	receipt, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return fmt.Errorf("encode verification receipt: %w", err)
	}
	receipt = append(receipt, '\n')
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

func buildProductResult(request contracts.OptimizerRequest, compact contracts.CompactIR, searchResult search.Result, verification finalists.VerificationResult, debugReceiptPath string) (contracts.OptimizerResult, error) {
	compactSHA256, err := contracts.CanonicalSHA256(compact)
	if err != nil {
		return contracts.OptimizerResult{}, fmt.Errorf("identify product compact IR: %w", err)
	}
	return buildMeasuredProductResult(request, compactSHA256, "", searchResult.OpaqueReasons, nil, verification, debugReceiptPath)
}

func buildMeasuredProductResult(request contracts.OptimizerRequest, compactSHA256, setPanelSHA256 string, opaqueReasons, extraWarnings []string, verification finalists.VerificationResult, debugReceiptPath string) (contracts.OptimizerResult, error) {
	winner := verification.Winner
	assignments := productAssignments(request, winner.Assignment)
	requestSHA256, err := contracts.CanonicalSHA256(request)
	if err != nil {
		return contracts.OptimizerResult{}, fmt.Errorf("identify product request: %w", err)
	}
	warnings := []string{"formula_rank_not_measurement_authority"}
	warnings = append(warnings, extraWarnings...)
	if len(opaqueReasons) > 0 {
		warnings = append(warnings, "opaque_formula_boundaries_present")
	}
	if verification.Adaptive != nil && verification.Adaptive.Status == finalists.AdaptiveUnresolvedPanelWide {
		warnings = append(warnings, "adaptive_finalist_panel_too_wide")
	}
	measuredOrder := append([]finalists.MeasuredCandidate(nil), verification.Candidates...)
	sort.Slice(measuredOrder, func(i, j int) bool {
		if measuredOrder[i].MeasuredDPS != measuredOrder[j].MeasuredDPS {
			return measuredOrder[i].MeasuredDPS > measuredOrder[j].MeasuredDPS
		}
		return measuredOrder[i].AssignmentSHA256 < measuredOrder[j].AssignmentSHA256
	})
	if len(measuredOrder) > 1 {
		combinedSE := math.Hypot(measuredOrder[0].StandardError, measuredOrder[1].StandardError)
		if measuredOrder[0].MeasuredDPS-measuredOrder[1].MeasuredDPS <= 1.96*combinedSE {
			warnings = append(warnings, "measured_top_confidence_overlap")
		}
	}
	sort.Strings(warnings)
	rankedCandidates := make([]contracts.RankedCandidateResult, 0, len(measuredOrder))
	for index, candidate := range measuredOrder {
		rankedCandidates = append(rankedCandidates, contracts.RankedCandidateResult{
			Rank:       index + 1,
			Artifacts:  productAssignments(request, candidate.Assignment),
			FormulaDPS: decimalText(candidate.FormulaDPS),
			Measured: contracts.MeasuredResult{
				Iterations:         candidate.Iterations,
				DPS:                decimalText(candidate.MeasuredDPS),
				StandardError:      decimalText(candidate.StandardError),
				EngineResultSHA256: candidate.EngineResultSHA256,
			},
			FormulaResidual: decimalText(candidate.FormulaResidualDPS),
		})
	}
	result := contracts.OptimizerResult{
		SchemaVersion:         contracts.SchemaVersion,
		SchemaKind:            contracts.ResultSchemaKind,
		RequestSHA256:         requestSHA256,
		CompactIRSHA256:       compactSHA256,
		SetContextPanelSHA256: setPanelSHA256,
		Status:                "success",
		Winner:                assignments,
		Candidates:            rankedCandidates,
		FormulaDPS:            decimalText(winner.FormulaDPS),
		Measured: &contracts.MeasuredResult{
			Iterations:         winner.Iterations,
			DPS:                decimalText(winner.MeasuredDPS),
			StandardError:      decimalText(winner.StandardError),
			EngineResultSHA256: winner.EngineResultSHA256,
		},
		FormulaResidual:  decimalText(winner.FormulaResidualDPS),
		Warnings:         warnings,
		DebugReceiptPath: debugReceiptPath,
	}
	if err := result.Validate(); err != nil {
		return contracts.OptimizerResult{}, fmt.Errorf("validate product result: %w", err)
	}
	return result, nil
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

func decimalText(value float64) string {
	return strconv.FormatFloat(value, 'f', -1, 64)
}

func boundedN1000Finalists(screen finalists.VerificationResult, result search.Result, measuredLimit int) []search.ScoredAssignment {
	rows := append([]finalists.MeasuredCandidate(nil), screen.Candidates...)
	sort.Slice(rows, func(i, j int) bool {
		if rows[i].MeasuredDPS != rows[j].MeasuredDPS {
			return rows[i].MeasuredDPS > rows[j].MeasuredDPS
		}
		return rows[i].AssignmentSHA256 < rows[j].AssignmentSHA256
	})
	if len(rows) > measuredLimit {
		rows = rows[:measuredLimit]
	}
	candidates := make([]search.ScoredAssignment, 0, measuredLimit+2)
	for _, row := range rows {
		candidates = append(candidates, search.ScoredAssignment{Assignment: row.Assignment, DPS: row.FormulaDPS, Source: row.Source + "+n128_top"})
	}
	formulaLeader := result.Leader
	formulaLeader.Source = "mandatory_formula_leader"
	current := result.Initial
	current.Source = "mandatory_current"
	candidates = append(candidates, formulaLeader, current)
	return uniqueCandidates(candidates)
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
	engine, err := search.New(artifactIndex, panel, search.DefaultConfig())
	if err != nil {
		return err
	}
	compileElapsed := time.Since(preparedAt)
	searchContext, cancel := context.WithTimeout(ctx, time.Duration(request.Budgets.ProductTimeoutMS)*time.Millisecond)
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

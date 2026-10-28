package finalists

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"sync"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
)

// FullBuildOrigin records where a full build came from without coupling the
// ordinary verifier to a particular search or theory representation.
type FullBuildOrigin struct {
	Kind            string   `json:"kind"`
	Phase           string   `json:"phase"`
	Family          string   `json:"family"`
	ContextSHA256   string   `json:"context_sha256"`
	DiagnosticCodes []string `json:"diagnostic_codes,omitempty"`
}

// FullBuildCandidate is the identity and formula-side metadata for one complete
// build. BuildIdentity is the canonical, typed-by-caller payload (for example,
// a Theory Witness45 plus its four concrete set packages). CandidateSHA256 is
// filled by the verifier and is ignored when a candidate is marshaled.
type FullBuildCandidate struct {
	FrameSHA256     string            `json:"frame_sha256"`
	BuildIdentity   json.RawMessage   `json:"build_identity"`
	FormulaDPS      float64           `json:"formula_dps"`
	Origins         []FullBuildOrigin `json:"origins"`
	CandidateSHA256 string            `json:"-"`

	tieBreakKey string
}

// FullBuildMeasurement is a receipt for one complete ordinary GCSIM run.
// Standard deviation and standard error are unavailable for a one-iteration
// result and are therefore encoded as JSON null.
type FullBuildMeasurement struct {
	CandidateSHA256      string            `json:"candidate_sha256"`
	FrameSHA256          string            `json:"frame_sha256"`
	BuildIdentity        json.RawMessage   `json:"build_identity"`
	FormulaDPS           float64           `json:"formula_dps"`
	MeasuredDPS          float64           `json:"measured_dps"`
	StandardDeviation    *float64          `json:"standard_deviation"`
	StandardError        *float64          `json:"standard_error"`
	Iterations           int               `json:"iterations"`
	ConfigSHA256         string            `json:"config_sha256"`
	EngineResultSHA256   string            `json:"engine_result_sha256"`
	EngineArtifactSHA256 string            `json:"engine_artifact_sha256"`
	SourceManifestSHA256 string            `json:"source_manifest_sha256"`
	IgnoreBurstEnergy    bool              `json:"ignore_burst_energy"`
	Origins              []FullBuildOrigin `json:"origins"`

	ElapsedMS              float64 `json:"-"`
	tieBreakKey            string
	standardDeviationValue float64
	standardErrorValue     float64
}

// FullBuildVerificationResult keeps every completed, eligible measurement
// available even when a later candidate fails or the caller cancels the run.
// AttemptedSHA256 contains only keys for which the ordinary runner was called.
type FullBuildVerificationResult struct {
	Measurements         []FullBuildMeasurement `json:"measurements"`
	Winner               *FullBuildMeasurement  `json:"winner,omitempty"`
	Iterations           int                    `json:"iterations"`
	Waves                []VerificationWave     `json:"waves,omitempty"`
	EnergyRejectedSHA256 []string               `json:"energy_rejected_sha256,omitempty"`
	AttemptedSHA256      []string               `json:"attempted_sha256"`
	FailedSHA256         []string               `json:"failed_sha256,omitempty"`
	TotalElapsedMS       float64                `json:"total_elapsed_ms"`

	maximumEnergyShortage float64
}

// FullBuildRenderer turns a full-build identity into the exact prepared
// ordinary configuration that will be measured.
type FullBuildRenderer func(FullBuildCandidate, int, int) (RenderedConfig, error)

// OrdinaryRunner is injectable for focused tests and alternate hosts. A nil
// runner selects the product engineclient path with binary integrity checks.
type OrdinaryRunner func(context.Context, contracts.OptimizerRequest, string, string, int, int) (engineclient.OrdinaryResult, error)

// FullBuildObserver receives serialized lifecycle notifications. Attempted is
// called immediately before an ordinary runner invocation. Measured is called
// after result validation and, for the product runner, a bound-binary check.
// Returning an error cancels pending candidates and returns completed rows.
type FullBuildObserver struct {
	Attempted func(candidateSHA256 string) error
	Measured  func(FullBuildMeasurement) error
}

type NoEnergyFeasibleFullBuildError struct {
	CandidateSHA256 []string
	MaximumShortage float64
	ElapsedMS       float64
}

func (err *NoEnergyFeasibleFullBuildError) Error() string {
	return fmt.Sprintf("no full build completed the intended rotation with finite energy (maximum shortage %.6f)", err.MaximumShortage)
}

// FullBuildFrameSHA256 binds candidate identities to the immutable ordinary
// frame, full engine/source binding, wearer/artifact inputs and stochastic
// seed policy, plus the parsed energy option. Iterations and worker budgets
// stay on the measurement/cohort and do not change candidate identity.
func FullBuildFrameSHA256(request contracts.OptimizerRequest) (string, error) {
	ignoreBurstEnergy, err := setcontext.IgnoreBurstEnergy(request.Context.PreparedConfig.Text)
	if err != nil {
		return "", fmt.Errorf("full-build energy policy: %w", err)
	}
	frame := struct {
		Kind              string                     `json:"kind"`
		Engine            contracts.EngineBinding    `json:"engine"`
		Context           contracts.RunContext       `json:"context"`
		Wearers           []contracts.Wearer         `json:"wearers"`
		Artifacts         []contracts.Artifact       `json:"artifacts"`
		Legality          contracts.LegalityPolicy   `json:"legality"`
		Stochastic        contracts.StochasticPolicy `json:"stochastic"`
		IgnoreBurstEnergy bool                       `json:"ignore_burst_energy"`
	}{
		Kind:              "gtt_gcsim_full_build_frame_v1",
		Engine:            request.Engine,
		Context:           request.Context,
		Wearers:           request.Wearers,
		Artifacts:         request.Artifacts,
		Legality:          request.Legality,
		Stochastic:        request.Stochastic,
		IgnoreBurstEnergy: ignoreBurstEnergy,
	}
	return contracts.CanonicalSHA256(frame)
}

// FullBuildCandidateSHA256 binds a canonical full-build payload to one exact
// ordinary frame. Object key order and insignificant input whitespace do not
// affect the returned identity.
func FullBuildCandidateSHA256(frameSHA256 string, buildIdentity json.RawMessage) (string, error) {
	if !isSHA256(frameSHA256) {
		return "", fmt.Errorf("full-build frame SHA-256 is invalid")
	}
	canonicalIdentity, err := canonicalBuildIdentity(buildIdentity)
	if err != nil {
		return "", err
	}
	identity := struct {
		Kind          string          `json:"kind"`
		FrameSHA256   string          `json:"frame_sha256"`
		BuildIdentity json.RawMessage `json:"build_identity"`
	}{
		Kind:          "gtt_gcsim_full_build_candidate_v1",
		FrameSHA256:   frameSHA256,
		BuildIdentity: canonicalIdentity,
	}
	return contracts.CanonicalSHA256(identity)
}

// VerifyFullBuildsWithRenderer runs the existing ordinary verifier lifecycle
// for generic full-build identities. The dynamic-wave plan is shared with the
// inventory adapters. A caller can inject a runner for no-engine tests; nil
// selects the bound product engine. At most one observer may be attached.
func VerifyFullBuildsWithRenderer(
	ctx context.Context,
	request contracts.OptimizerRequest,
	candidates []FullBuildCandidate,
	render FullBuildRenderer,
	runRoot string,
	iterations, maxParallelism, cpuBudget int,
	runner OrdinaryRunner,
	observers ...FullBuildObserver,
) (FullBuildVerificationResult, error) {
	plan, err := PlanDynamicWaves(len(candidates), maxParallelism, cpuBudget)
	if err != nil {
		return FullBuildVerificationResult{}, err
	}
	return verifyFullBuildsWithPlan(ctx, request, candidates, render, runRoot, iterations, plan, runner, true, observers...)
}

func verifyFullBuildsWithPlan(
	ctx context.Context,
	request contracts.OptimizerRequest,
	candidates []FullBuildCandidate,
	render FullBuildRenderer,
	runRoot string,
	iterations int,
	plan []VerificationWave,
	runner OrdinaryRunner,
	waveDirectories bool,
	observers ...FullBuildObserver,
) (FullBuildVerificationResult, error) {
	var output FullBuildVerificationResult
	if ctx == nil {
		return output, fmt.Errorf("full-build verification context is nil")
	}
	if render == nil {
		return output, fmt.Errorf("missing full-build renderer")
	}
	if len(candidates) == 0 {
		return output, fmt.Errorf("at least one full-build candidate is required")
	}
	if iterations <= 0 {
		return output, fmt.Errorf("iterations must be positive")
	}
	if len(observers) > 1 {
		return output, fmt.Errorf("at most one full-build observer is supported")
	}
	for _, wave := range plan {
		if wave.CandidateCount <= 0 || wave.Parallelism <= 0 || wave.Workers <= 0 || wave.StartRank <= 0 {
			return output, fmt.Errorf("full-build verification plan is invalid")
		}
	}
	if err := os.Mkdir(runRoot, 0o700); err != nil {
		return output, fmt.Errorf("create full-build root: %w", err)
	}

	var boundEngine engineclient.BoundEngine
	productRunner := runner == nil
	if productRunner {
		var err error
		boundEngine, err = engineclient.BindEngine(request)
		if err != nil {
			return output, err
		}
		runner = func(runCtx context.Context, _ contracts.OptimizerRequest, configText, runDirectory string, expectedIterations, workers int) (engineclient.OrdinaryResult, error) {
			return boundEngine.RunOrdinary(runCtx, configText, runDirectory, expectedIterations, workers)
		}
	}
	ignoreBurstEnergy, err := setcontext.IgnoreBurstEnergy(request.Context.PreparedConfig.Text)
	if err != nil {
		return output, fmt.Errorf("full-build energy policy: %w", err)
	}
	frameSHA256, err := FullBuildFrameSHA256(request)
	if err != nil {
		return output, err
	}
	started := time.Now()
	prepared := make([]fullBuildPreparedCandidate, len(candidates))
	seen := make(map[string]struct{}, len(candidates))
	for rank, input := range candidates {
		if err := ctx.Err(); err != nil {
			return output, err
		}
		candidate := input
		if candidate.FrameSHA256 != "" && candidate.FrameSHA256 != frameSHA256 {
			return output, fmt.Errorf("full-build candidate %d frame identity mismatch", rank+1)
		}
		candidate.FrameSHA256 = frameSHA256
		identity, err := canonicalBuildIdentity(candidate.BuildIdentity)
		if err != nil {
			return output, fmt.Errorf("full-build candidate %d identity: %w", rank+1, err)
		}
		candidate.BuildIdentity = identity
		if math.IsNaN(candidate.FormulaDPS) || math.IsInf(candidate.FormulaDPS, 0) || candidate.FormulaDPS < 0 {
			return output, fmt.Errorf("full-build candidate %d formula DPS is invalid", rank+1)
		}
		if len(candidate.Origins) == 0 {
			return output, fmt.Errorf("full-build candidate %d has no provenance origin", rank+1)
		}
		for _, origin := range candidate.Origins {
			if strings.TrimSpace(origin.Kind) == "" {
				return output, fmt.Errorf("full-build candidate %d has an origin without kind", rank+1)
			}
		}
		identitySHA, err := FullBuildCandidateSHA256(frameSHA256, identity)
		if err != nil {
			return output, fmt.Errorf("full-build candidate %d identity: %w", rank+1, err)
		}
		if candidate.CandidateSHA256 != "" && candidate.CandidateSHA256 != identitySHA {
			return output, fmt.Errorf("full-build candidate %d candidate identity mismatch", rank+1)
		}
		if _, exists := seen[identitySHA]; exists {
			return output, fmt.Errorf("duplicate full-build candidate identity at rank %d", rank+1)
		}
		seen[identitySHA] = struct{}{}
		candidate.CandidateSHA256 = identitySHA
		candidate.Origins = cloneOrigins(candidate.Origins)
		prepared[rank] = fullBuildPreparedCandidate{
			candidate: candidate,
			runDir:    filepath.Join(runRoot, fmt.Sprintf("%02d-%s", rank+1, identitySHA[:12])),
		}
	}
	if err := validatePlanCoverage(plan, len(prepared)); err != nil {
		return output, err
	}
	output = FullBuildVerificationResult{
		Iterations:      iterations,
		AttemptedSHA256: make([]string, 0, len(prepared)),
	}
	var observer *FullBuildObserver
	if len(observers) == 1 {
		observer = &observers[0]
	}
	var observerMu sync.Mutex
	measurements := make([]FullBuildMeasurement, len(prepared))
	measurementValid := make([]bool, len(prepared))
	energyRejected := make([]bool, len(prepared))
	failedCandidates := make([]bool, len(prepared))
	var verificationErr error
	stopPublishing := false
	integrityFailure := false

	for waveIndex, plannedWave := range plan {
		if err := ctx.Err(); err != nil {
			verificationErr = err
			break
		}
		wave := plannedWave
		wave.Index = waveIndex + 1
		startIndex := wave.StartRank - 1
		endIndex := startIndex + wave.CandidateCount
		if startIndex < 0 || endIndex > len(prepared) {
			verificationErr = fmt.Errorf("full-build verification plan exceeds candidate count")
			break
		}
		waveStarted := time.Now()
		output.Waves = append(output.Waves, wave)
		waveRoot := runRoot
		if waveDirectories {
			waveRoot = filepath.Join(runRoot, fmt.Sprintf("wave-%02d", wave.Index))
			if err := os.Mkdir(waveRoot, 0o700); err != nil {
				verificationErr = fmt.Errorf("create full-build wave %d root: %w", wave.Index, err)
				break
			}
		}
		for index := startIndex; index < endIndex; index++ {
			candidate := prepared[index].candidate
			rendered, renderErr := render(candidate, iterations, wave.Workers)
			if renderErr != nil {
				verificationErr = fmt.Errorf("render full-build candidate %d: %w", index+1, renderErr)
				break
			}
			prepared[index].rendered = rendered
			if !isSHA256(rendered.SHA256) || contracts.TextSHA256(rendered.Text) != rendered.SHA256 {
				verificationErr = fmt.Errorf("render full-build candidate %d config identity mismatch", index+1)
				break
			}
			renderedIgnoreBurstEnergy, energyErr := setcontext.IgnoreBurstEnergy(rendered.Text)
			if energyErr != nil || renderedIgnoreBurstEnergy != ignoreBurstEnergy {
				if energyErr == nil {
					energyErr = fmt.Errorf("rendered energy policy differs from the ordinary frame")
				}
				verificationErr = fmt.Errorf("render full-build candidate %d energy policy: %w", index+1, energyErr)
				break
			}
			if waveDirectories {
				prepared[index].runDir = filepath.Join(waveRoot, fmt.Sprintf("%02d-%s", index-startIndex+1, candidate.CandidateSHA256[:12]))
			}
		}
		if verificationErr != nil {
			output.Waves[len(output.Waves)-1].TotalElapsedMS = float64(time.Since(waveStarted)) / float64(time.Millisecond)
			break
		}

		waveCtx, cancelWave := context.WithCancel(ctx)
		jobs := make(chan int)
		events := make(chan fullBuildRunEvent, wave.CandidateCount)
		var workersGroup sync.WaitGroup
		workerCount := minInt(wave.Parallelism, wave.CandidateCount)
		for workerIndex := 0; workerIndex < workerCount; workerIndex++ {
			workersGroup.Add(1)
			go func() {
				defer workersGroup.Done()
				for candidateIndex := range jobs {
					if waveCtx.Err() != nil {
						continue
					}
					item := prepared[candidateIndex]
					observerMu.Lock()
					if waveCtx.Err() != nil {
						observerMu.Unlock()
						continue
					}
					var admissionErr error
					if observer != nil && observer.Attempted != nil {
						admissionErr = observer.Attempted(item.candidate.CandidateSHA256)
					}
					if admissionErr == nil {
						output.AttemptedSHA256 = append(output.AttemptedSHA256, item.candidate.CandidateSHA256)
					}
					observerMu.Unlock()
					if admissionErr != nil {
						events <- fullBuildRunEvent{candidateIndex: candidateIndex, err: fmt.Errorf("full-build attempted observer for candidate %d: %w", candidateIndex+1, admissionErr), observerFailure: true}
						cancelWave()
						continue
					}
					measured, runErr := runner(waveCtx, request, item.rendered.Text, item.runDir, iterations, wave.Workers)
					if runErr != nil {
						events <- fullBuildRunEvent{candidateIndex: candidateIndex, err: fmt.Errorf("verify full-build candidate %d: %w", candidateIndex+1, runErr), attempted: true}
						cancelWave()
						continue
					}
					if validationErr := validateOrdinaryMeasurement(measured, item.rendered, iterations); validationErr != nil {
						events <- fullBuildRunEvent{candidateIndex: candidateIndex, err: fmt.Errorf("verify full-build candidate %d: %w", candidateIndex+1, validationErr), attempted: true}
						cancelWave()
						continue
					}
					if !ignoreBurstEnergy && measured.InsufficientEnergyMax > 0 {
						events <- fullBuildRunEvent{candidateIndex: candidateIndex, energyShortage: measured.InsufficientEnergyMax, attempted: true}
						continue
					}
					measurement := makeFullBuildMeasurement(request, item.candidate, measured, ignoreBurstEnergy)
					events <- fullBuildRunEvent{candidateIndex: candidateIndex, measurement: &measurement, attempted: true}
				}
			}()
		}
		var dispatcherGroup sync.WaitGroup
		dispatcherGroup.Add(1)
		go func() {
			defer dispatcherGroup.Done()
			defer close(jobs)
			for candidateIndex := startIndex; candidateIndex < endIndex; candidateIndex++ {
				select {
				case jobs <- candidateIndex:
				case <-waveCtx.Done():
					return
				}
			}
		}()
		go func() {
			dispatcherGroup.Wait()
			workersGroup.Wait()
			close(events)
		}()
		for event := range events {
			if event.err != nil {
				if event.attempted {
					failedCandidates[event.candidateIndex] = true
				}
				if verificationErr == nil {
					verificationErr = event.err
				}
				if event.observerFailure {
					stopPublishing = true
				}
				continue
			}
			if event.energyShortage > 0 {
				energyRejected[event.candidateIndex] = true
				if event.energyShortage > output.maximumEnergyShortage {
					output.maximumEnergyShortage = event.energyShortage
				}
				continue
			}
			if event.measurement == nil {
				continue
			}
			if productRunner {
				if err := boundEngine.VerifyUnchanged(); err != nil {
					failedCandidates[event.candidateIndex] = true
					verificationErr = fmt.Errorf("bound engine changed during full-build stage: %w", err)
					stopPublishing = true
					integrityFailure = true
					cancelWave()
					continue
				}
			}
			if integrityFailure {
				continue
			}
			if stopPublishing {
				measurements[event.candidateIndex] = *event.measurement
				measurementValid[event.candidateIndex] = true
				continue
			}
			if observer != nil && observer.Measured != nil {
				observerMu.Lock()
				observerErr := observer.Measured(*event.measurement)
				observerMu.Unlock()
				if observerErr != nil {
					verificationErr = fmt.Errorf("full-build measured observer for candidate %d: %w", event.candidateIndex+1, observerErr)
					stopPublishing = true
					measurements[event.candidateIndex] = *event.measurement
					measurementValid[event.candidateIndex] = true
					cancelWave()
					continue
				}
			}
			measurements[event.candidateIndex] = *event.measurement
			measurementValid[event.candidateIndex] = true
		}
		cancelWave()
		output.Waves[len(output.Waves)-1].TotalElapsedMS = float64(time.Since(waveStarted)) / float64(time.Millisecond)
		if verificationErr != nil {
			break
		}
		if err := ctx.Err(); err != nil {
			verificationErr = err
			break
		}
	}

	output.TotalElapsedMS = float64(time.Since(started)) / float64(time.Millisecond)
	if productRunner {
		if err := boundEngine.VerifyUnchanged(); err != nil {
			verificationErr = fmt.Errorf("bound engine changed during full-build stage: %w", err)
		}
	}
	for index, candidate := range prepared {
		if energyRejected[index] {
			output.EnergyRejectedSHA256 = append(output.EnergyRejectedSHA256, candidate.candidate.CandidateSHA256)
		}
		if failedCandidates[index] {
			output.FailedSHA256 = append(output.FailedSHA256, candidate.candidate.CandidateSHA256)
		}
	}
	for index, isValid := range measurementValid {
		if isValid {
			output.Measurements = append(output.Measurements, measurements[index])
		}
	}
	setFullBuildWinner(&output)
	if verificationErr != nil {
		return output, verificationErr
	}
	if err := ctx.Err(); err != nil {
		return output, err
	}
	if len(output.Measurements) == 0 && len(output.EnergyRejectedSHA256) > 0 {
		return output, &NoEnergyFeasibleFullBuildError{
			CandidateSHA256: append([]string(nil), output.EnergyRejectedSHA256...),
			MaximumShortage: output.maximumEnergyShortage,
			ElapsedMS:       output.TotalElapsedMS,
		}
	}
	if len(output.Measurements) == 0 {
		return output, fmt.Errorf("full-build verification produced no completed measurements")
	}
	return output, nil
}

type fullBuildPreparedCandidate struct {
	candidate FullBuildCandidate
	rendered  RenderedConfig
	runDir    string
}

type fullBuildRunEvent struct {
	candidateIndex  int
	measurement     *FullBuildMeasurement
	energyShortage  float64
	err             error
	observerFailure bool
	attempted       bool
}

func validatePlanCoverage(plan []VerificationWave, candidateCount int) error {
	if len(plan) == 0 {
		return fmt.Errorf("full-build verification plan is empty")
	}
	nextRank := 1
	for _, wave := range plan {
		if wave.StartRank != nextRank {
			return fmt.Errorf("full-build verification plan does not cover candidates in order")
		}
		nextRank += wave.CandidateCount
	}
	if nextRank != candidateCount+1 {
		return fmt.Errorf("full-build verification plan coverage %d does not match candidate count %d", nextRank-1, candidateCount)
	}
	return nil
}

func validateOrdinaryMeasurement(measured engineclient.OrdinaryResult, rendered RenderedConfig, expectedIterations int) error {
	if measured.Iterations != expectedIterations {
		return fmt.Errorf("ordinary result iterations %d; expected %d", measured.Iterations, expectedIterations)
	}
	if measured.ConfigSHA256 != rendered.SHA256 {
		return fmt.Errorf("full-build config identity changed across boundary")
	}
	if !isSHA256(measured.EngineResultSHA256) {
		return fmt.Errorf("ordinary result SHA-256 is invalid")
	}
	if math.IsNaN(measured.DPS) || math.IsInf(measured.DPS, 0) || measured.DPS < 0 ||
		math.IsNaN(measured.StandardDeviation) || math.IsInf(measured.StandardDeviation, 0) || measured.StandardDeviation < 0 ||
		math.IsNaN(measured.StandardError) || math.IsInf(measured.StandardError, 0) || measured.StandardError < 0 ||
		math.IsNaN(measured.InsufficientEnergyMax) || math.IsInf(measured.InsufficientEnergyMax, 0) || measured.InsufficientEnergyMax < 0 {
		return fmt.Errorf("ordinary result statistics are invalid")
	}
	return nil
}

func makeFullBuildMeasurement(request contracts.OptimizerRequest, candidate FullBuildCandidate, measured engineclient.OrdinaryResult, ignoreBurstEnergy bool) FullBuildMeasurement {
	var standardDeviation, standardError *float64
	if measured.Iterations > 1 {
		sd, se := measured.StandardDeviation, measured.StandardError
		standardDeviation, standardError = &sd, &se
	}
	return FullBuildMeasurement{
		CandidateSHA256:        candidate.CandidateSHA256,
		FrameSHA256:            candidate.FrameSHA256,
		BuildIdentity:          append(json.RawMessage(nil), candidate.BuildIdentity...),
		FormulaDPS:             candidate.FormulaDPS,
		MeasuredDPS:            measured.DPS,
		StandardDeviation:      standardDeviation,
		StandardError:          standardError,
		Iterations:             measured.Iterations,
		ConfigSHA256:           measured.ConfigSHA256,
		EngineResultSHA256:     measured.EngineResultSHA256,
		EngineArtifactSHA256:   request.Engine.ArtifactSHA256,
		SourceManifestSHA256:   request.Engine.SourceManifestSHA256,
		IgnoreBurstEnergy:      ignoreBurstEnergy,
		Origins:                cloneOrigins(candidate.Origins),
		ElapsedMS:              measured.ElapsedMS,
		tieBreakKey:            candidate.tieBreakKey,
		standardDeviationValue: measured.StandardDeviation,
		standardErrorValue:     measured.StandardError,
	}
}

func setFullBuildWinner(result *FullBuildVerificationResult) {
	if len(result.Measurements) == 0 {
		result.Winner = nil
		return
	}
	ordered := append([]FullBuildMeasurement(nil), result.Measurements...)
	sort.Slice(ordered, func(i, j int) bool {
		if ordered[i].MeasuredDPS != ordered[j].MeasuredDPS {
			return ordered[i].MeasuredDPS > ordered[j].MeasuredDPS
		}
		left, right := ordered[i].tieBreakKey, ordered[j].tieBreakKey
		if left == "" {
			left = ordered[i].CandidateSHA256
		}
		if right == "" {
			right = ordered[j].CandidateSHA256
		}
		return left < right
	})
	winner := ordered[0]
	result.Winner = &winner
}

func canonicalBuildIdentity(raw json.RawMessage) (json.RawMessage, error) {
	if len(raw) == 0 {
		return nil, fmt.Errorf("build identity is required")
	}
	canonical, err := contracts.CanonicalJSON(raw)
	if err != nil {
		return nil, fmt.Errorf("canonicalize build identity: %w", err)
	}
	var object map[string]json.RawMessage
	if err := json.Unmarshal(canonical, &object); err != nil || object == nil || len(object) == 0 {
		return nil, fmt.Errorf("build identity must be a non-empty JSON object")
	}
	return json.RawMessage(append([]byte(nil), canonical...)), nil
}

func cloneOrigins(origins []FullBuildOrigin) []FullBuildOrigin {
	cloned := make([]FullBuildOrigin, len(origins))
	for index, origin := range origins {
		cloned[index] = origin
		cloned[index].DiagnosticCodes = append([]string(nil), origin.DiagnosticCodes...)
	}
	return cloned
}

func isSHA256(value string) bool {
	if len(value) != sha256.Size*2 || value != strings.ToLower(value) {
		return false
	}
	decoded, err := hex.DecodeString(value)
	return err == nil && len(decoded) == sha256.Size
}

func inventoryFullBuildIdentity(candidateAssignment any) (json.RawMessage, error) {
	identity := struct {
		Kind       string `json:"kind"`
		Assignment any    `json:"assignment"`
	}{Kind: "inventory_assignment_v1", Assignment: candidateAssignment}
	encoded, err := json.Marshal(identity)
	if err != nil {
		return nil, err
	}
	return canonicalBuildIdentity(encoded)
}

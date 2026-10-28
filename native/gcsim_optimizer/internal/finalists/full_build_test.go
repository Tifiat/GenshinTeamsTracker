package finalists

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
)

func TestFullBuildCandidateIdentityCanonicalAndFrameBound(t *testing.T) {
	frame := strings.Repeat("a", 64)
	left, err := FullBuildCandidateSHA256(frame, json.RawMessage(`{"kind":"theory_witness45_v1", "alias":"x"}`))
	if err != nil {
		t.Fatal(err)
	}
	right, err := FullBuildCandidateSHA256(frame, json.RawMessage("{\"alias\":\"x\",\"kind\":\"theory_witness45_v1\"}"))
	if err != nil {
		t.Fatal(err)
	}
	otherFrame, err := FullBuildCandidateSHA256(strings.Repeat("b", 64), json.RawMessage(`{"kind":"theory_witness45_v1","alias":"x"}`))
	if err != nil {
		t.Fatal(err)
	}
	if left != right || left == otherFrame {
		t.Fatalf("canonical identity/frame binding failed: left=%s right=%s other=%s", left, right, otherFrame)
	}
}

func TestVerifyFullBuildsReturnsCompletedRowsAndAttemptedKeysOnLaterFailure(t *testing.T) {
	request := fullBuildRequestFixture(false)
	candidates := fullBuildCandidateFixtures("first", "second", "third")
	render := fullBuildRendererFixture(false)
	calls := 0
	attemptedEvents := make([]string, 0)
	measuredEvents := make([]string, 0)
	runner := func(ctx context.Context, _ contracts.OptimizerRequest, configText, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
		calls++
		if calls == 2 {
			return engineclient.OrdinaryResult{}, errors.New("runner failed on second candidate")
		}
		return ordinaryFixtureResult(configText, iterations, 1000, 0), nil
	}
	result, err := VerifyFullBuildsWithRenderer(
		context.Background(), request, candidates, render, t.TempDir()+"/run", 500, 1, 1, runner,
		FullBuildObserver{
			Attempted: func(key string) error { attemptedEvents = append(attemptedEvents, key); return nil },
			Measured: func(row FullBuildMeasurement) error {
				measuredEvents = append(measuredEvents, row.CandidateSHA256)
				return nil
			},
		},
	)
	if err == nil || !strings.Contains(err.Error(), "runner failed on second candidate") {
		t.Fatalf("expected second-candidate runner error, got %v", err)
	}
	if len(result.Measurements) != 1 || len(result.AttemptedSHA256) != 2 || len(result.FailedSHA256) != 1 {
		t.Fatalf("unexpected partial result: %+v", result)
	}
	if len(attemptedEvents) != 2 || len(measuredEvents) != 1 || result.Measurements[0].CandidateSHA256 != measuredEvents[0] {
		t.Fatalf("observer lifecycle mismatch: attempted=%v measured=%v result=%+v", attemptedEvents, measuredEvents, result)
	}
	if result.Winner == nil || result.Winner.CandidateSHA256 != result.Measurements[0].CandidateSHA256 {
		t.Fatalf("partial winner was not retained: %+v", result.Winner)
	}
}

func TestVerifyFullBuildOneIterationHasUnavailableUncertainty(t *testing.T) {
	request := fullBuildRequestFixture(false)
	runner := func(_ context.Context, _ contracts.OptimizerRequest, configText, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
		return ordinaryFixtureResult(configText, iterations, 10, 0), nil
	}
	result, err := VerifyFullBuildsWithRenderer(
		context.Background(), request, fullBuildCandidateFixtures("only"), fullBuildRendererFixture(false),
		t.TempDir()+"/run", 1, 1, 1, runner,
	)
	if err != nil {
		t.Fatal(err)
	}
	if len(result.Measurements) != 1 || result.Measurements[0].StandardDeviation != nil || result.Measurements[0].StandardError != nil {
		t.Fatalf("one-iteration uncertainty must be null: %+v", result.Measurements)
	}
	if string(result.Measurements[0].BuildIdentity) != `{"alias":"only","kind":"theory_witness45_v1"}` {
		t.Fatalf("receipt did not echo canonical build identity: %s", result.Measurements[0].BuildIdentity)
	}
}

func TestVerifyFullBuildNeverRetainsEnergyRejectedMeasurement(t *testing.T) {
	request := fullBuildRequestFixture(false)
	runner := func(_ context.Context, _ contracts.OptimizerRequest, configText, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
		return ordinaryFixtureResult(configText, iterations, 10, 2), nil
	}
	result, err := VerifyFullBuildsWithRenderer(
		context.Background(), request, fullBuildCandidateFixtures("rejected"), fullBuildRendererFixture(false),
		t.TempDir()+"/run", 20, 1, 1, runner,
	)
	var noEnergy *NoEnergyFeasibleFullBuildError
	if !errors.As(err, &noEnergy) {
		t.Fatalf("expected energy rejection error, got %v", err)
	}
	if len(result.Measurements) != 0 || len(result.EnergyRejectedSHA256) != 1 || len(result.AttemptedSHA256) != 1 {
		t.Fatalf("energy-rejected build became a measurement: %+v", result)
	}
}

func TestVerifyFullBuildCancellationBeforeDispatchDoesNotSpendAttempt(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	cancel()
	calls := 0
	runner := func(context.Context, contracts.OptimizerRequest, string, string, int, int) (engineclient.OrdinaryResult, error) {
		calls++
		return engineclient.OrdinaryResult{}, errors.New("must not run")
	}
	result, err := VerifyFullBuildsWithRenderer(
		ctx, fullBuildRequestFixture(false), fullBuildCandidateFixtures("cancelled"), fullBuildRendererFixture(false),
		t.TempDir()+"/run", 50, 1, 1, runner,
	)
	if err == nil || len(result.AttemptedSHA256) != 0 || calls != 0 {
		t.Fatalf("cancelled dispatch was counted: calls=%d attempted=%v err=%v", calls, result.AttemptedSHA256, err)
	}
}

func TestVerifyFullBuildStreamsMeasurementWhileLaterRunnerIsPending(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	request := fullBuildRequestFixture(false)
	candidates := fullBuildCandidateFixtures("first", "pending-1", "pending-2", "pending-3")
	render := func(candidate FullBuildCandidate, iterations, workers int) (RenderedConfig, error) {
		var identity struct {
			Alias string `json:"alias"`
		}
		if err := json.Unmarshal(candidate.BuildIdentity, &identity); err != nil {
			return RenderedConfig{}, err
		}
		text := fmt.Sprintf("options iteration=%d workers=%d ignore_burst_energy=false;\n# alias=%s\n", iterations, workers, identity.Alias)
		return RenderedConfig{Text: text, SHA256: contracts.TextSHA256(text)}, nil
	}
	pendingStarted := make(chan struct{}, len(candidates))
	pendingFinished := make(chan struct{}, len(candidates))
	measured := make(chan string, len(candidates))
	runner := func(runCtx context.Context, _ contracts.OptimizerRequest, configText, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
		if strings.Contains(configText, "# alias=first\n") {
			return ordinaryFixtureResult(configText, iterations, 1000, 0), nil
		}
		pendingStarted <- struct{}{}
		<-runCtx.Done()
		pendingFinished <- struct{}{}
		return engineclient.OrdinaryResult{}, runCtx.Err()
	}
	plan := []VerificationWave{{Index: 1, StartRank: 1, CandidateCount: len(candidates), Workers: 1, Parallelism: 2}}
	runRoot := t.TempDir() + "/run"
	resultCh := make(chan struct {
		result FullBuildVerificationResult
		err    error
	}, 1)
	go func() {
		result, err := verifyFullBuildsWithPlan(
			ctx, request, candidates, render, runRoot, 50, plan, runner, false,
			FullBuildObserver{Measured: func(row FullBuildMeasurement) error {
				measured <- row.CandidateSHA256
				return nil
			}},
		)
		resultCh <- struct {
			result FullBuildVerificationResult
			err    error
		}{result: result, err: err}
	}()

	select {
	case <-pendingStarted:
	case <-time.After(2 * time.Second):
		t.Fatal("no later ordinary runner started")
	}
	select {
	case key := <-measured:
		if key == "" {
			t.Fatal("observer received an empty candidate key")
		}
	case <-time.After(2 * time.Second):
		t.Fatal("completed receipt was not streamed while a later runner remained pending")
	}
	select {
	case <-pendingFinished:
		t.Fatal("pending ordinary runner finished before cancellation")
	default:
	}
	cancel()

	select {
	case outcome := <-resultCh:
		if !errors.Is(outcome.err, context.Canceled) {
			t.Fatalf("expected cancellation after streamed receipt, got %v", outcome.err)
		}
		if len(outcome.result.Measurements) != 1 || outcome.result.Winner == nil || len(outcome.result.AttemptedSHA256) < 2 {
			t.Fatalf("streamed completed receipt or actual attempts were lost: %+v", outcome.result)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("verification did not return after cancellation")
	}
}

func TestVerifyFullBuildMeasuredObserverErrorDoesNotMarkCompletedCallFailed(t *testing.T) {
	observerErr := errors.New("receipt archive rejected measurement")
	runner := func(_ context.Context, _ contracts.OptimizerRequest, configText, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
		return ordinaryFixtureResult(configText, iterations, 10, 0), nil
	}
	result, err := VerifyFullBuildsWithRenderer(
		context.Background(), fullBuildRequestFixture(false), fullBuildCandidateFixtures("only"), fullBuildRendererFixture(false),
		t.TempDir()+"/run", 50, 1, 1, runner,
		FullBuildObserver{Measured: func(FullBuildMeasurement) error { return observerErr }},
	)
	if !errors.Is(err, observerErr) {
		t.Fatalf("expected measured observer failure, got %v", err)
	}
	if len(result.AttemptedSHA256) != 1 || len(result.Measurements) != 1 || len(result.FailedSHA256) != 0 {
		t.Fatalf("a completed call was counted as both failed and measured: %+v", result)
	}
}

func fullBuildRequestFixture(ignoreEnergy bool) contracts.OptimizerRequest {
	energy := "false"
	if ignoreEnergy {
		energy = "true"
	}
	text := "options iteration=7 workers=1 ignore_burst_energy=" + energy + ";\n"
	return contracts.OptimizerRequest{
		Context: contracts.RunContext{
			PreparedConfig: contracts.SourceText{Text: text, SHA256: contracts.TextSHA256(text)},
			ContextSHA256:  strings.Repeat("c", 64),
		},
		Engine: contracts.EngineBinding{
			ArtifactSHA256:       strings.Repeat("a", 64),
			SourceManifestSHA256: strings.Repeat("b", 64),
		},
	}
}

func fullBuildCandidateFixtures(aliases ...string) []FullBuildCandidate {
	candidates := make([]FullBuildCandidate, 0, len(aliases))
	for _, alias := range aliases {
		identity, _ := json.Marshal(map[string]string{"kind": "theory_witness45_v1", "alias": alias})
		candidates = append(candidates, FullBuildCandidate{
			BuildIdentity: identity,
			FormulaDPS:    100,
			Origins:       []FullBuildOrigin{{Kind: "theory", Phase: "search", Family: alias}},
		})
	}
	return candidates
}

func fullBuildRendererFixture(ignoreEnergy bool) FullBuildRenderer {
	energy := "false"
	if ignoreEnergy {
		energy = "true"
	}
	return func(_ FullBuildCandidate, iterations, workers int) (RenderedConfig, error) {
		text := fmt.Sprintf("options iteration=%d workers=%d ignore_burst_energy=%s;\n", iterations, workers, energy)
		return RenderedConfig{Text: text, SHA256: contracts.TextSHA256(text)}, nil
	}
}

func ordinaryFixtureResult(configText string, iterations int, dps, energyShortage float64) engineclient.OrdinaryResult {
	return engineclient.OrdinaryResult{
		Iterations:            iterations,
		DPS:                   dps,
		StandardDeviation:     5,
		StandardError:         1,
		ElapsedMS:             1,
		ConfigSHA256:          contracts.TextSHA256(configText),
		EngineResultSHA256:    strings.Repeat("d", 64),
		InsufficientEnergyMax: energyShortage,
	}
}

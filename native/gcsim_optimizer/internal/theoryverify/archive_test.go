package theoryverify

import (
	"context"
	"encoding/json"
	"errors"
	"math"
	"os"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
	"genshinteamstracker/native/gcsim_optimizer/internal/finalists"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorypackages"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorysearch"
)

func ordinaryRequestFixture() contracts.OptimizerRequest {
	hash := strings.Repeat("a", 64)
	request := contracts.OptimizerRequest{Engine: contracts.EngineBinding{ArtifactSHA256: hash, BindingSHA256: hash, SourceManifestSHA256: hash, PatchManifestSHA256: hash},
		Legality: contracts.LegalityPolicy{TheorySearch: true}, Stochastic: contracts.StochasticPolicy{Seeds: []uint64{431}}}
	text := "options iteration=7 workers=1 seed=431 ignore_burst_energy=true;\n"
	for _, actor := range []string{"actor_a", "actor_b", "actor_c", "actor_d"} {
		request.Wearers = append(request.Wearers, contracts.Wearer{WearerKey: actor})
		text += actor + " char lvl=90/90;\n" + actor + " add set=\"old\" count=4;\n" + actor + " add stats hp=4780 atk=311 atk%=0.932 cr=0.311;\n\n"
	}
	text += "target lvl=100;\nactor_a skill;\nactor_b burst;\n"
	request.Context.PreparedConfig = contracts.SourceText{Text: text, SHA256: contracts.TextSHA256(text)}
	request.Context.ContextSHA256 = hash
	return request
}

func witnessFixture() alloc.State {
	var mains [4][5]string
	for actor := range mains {
		mains[actor] = [5]string{"hp", "atk", "atk_percent", "atk_percent", "crit_rate"}
	}
	return alloc.Seed(mains, [4][10]float64{}, 0, 45)
}

func aliasFixture(set string) theorysearch.Alias {
	var packages [4]domain.Package
	rows := make([]theorysearch.PackageRow, 4)
	for actor, key := range []string{"actor_a", "actor_b", "actor_c", "actor_d"} {
		packages[actor] = domain.Package{Sets: []contracts.SetRequirement{}}
		if actor == 0 && set != "" {
			packages[actor].Sets = []contracts.SetRequirement{{SetUID: set, Count: 4}}
		}
		rows[actor] = theorysearch.PackageRow{WearerKey: key, Sets: packages[actor].Sets}
	}
	return theorysearch.Alias{TupleKey: theorypackages.Key(packages), Packages: rows, ContextSHA256: strings.Repeat("b", 64), Uncertainty: []string{}}
}

func candidateFixture(t *testing.T, archive *Archive, set string, score float64) Candidate {
	t.Helper()
	candidate, err := NewCandidate(archive.FrameSHA256(), witnessFixture(), aliasFixture(set), score, []finalists.FullBuildOrigin{{Kind: "formula_search", Phase: "first_light", Family: "compressed_family", ContextSHA256: strings.Repeat("b", 64)}}, 0)
	if err != nil {
		t.Fatal(err)
	}
	return candidate
}

func searchFixture(candidates []Candidate, phase string) theorysearch.Snapshot {
	rows := make([]theorysearch.FamilyRow, len(candidates))
	for index, candidate := range candidates {
		rows[index] = candidate.Row
	}
	return theorysearch.Snapshot{SchemaVersion: 2, SchemaKind: theorysearch.ResultKind, RequestSHA256: strings.Repeat("c", 64), SessionID: "session", SnapshotVersion: 1, Phase: phase,
		PolicyID: theorysearch.PolicyID, Status: "success", SearchStatus: "partial", ResponseStatus: "formula_only", ReferenceScore: 999999,
		PracticalBandPercent: 3, SensitivityBandPercent: 2, CoLeaders: rows, Pending: []theorysearch.FamilyRow{}, Unavailable: []theorysearch.Unavailable{},
		TotalFoundFamilies: len(rows), TotalFoundTuples: len(rows), DomainTuples: "100", UnseenTuples: "90", SourceUpper: "unbounded", OuterUpper: "unbounded"}
}

func runnerReceipt(text string, iterations int, dps float64) engineclient.OrdinaryResult {
	return engineclient.OrdinaryResult{Iterations: iterations, DPS: dps, StandardDeviation: 5, StandardError: 5 / math.Sqrt(float64(iterations)), ConfigSHA256: contracts.TextSHA256(text), EngineResultSHA256: strings.Repeat("d", 64)}
}

func TestTheoryVerifiedIdentityDoesNotInheritAliasMainOrAllocation(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, err := NewArchive(request, Policy{Limit: 7, Iterations: 500})
	if err != nil {
		t.Fatal(err)
	}
	base := candidateFixture(t, archive, "first", 100)
	alias := candidateFixture(t, archive, "second", 100)
	mainState := alloc.ReplaceMain(base.Row.Witness45, 0, 2, "hp_percent", [4][10]float64{}, 45)
	main, err := NewCandidate(archive.frameSHA, mainState, base.Row.Aliases[0], 100, base.Build.Origins, 0)
	if err != nil {
		t.Fatal(err)
	}
	allocationState := base.Row.Witness45
	allocationState.Upgrades[0][0][0] -= .25
	allocationState.Upgrades[0][0][1] += .25
	allocation, err := NewCandidate(archive.frameSHA, allocationState, base.Row.Aliases[0], 100, base.Build.Origins, 0)
	if err != nil {
		t.Fatal(err)
	}
	keys := map[string]bool{}
	for _, candidate := range []Candidate{base, alias, main, allocation} {
		if keys[candidate.Key] {
			t.Fatal("different full build inherited a candidate identity")
		}
		keys[candidate.Key] = true
	}
	corrupt := base
	corrupt.Row.Witness45 = allocationState
	if err := archive.Offer([]Candidate{corrupt}); err == nil {
		t.Fatal("candidate payload mismatch was accepted")
	}
}

func TestTheoryVerifiedRendererUsesOrdinaryFrameAndRawTotals(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 7, Iterations: 500})
	candidate := candidateFixture(t, archive, "replacement", 100)
	render, err := Renderer(request, strings.Repeat("e", 64))
	if err != nil {
		t.Fatal(err)
	}
	config, err := render(candidate.Build, 500, 4)
	if err != nil {
		t.Fatal(err)
	}
	for _, inherited := range []string{"seed=431", "ignore_burst_energy=true", "target lvl=100;\nactor_a skill;\nactor_b burst;"} {
		if !strings.Contains(config.Text, inherited) {
			t.Fatal("ordinary frame changed", inherited)
		}
	}
	if strings.Contains(config.Text, `set="old"`) || strings.Count(config.Text, `set="replacement" count=4`) != 1 || strings.Count(config.Text, " add stats ") != 4 {
		t.Fatal("old sets/stats survived or new package was duplicated", config.Text)
	}
	if strings.Count(config.Text, " char lvl=90/90;") != 4 || strings.Contains(config.Text, "gtt_theory_neutral") || contracts.TextSHA256(config.Text) != config.SHA256 {
		t.Fatal("renderer fabricated an identity or declaration", config)
	}
	var stats [4]map[string]float64
	keys, values, mainValues, rolls := alloc.StatKeys(), alloc.StatValues(), alloc.MainValues(), candidate.Row.Witness45.Rolls()
	for actor := range stats {
		stats[actor] = map[string]float64{}
		for _, main := range candidate.Row.Witness45.Mains[actor] {
			stats[actor][main] += mainValues[main]
		}
		for coordinate, units := range rolls[actor] {
			stats[actor][keys[coordinate]] += units * values[coordinate]
		}
	}
	withoutSets := request
	withoutSets.Context.PreparedConfig.Text = strings.ReplaceAll(config.Text, "iteration=500 workers=4", "iteration=7 workers=1")
	expected, err := finalists.RenderArtifactStatTotals(withoutSets, stats, 500, 4)
	if err != nil || config.Text != expected.Text {
		t.Fatal("renderer did not use exact main/max-roll totals", err)
	}
}

func TestTheoryVerifiedArchiveKeepsCompleteReceiptsOnErrorAndDeep(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 3, Iterations: 50})
	candidates := []Candidate{candidateFixture(t, archive, "first", 300), candidateFixture(t, archive, "second", 200), candidateFixture(t, archive, "third", 100)}
	if err := archive.Offer(candidates); err != nil {
		t.Fatal(err)
	}
	search := searchFixture(candidates, "first_light")
	render, _ := Renderer(request, strings.Repeat("e", 64))
	calls := 0
	completedPublications := 0
	runner := func(_ context.Context, _ contracts.OptimizerRequest, text, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
		calls++
		if calls == 2 {
			return engineclient.OrdinaryResult{}, errors.New("later ordinary call failed")
		}
		return runnerReceipt(text, iterations, 90), nil
	}
	err := archive.Verify(context.Background(), request, search, true, render, t.TempDir(), 1, nil, func(snapshot Snapshot) error {
		if snapshot.Verification.CompletedCount > 0 {
			completedPublications++
		}
		return nil
	}, runner)
	if err == nil || calls != 2 || completedPublications == 0 {
		t.Fatal("completed receipt was not streamed before later failure", err, calls)
	}
	search.Phase, search.SnapshotVersion = "deep_baseline", 3
	search.ReferenceScore = 1000000
	snapshot := archive.Publish(search)
	if len(snapshot.CoLeaders) != 1 || snapshot.ReferenceScore != 90 || snapshot.ResponseStatus != "ordinary_verified" || snapshot.Verification.AttemptedCount != 2 || snapshot.Verification.CompletedCount != 1 || snapshot.Verification.FailedCount != 1 {
		t.Fatal("Deep/error reverted or inherited a receipt", snapshot)
	}
	encoded, _ := json.Marshal(snapshot)
	var wire map[string]any
	if err := json.Unmarshal(encoded, &wire); err != nil {
		t.Fatal(err)
	}
	if len(wire["co_leaders"].([]any)) != 1 || len(wire["pending"].([]any)) != 0 || wire["schema_kind"] != ResultKind {
		t.Fatal("formula rows escaped into verified JSON", string(encoded))
	}
}

func TestTheoryVerifiedCancelRetainsOnlyFinishedReceipt(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 3, Iterations: 50})
	candidates := []Candidate{candidateFixture(t, archive, "first", 300), candidateFixture(t, archive, "second", 200)}
	_ = archive.Offer(candidates)
	render, _ := Renderer(request, strings.Repeat("e", 64))
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	calls := 0
	err := archive.Verify(ctx, request, searchFixture(candidates, "first_light"), true, render, t.TempDir(), 1, nil, func(snapshot Snapshot) error {
		if snapshot.Verification.CompletedCount == 1 {
			cancel()
		}
		return nil
	}, func(_ context.Context, _ contracts.OptimizerRequest, text, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
		calls++
		return runnerReceipt(text, iterations, 75), nil
	})
	if !errors.Is(err, context.Canceled) || calls != 1 || len(archive.verified) != 1 {
		t.Fatal("Cancel lost/added a receipt or continued calls", err, calls)
	}
}

func TestTheoryVerifiedNoMeasurementMeansNoRecommendations(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 7, Iterations: 500})
	candidates := []Candidate{candidateFixture(t, archive, "first", 999999)}
	_ = archive.Offer(candidates)
	snapshot := archive.Publish(searchFixture(candidates, "first_light"))
	if snapshot.Status != "no_verified_result" || snapshot.ResponseStatus != "no_verified_result" || snapshot.ReferenceScore != 0 || len(snapshot.CoLeaders)+len(snapshot.Pending) != 0 || snapshot.Verification.UnverifiedCount != 1 {
		t.Fatal("formula-only candidate became a recommendation", snapshot)
	}
}

func TestTheoryVerifiedLifetimeBudgetProtectsLowFormulaResponseLane(t *testing.T) {
	request := ordinaryRequestFixture()
	policy, err := PolicyFromRequest(request)
	if err != nil || policy.Limit != 7 || policy.Iterations != 500 || policy.ResponseReserve != 2 {
		t.Fatal(policy, err)
	}
	archive, _ := NewArchive(request, policy)
	candidates := []Candidate{}
	for _, set := range []string{"a", "b", "c", "d", "e", "f", "g", "h"} {
		candidates = append(candidates, candidateFixture(t, archive, set, 10000))
	}
	_ = archive.Offer(candidates)
	render, _ := Renderer(request, strings.Repeat("e", 64))
	calls := 0
	runner := func(_ context.Context, _ contracts.OptimizerRequest, text, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
		calls++
		dps := 100.0
		if strings.Contains(text, `set="response`) {
			dps = 200
		}
		return runnerReceipt(text, iterations, dps), nil
	}
	root := t.TempDir()
	search := searchFixture(candidates, "first_light")
	for _, phase := range []string{"first_light", "breadth_light", "deep_baseline"} {
		search.Phase = phase
		if err := archive.Verify(context.Background(), request, search, false, render, root, 1, nil, nil, runner); err != nil {
			t.Fatal(err)
		}
	}
	if calls != 5 || archive.remaining() != 2 {
		t.Fatal("formula lane consumed the response reserve", calls, archive.remaining())
	}
	for _, set := range []string{"response_a", "response_b"} {
		candidate := candidateFixture(t, archive, set, 1)
		candidate.Lane = ResponseLane
		candidate.Build.Origins = []finalists.FullBuildOrigin{{Kind: string(ResponseLane), Phase: "response", Family: "support_proposal", ContextSHA256: strings.Repeat("b", 64)}}
		if err := archive.Offer([]Candidate{candidate}); err != nil {
			t.Fatal(err)
		}
	}
	if err := archive.Verify(context.Background(), request, search, true, render, root, 1, nil, nil, runner); err != nil {
		t.Fatal(err)
	}
	snapshot := archive.Publish(search)
	if calls != 7 || snapshot.ReferenceScore != 200 || snapshot.Verification.ResponseLaneAttemptedCount != 2 || snapshot.Verification.AttemptedCount != 7 || snapshot.Verification.OmittedCount != 3 {
		t.Fatal("low formula proposals were discarded or budget reset", calls, snapshot.Verification)
	}
	if err := archive.Verify(context.Background(), request, search, true, render, root, 1, nil, nil, runner); err != nil || calls != 7 {
		t.Fatal("completed rows or continuations caused extra calls", err, calls)
	}
}

func TestTheoryVerifiedPublishedReceiptsAreDetached(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 1, Iterations: 50})
	candidate := candidateFixture(t, archive, "original", 100)
	candidate.Build.Origins[0].DiagnosticCodes = []string{"original_evidence"}
	if err := archive.Offer([]Candidate{candidate}); err != nil {
		t.Fatal(err)
	}
	candidate.Build.Origins[0].DiagnosticCodes[0] = "caller_mutated"
	render, _ := Renderer(request, strings.Repeat("e", 64))
	search := searchFixture([]Candidate{candidate}, "first_light")
	if err := archive.Verify(context.Background(), request, search, true, render, t.TempDir(), 1, nil, nil,
		func(_ context.Context, _ contracts.OptimizerRequest, text, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
			return runnerReceipt(text, iterations, 100), nil
		}); err != nil {
		t.Fatal(err)
	}
	first := archive.Publish(search)
	row := &first.CoLeaders[0]
	row.Measurement.BuildIdentity[0] = '!'
	row.Measurement.Origins[0].DiagnosticCodes[0] = "publication_mutated"
	*row.Measurement.StandardDeviation = 999
	row.Aliases[0].Packages[0].Sets[0].SetUID = "publication_mutated"
	row.Allocations[0].MainStats["goblet"] = "hp_percent"
	second := archive.Publish(search)
	actual := second.CoLeaders[0]
	if actual.Measurement.BuildIdentity[0] == '!' || actual.Measurement.Origins[0].DiagnosticCodes[0] != "original_evidence" ||
		*actual.Measurement.StandardDeviation != 5 || actual.Aliases[0].Packages[0].Sets[0].SetUID != "original" || actual.Allocations[0].MainStats["goblet"] != "atk_percent" {
		t.Fatal("publication/offerer mutated the retained archive receipt", actual)
	}
}

func TestTheoryVerifiedPublisherErrorRecoversCompletedInFlight(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 2, Iterations: 50})
	candidates := []Candidate{candidateFixture(t, archive, "first", 200), candidateFixture(t, archive, "second", 100)}
	_ = archive.Offer(candidates)
	render, _ := Renderer(request, strings.Repeat("e", 64))
	started, release := make(chan struct{}, 2), make(chan struct{})
	go func() { <-started; <-started; close(release) }()
	err := archive.Verify(context.Background(), request, searchFixture(candidates, "first_light"), true, render, t.TempDir(), 2, nil,
		func(snapshot Snapshot) error {
			if snapshot.Verification.CompletedCount > 0 {
				return errors.New("publication transport failed")
			}
			return nil
		}, func(_ context.Context, _ contracts.OptimizerRequest, text, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
			started <- struct{}{}
			<-release
			return runnerReceipt(text, iterations, 100), nil
		})
	if err == nil || len(archive.verified) != 2 || len(archive.failed) != 0 || len(archive.attempted) != 2 {
		t.Fatal("publisher error erased another complete receipt", err, len(archive.verified), len(archive.failed))
	}
}

// The compact wire is consumed by the Python contract gate during closeout.
// Its runner is synthetic; this is no engine or numerical acceptance evidence.
func TestTheoryVerifiedNativeWireSnapshot(t *testing.T) {
	request := ordinaryRequestFixture()
	archive, _ := NewArchive(request, Policy{Limit: 2, Iterations: 50})
	candidates := []Candidate{candidateFixture(t, archive, "native_wire_a", 1000), candidateFixture(t, archive, "native_wire_b", 990)}
	_ = archive.Offer(candidates)
	search := searchFixture(candidates, "first_light")
	render, _ := Renderer(request, strings.Repeat("e", 64))
	if err := archive.Verify(context.Background(), request, search, true, render, t.TempDir(), 1, nil, nil,
		func(_ context.Context, _ contracts.OptimizerRequest, text, _ string, iterations, _ int) (engineclient.OrdinaryResult, error) {
			dps := 900.0
			if strings.Contains(text, "native_wire_b") {
				dps = 800
			}
			return runnerReceipt(text, iterations, dps), nil
		}); err != nil {
		t.Fatal(err)
	}
	snapshot := archive.Publish(search)
	wire, err := json.Marshal(snapshot)
	if err != nil {
		t.Fatal(err)
	}
	var decoded map[string]json.RawMessage
	if err := json.Unmarshal(wire, &decoded); err != nil {
		t.Fatal(err)
	}
	var rows []VerifiedRow
	if err := json.Unmarshal(decoded["co_leaders"], &rows); err != nil || len(rows) != 1 || rows[0].Measurement.MeasuredDPS != 900 || snapshot.ReferenceScore != 900 {
		t.Fatal("ordinary projection leaked formula rows/reference", err)
	}
	if err := json.Unmarshal(decoded["pending"], &rows); err != nil || len(rows) != 1 || rows[0].Measurement.MeasuredDPS != 800 || rows[0].Reason != "below_verified_practical_band" {
		t.Fatal("measured below-band row was omitted from the wire", err)
	}
	if os.Getenv("GTT_THEORY_PRINT_TEST_WIRE") == "1" {
		t.Logf("THEORY_NATIVE_WIRE:%s", wire)
	}
}

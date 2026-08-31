package stochastic

import (
	"math"
	"os"
	"path/filepath"
	"reflect"
	"runtime"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func readContracts(t *testing.T) (contracts.OptimizerRequest, contracts.CompactIR) {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve test location")
	}
	fixtures := filepath.Clean(filepath.Join(filepath.Dir(filename), "..", "..", "..", "..", "tests", "fixtures", "gcsim_optimizer_go_v1"))
	requestPayload, err := os.ReadFile(filepath.Join(fixtures, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	request, err := contracts.DecodeRequest(requestPayload)
	if err != nil {
		t.Fatal(err)
	}
	compactPayload, err := os.ReadFile(filepath.Join(fixtures, "compact_ir_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	compact, err := contracts.DecodeCompactIR(compactPayload)
	if err != nil {
		t.Fatal(err)
	}
	return request, compact
}

func closeTo(left, right float64) bool {
	return math.Abs(left-right) <= 1e-12
}

func TestAggregateFixedPanelBaselineAndCandidate(t *testing.T) {
	request, compact := readContracts(t)
	baseline, err := AggregateFixedPanel(request, compact, nil)
	if err != nil {
		t.Fatal(err)
	}
	if baseline.SampleCount != 2 || baseline.DurationMS != 20000 || !closeTo(baseline.CandidateMeanDamage, 109.5) || !closeTo(baseline.CandidateMeanDPS, 5.475) {
		t.Fatalf("baseline aggregate = %#v", baseline)
	}
	if !closeTo(baseline.SampleStandardDeviationDamage, math.Sqrt(40.5)) || !closeTo(baseline.StandardErrorDamage, 4.5) {
		t.Fatalf("baseline dispersion = sd %v se %v", baseline.SampleStandardDeviationDamage, baseline.StandardErrorDamage)
	}
	if !closeTo(baseline.SampleStandardDeviationDPS, math.Sqrt(40.5)/20) || !closeTo(baseline.StandardErrorDPS, 0.225) {
		t.Fatalf("baseline DPS dispersion = sd %v se %v", baseline.SampleStandardDeviationDPS, baseline.StandardErrorDPS)
	}
	if len(baseline.OpaqueReasons) != 1 || baseline.OpaqueReasons[0].ReasonCode != "unsupported_source_program" || len(baseline.OpaqueReasons[0].Seeds) != 2 {
		t.Fatalf("opaque coverage = %#v", baseline.OpaqueReasons)
	}
	if compact.Members[0].TopologySHA256 == compact.Members[1].TopologySHA256 {
		t.Fatal("fixture must prove differing topology hashes are accepted")
	}

	candidate, err := AggregateFixedPanel(request, compact, map[string]float64{"actor_a.hp_percent": 1})
	if err != nil {
		t.Fatal(err)
	}
	if !closeTo(candidate.CandidateMeanDamage, 209.5) || !closeTo(candidate.DeltaMeanDamage, 100) || !closeTo(candidate.CandidateMeanDPS, 10.475) || !closeTo(candidate.DeltaMeanDPS, 5) {
		t.Fatalf("candidate aggregate = %#v", candidate)
	}
	if len(candidate.CandidateByActor) != 4 || candidate.CandidateByActor[0].ActorKey != "actor_a" || !closeTo(candidate.CandidateByActor[0].Damage, 209.5) {
		t.Fatalf("candidate actor means = %#v", candidate.CandidateByActor)
	}
	for _, actor := range candidate.CandidateByActor[1:] {
		if actor.Damage != 0 || actor.DPS != 0 {
			t.Fatalf("absent actor must contribute zero: %#v", actor)
		}
	}
	repeated, err := AggregateFixedPanel(request, compact, map[string]float64{"actor_a.hp_percent": 1})
	if err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(candidate, repeated) {
		t.Fatal("fixed-panel aggregation is not repeatable")
	}
}

func TestAggregateFixedPanelAllowsOneTraceOnlyWithProof(t *testing.T) {
	request, compact := readContracts(t)
	request.Stochastic.Seeds = request.Stochastic.Seeds[:1]
	request.Stochastic.TopologyStabilityProofSHA256 = strings.Repeat("a", 64)
	requestSHA256, err := contracts.CanonicalSHA256(request)
	if err != nil {
		t.Fatal(err)
	}
	compact.RequestSHA256 = requestSHA256
	compact.Members = compact.Members[:1]
	result, err := AggregateFixedPanel(request, compact, nil)
	if err != nil {
		t.Fatal(err)
	}
	if result.SampleCount != 1 || result.SampleStandardDeviationDamage != 0 || result.StandardErrorDamage != 0 || result.SampleStandardDeviationDPS != 0 || result.StandardErrorDPS != 0 {
		t.Fatalf("proven one-trace dispersion must be zero: %#v", result)
	}
}

func TestAggregateFixedPanelRejectsSeedPanelDrift(t *testing.T) {
	request, compact := readContracts(t)

	reordered := compact
	reordered.Members = append([]contracts.IRSeedMember(nil), compact.Members...)
	reordered.Members[0], reordered.Members[1] = reordered.Members[1], reordered.Members[0]
	if _, err := AggregateFixedPanel(request, reordered, nil); err == nil || !strings.Contains(err.Error(), "sorted") {
		t.Fatalf("reordered members should fail closed, got %v", err)
	}

	missing := compact
	missing.Members = missing.Members[:1]
	if _, err := AggregateFixedPanel(request, missing, nil); err == nil || !strings.Contains(err.Error(), "count") {
		t.Fatalf("missing member should fail closed, got %v", err)
	}

	duplicate := compact
	duplicate.Members = append([]contracts.IRSeedMember(nil), compact.Members...)
	duplicate.Members[1].Seed = duplicate.Members[0].Seed
	if _, err := AggregateFixedPanel(request, duplicate, nil); err == nil || !strings.Contains(err.Error(), "sorted") {
		t.Fatalf("duplicate seed should fail closed, got %v", err)
	}
}

func TestAggregateFixedPanelAllowsPerSeedDurationsAndRejectsBaselineDrift(t *testing.T) {
	request, compact := readContracts(t)

	durationDrift := compact
	durationDrift.Members = append([]contracts.IRSeedMember(nil), compact.Members...)
	durationDrift.Members[1].DurationMS = 10000
	durationResult, err := AggregateFixedPanel(request, durationDrift, nil)
	if err != nil {
		t.Fatal(err)
	}
	if durationResult.DurationMS != 0 || !reflect.DeepEqual(durationResult.MemberDurationsMS, []int64{20000, 10000}) {
		t.Fatalf("duration receipt = %#v", durationResult)
	}
	if !closeTo(durationResult.CandidateMeanDPS, (105.0/20.0+114.0/10.0)/2.0) {
		t.Fatalf("per-seed DPS denominator was not preserved: %#v", durationResult)
	}
	if !closeTo(durationResult.CandidateByActor[0].DPS, durationResult.CandidateMeanDPS) {
		t.Fatalf("actor DPS does not use per-seed duration: %#v", durationResult.CandidateByActor)
	}

	baselineDrift := compact
	baselineDrift.Members = append([]contracts.IRSeedMember(nil), compact.Members...)
	baselineDrift.Members[0].Channels = append([]contracts.IRChannel(nil), compact.Members[0].Channels...)
	baselineDrift.Members[0].Channels[0].BaselineDamage = "104"
	if _, err := AggregateFixedPanel(request, baselineDrift, nil); err == nil || !strings.Contains(err.Error(), "zero artifact delta") {
		t.Fatalf("baseline drift should fail closed, got %v", err)
	}

	contextDrift := compact
	contextDrift.ContextSHA256 = strings.Repeat("f", 64)
	if _, err := AggregateFixedPanel(request, contextDrift, nil); err == nil || !strings.Contains(err.Error(), "context mismatch") {
		t.Fatalf("context drift should fail closed, got %v", err)
	}

	actorDrift := compact
	actorDrift.Members = append([]contracts.IRSeedMember(nil), compact.Members...)
	actorDrift.Members[0].Channels = append([]contracts.IRChannel(nil), compact.Members[0].Channels...)
	actorDrift.Members[0].Channels[0].ActorKey = "unknown_actor"
	if _, err := AggregateFixedPanel(request, actorDrift, nil); err == nil || !strings.Contains(err.Error(), "outside request domain") {
		t.Fatalf("actor-domain drift should fail closed, got %v", err)
	}
}

func TestAggregateFixedPanelRejectsNonFiniteArtifactDelta(t *testing.T) {
	request, compact := readContracts(t)
	if _, err := AggregateFixedPanel(request, compact, map[string]float64{"actor_a.hp_percent": math.Inf(1)}); err == nil || !strings.Contains(err.Error(), "non-finite") {
		t.Fatalf("non-finite delta should fail closed, got %v", err)
	}
}

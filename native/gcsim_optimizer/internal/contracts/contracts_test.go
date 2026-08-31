package contracts

import (
	"encoding/json"
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

type fixtureHashes struct {
	SchemaVersion int               `json:"schema_version"`
	SchemaKind    string            `json:"schema_kind"`
	Files         map[string]string `json:"files"`
}

func fixtureDirectory(t *testing.T) string {
	t.Helper()
	_, filename, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve contracts_test.go")
	}
	return filepath.Clean(filepath.Join(
		filepath.Dir(filename),
		"..", "..", "..", "..",
		"tests", "fixtures", "gcsim_optimizer_go_v1",
	))
}

func readFixture(t *testing.T, name string) []byte {
	t.Helper()
	payload, err := os.ReadFile(filepath.Join(fixtureDirectory(t), name))
	if err != nil {
		t.Fatalf("read fixture %s: %v", name, err)
	}
	return payload
}

func expectedHashes(t *testing.T) fixtureHashes {
	t.Helper()
	var fixture fixtureHashes
	if err := json.Unmarshal(readFixture(t, "canonical_sha256_v1.json"), &fixture); err != nil {
		t.Fatalf("decode fixture hashes: %v", err)
	}
	if fixture.SchemaVersion != SchemaVersion || fixture.SchemaKind != "gtt_gcsim_optimizer_fixture_hashes_v1" {
		t.Fatalf("unexpected fixture hash schema: %+v", fixture)
	}
	return fixture
}

func TestSharedFixturesValidateAndMatchCanonicalHashes(t *testing.T) {
	decoders := map[string]func([]byte) (any, error){
		"request_v1.json":    func(data []byte) (any, error) { return DecodeRequest(data) },
		"compact_ir_v1.json": func(data []byte) (any, error) { return DecodeCompactIR(data) },
		"progress_v1.json":   func(data []byte) (any, error) { return DecodeProgress(data) },
		"result_v1.json":     func(data []byte) (any, error) { return DecodeResult(data) },
	}
	for name, expected := range expectedHashes(t).Files {
		decode, ok := decoders[name]
		if !ok {
			t.Fatalf("no decoder for shared fixture %s", name)
		}
		value, err := decode(readFixture(t, name))
		if err != nil {
			t.Fatalf("decode %s: %v", name, err)
		}
		actual, err := CanonicalSHA256(value)
		if err != nil {
			t.Fatalf("hash %s: %v", name, err)
		}
		if actual != expected {
			t.Fatalf("%s hash %s; expected %s", name, actual, expected)
		}
		canonical, err := CanonicalJSON(value)
		if err != nil {
			t.Fatalf("canonicalize %s: %v", name, err)
		}
		roundTrip, err := decode(canonical)
		if err != nil {
			t.Fatalf("decode canonical %s: %v", name, err)
		}
		roundTripBytes, err := CanonicalJSON(roundTrip)
		if err != nil || string(roundTripBytes) != string(canonical) {
			t.Fatalf("%s canonical round-trip changed bytes: %v", name, err)
		}
	}
}

func TestSharedFixtureIdentitiesAreLinked(t *testing.T) {
	request, err := DecodeRequest(readFixture(t, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	requestSHA256, err := CanonicalSHA256(request)
	if err != nil {
		t.Fatal(err)
	}
	compact, err := DecodeCompactIR(readFixture(t, "compact_ir_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	if compact.RequestSHA256 != requestSHA256 || compact.ContextSHA256 != request.Context.ContextSHA256 || compact.EngineBindingSHA256 != request.Engine.BindingSHA256 {
		t.Fatal("compact IR is not bound to the request engine/context identity")
	}
	if len(compact.Members) != len(request.Stochastic.Seeds) {
		t.Fatal("compact IR member count differs from the fixed seed panel")
	}
	for index, member := range compact.Members {
		if member.Seed != request.Stochastic.Seeds[index] {
			t.Fatal("compact IR seed order differs from the request")
		}
	}
	progress, err := DecodeProgress(readFixture(t, "progress_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	if progress.RequestSHA256 != requestSHA256 {
		t.Fatal("progress is not bound to request identity")
	}
	result, err := DecodeResult(readFixture(t, "result_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	compactSHA256, err := CanonicalSHA256(compact)
	if err != nil {
		t.Fatal(err)
	}
	if result.RequestSHA256 != requestSHA256 || result.CompactIRSHA256 != compactSHA256 {
		t.Fatal("result is not bound to request and compact IR identities")
	}
}

func TestRequestRejectsUnknownFieldAndSchema(t *testing.T) {
	valid := string(readFixture(t, "request_v1.json"))
	unknownField := strings.Replace(valid, "{", "{\n  \"unexpected\": true,", 1)
	if _, err := DecodeRequest([]byte(unknownField)); err == nil || !strings.Contains(err.Error(), "unknown field") {
		t.Fatalf("unknown field should fail closed, got %v", err)
	}
	unknownVersion := strings.Replace(valid, "\"schema_version\": 1", "\"schema_version\": 2", 1)
	if _, err := DecodeRequest([]byte(unknownVersion)); err == nil || !strings.Contains(err.Error(), "unsupported schema_version") {
		t.Fatalf("unknown schema version should fail closed, got %v", err)
	}
	unknownKind := strings.Replace(valid, RequestSchemaKind, "unknown_request_v2", 1)
	if _, err := DecodeRequest([]byte(unknownKind)); err == nil || !strings.Contains(err.Error(), "unsupported schema_kind") {
		t.Fatalf("unknown schema kind should fail closed, got %v", err)
	}
}

func TestDecoderRejectsMissingRequiredField(t *testing.T) {
	valid := string(readFixture(t, "progress_v1.json"))
	missing := strings.Replace(valid, "  \"cancellation_requested\": false,\n", "", 1)
	if missing == valid {
		t.Fatal("test did not remove required field")
	}
	if _, err := DecodeProgress([]byte(missing)); err == nil || !strings.Contains(err.Error(), "missing") {
		t.Fatalf("missing required field should fail closed, got %v", err)
	}
}

func TestRequestRejectsNonCanonicalOrderingAndIdentityDrift(t *testing.T) {
	request, err := DecodeRequest(readFixture(t, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	request.Artifacts[0], request.Artifacts[1] = request.Artifacts[1], request.Artifacts[0]
	if err := request.Validate(); err == nil || !strings.Contains(err.Error(), "sorted") {
		t.Fatalf("artifact ordering should fail, got %v", err)
	}
	request, _ = DecodeRequest(readFixture(t, "request_v1.json"))
	request.Context.Rotation.Text += "changed"
	if err := request.Validate(); err == nil || !strings.Contains(err.Error(), "does not match text") {
		t.Fatalf("text identity drift should fail, got %v", err)
	}
}

func TestOneTraceRequiresTopologyProof(t *testing.T) {
	request, err := DecodeRequest(readFixture(t, "request_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	request.Stochastic.Seeds = request.Stochastic.Seeds[:1]
	if err := request.Validate(); err == nil || !strings.Contains(err.Error(), "requires topology proof") {
		t.Fatalf("one trace without proof should fail, got %v", err)
	}
	request.Stochastic.TopologyStabilityProofSHA256 = strings.Repeat("a", 64)
	if err := request.Validate(); err != nil {
		t.Fatalf("one trace with proof should pass: %v", err)
	}
}

func TestEveryContractRejectsUnknownVersion(t *testing.T) {
	compact, err := DecodeCompactIR(readFixture(t, "compact_ir_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	compact.SchemaVersion++
	if err := compact.Validate(); err == nil {
		t.Fatal("compact IR accepted unknown schema")
	}
	progress, err := DecodeProgress(readFixture(t, "progress_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	progress.SchemaVersion++
	if err := progress.Validate(); err == nil {
		t.Fatal("progress accepted unknown schema")
	}
	result, err := DecodeResult(readFixture(t, "result_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	result.SchemaVersion++
	if err := result.Validate(); err == nil {
		t.Fatal("result accepted unknown schema")
	}
}

func TestResultRejectsDuplicatePhysicalArtifact(t *testing.T) {
	result, err := DecodeResult(readFixture(t, "result_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	result.Winner[1].ArtifactID = result.Winner[0].ArtifactID
	if err := result.Validate(); err == nil || !strings.Contains(err.Error(), "repeats artifact_id") {
		t.Fatalf("duplicate artifact should fail, got %v", err)
	}
}

func TestCompactIRRejectsUnknownOperation(t *testing.T) {
	compact, err := DecodeCompactIR(readFixture(t, "compact_ir_v1.json"))
	if err != nil {
		t.Fatal(err)
	}
	compact.Members[0].Nodes[0].Operation = "character_specific_magic"
	if err := compact.Validate(); err == nil || !strings.Contains(err.Error(), "unsupported") {
		t.Fatalf("unknown operation should fail, got %v", err)
	}
}

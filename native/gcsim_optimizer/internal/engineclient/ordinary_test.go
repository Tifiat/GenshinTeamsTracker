package engineclient

import (
	"crypto/sha256"
	"encoding/hex"
	"math"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

func TestParseOrdinaryResult(t *testing.T) {
	payload := []byte(`{"statistics":{"iterations":1000,"dps":{"mean":148135.25,"sd":3162.2776601683795}}}`)
	result, err := ParseOrdinaryResult(payload, 1000)
	if err != nil {
		t.Fatal(err)
	}
	if result.DPS != 148135.25 || math.Abs(result.StandardError-100) > 1e-9 {
		t.Fatalf("unexpected result: %+v", result)
	}
}

func TestParseOrdinaryResultFailsClosed(t *testing.T) {
	tests := []struct {
		name    string
		payload string
		want    string
	}{
		{"iterations", `{"statistics":{"iterations":999,"dps":{"mean":1,"sd":1}}}`, "expected 1000"},
		{"negative", `{"statistics":{"iterations":1000,"dps":{"mean":-1,"sd":1}}}`, "statistics are invalid"},
		{"missing", `{}`, "iterations 0"},
		{"missing_dps", `{"statistics":{"iterations":1000}}`, "non-null DPS"},
		{"missing_sd", `{"statistics":{"iterations":1000,"dps":{"mean":100}}}`, "non-null DPS"},
		{"missing_mean", `{"statistics":{"iterations":1000,"dps":{"sd":1}}}`, "non-null DPS"},
		{"null", `{"statistics":{"iterations":1000,"dps":{"mean":null,"sd":null}}}`, "non-null DPS"},
	}
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			_, err := ParseOrdinaryResult([]byte(test.payload), 1000)
			if err == nil || !strings.Contains(err.Error(), test.want) {
				t.Fatalf("got %v; expected %q", err, test.want)
			}
		})
	}
}

func TestParseOrdinaryExplicitZeroAndAdditionalFields(t *testing.T) {
	result, err := ParseOrdinaryResult([]byte(`{"future":true,"statistics":{"iterations":1000,"dps":{"mean":0,"sd":0,"future":2}}}`), 1000)
	if err != nil || result.DPS != 0 || result.StandardError != 0 {
		t.Fatal(result, err)
	}
}

func TestBoundEngineDetectsStageMutation(t *testing.T) {
	path := filepath.Join(t.TempDir(), "engine.exe")
	original := []byte("bound-engine-v1")
	if err := os.WriteFile(path, original, 0o600); err != nil {
		t.Fatal(err)
	}
	digest := sha256.Sum256(original)
	request := contracts.OptimizerRequest{Engine: contracts.EngineBinding{
		BinaryPath: path, ArtifactSHA256: hex.EncodeToString(digest[:]),
	}}
	bound, err := BindEngine(request)
	if err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(path, []byte("bound-engine-v2"), 0o600); err != nil {
		t.Fatal(err)
	}
	if err := bound.VerifyUnchanged(); err == nil {
		t.Fatal("mutated engine passed the stage boundary")
	}
}

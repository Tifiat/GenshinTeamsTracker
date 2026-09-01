// Package engineclient owns verified subprocess calls to the bound GCSIM
// artifact. It does not know how candidates were searched or ranked.
package engineclient

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

type OrdinaryResult struct {
	Iterations         int
	DPS                float64
	StandardDeviation  float64
	StandardError      float64
	ElapsedMS          float64
	ConfigSHA256       string
	EngineResultSHA256 string
	ResultPath         string
}

type ordinaryPayload struct {
	Statistics struct {
		Iterations int `json:"iterations"`
		DPS        struct {
			Mean float64 `json:"mean"`
			SD   float64 `json:"sd"`
		} `json:"dps"`
	} `json:"statistics"`
}

// BoundEngine is an immutable, verified executable binding for one complete
// verification stage. Call VerifyUnchanged after the stage; individual
// candidates deliberately do not reread the executable.
type BoundEngine struct {
	binaryPath     string
	artifactSHA256 string
}

func BindEngine(request contracts.OptimizerRequest) (BoundEngine, error) {
	bound := BoundEngine{
		binaryPath:     request.Engine.BinaryPath,
		artifactSHA256: request.Engine.ArtifactSHA256,
	}
	if err := bound.VerifyUnchanged(); err != nil {
		return BoundEngine{}, fmt.Errorf("verify bound engine before stage: %w", err)
	}
	return bound, nil
}

func (bound BoundEngine) VerifyUnchanged() error {
	return verifyFileSHA256(bound.binaryPath, bound.artifactSHA256)
}

func RunOrdinary(ctx context.Context, request contracts.OptimizerRequest, configText, runDirectory string, expectedIterations, workers int) (OrdinaryResult, error) {
	bound, err := BindEngine(request)
	if err != nil {
		return OrdinaryResult{}, err
	}
	output, runErr := bound.RunOrdinary(ctx, configText, runDirectory, expectedIterations, workers)
	if verifyErr := bound.VerifyUnchanged(); verifyErr != nil {
		return OrdinaryResult{}, fmt.Errorf("bound engine changed during run: %w", verifyErr)
	}
	return output, runErr
}

func (bound BoundEngine) RunOrdinary(ctx context.Context, configText, runDirectory string, expectedIterations, workers int) (OrdinaryResult, error) {
	var output OrdinaryResult
	if expectedIterations <= 0 || workers <= 0 {
		return output, fmt.Errorf("expected iterations and workers must be positive")
	}
	if runDirectory == "" {
		return output, fmt.Errorf("run directory is required")
	}
	resolvedRunDirectory, err := filepath.Abs(runDirectory)
	if err != nil {
		return output, fmt.Errorf("resolve isolated run directory: %w", err)
	}
	if err := os.Mkdir(resolvedRunDirectory, 0o700); err != nil {
		return output, fmt.Errorf("create isolated run directory: %w", err)
	}
	configPath := filepath.Join(resolvedRunDirectory, "config.txt")
	resultPath := filepath.Join(resolvedRunDirectory, "result.json")
	if err := os.WriteFile(configPath, []byte(configText), 0o600); err != nil {
		return output, fmt.Errorf("write finalist config: %w", err)
	}
	configDigest := sha256.Sum256([]byte(configText))
	output.ConfigSHA256 = hex.EncodeToString(configDigest[:])
	command := exec.CommandContext(ctx, bound.binaryPath, "-c", configPath, "-out", resultPath)
	command.Dir = resolvedRunDirectory
	command.Env = append(os.Environ(), "GOMAXPROCS="+strconv.Itoa(workers))
	started := time.Now()
	combined, err := command.CombinedOutput()
	output.ElapsedMS = float64(time.Since(started)) / float64(time.Millisecond)
	if err != nil {
		if ctx.Err() != nil {
			return output, fmt.Errorf("ordinary simulation cancelled or timed out after %.3f ms: %w", output.ElapsedMS, ctx.Err())
		}
		return output, fmt.Errorf("ordinary simulation failed after %.3f ms: %w: %s", output.ElapsedMS, err, truncate(string(combined), 4000))
	}
	payload, err := os.ReadFile(resultPath)
	if err != nil {
		return output, fmt.Errorf("read ordinary result: %w", err)
	}
	parsed, err := ParseOrdinaryResult(payload, expectedIterations)
	if err != nil {
		return output, err
	}
	resultDigest := sha256.Sum256(payload)
	parsed.ElapsedMS = output.ElapsedMS
	parsed.ConfigSHA256 = output.ConfigSHA256
	parsed.EngineResultSHA256 = hex.EncodeToString(resultDigest[:])
	parsed.ResultPath = resultPath
	return parsed, nil
}

func ParseOrdinaryResult(payload []byte, expectedIterations int) (OrdinaryResult, error) {
	var output OrdinaryResult
	var decoded ordinaryPayload
	if err := json.Unmarshal(payload, &decoded); err != nil {
		return output, fmt.Errorf("decode ordinary result: %w", err)
	}
	if decoded.Statistics.Iterations != expectedIterations {
		return output, fmt.Errorf("ordinary result iterations %d; expected %d", decoded.Statistics.Iterations, expectedIterations)
	}
	mean, sd := decoded.Statistics.DPS.Mean, decoded.Statistics.DPS.SD
	if math.IsNaN(mean) || math.IsInf(mean, 0) || mean < 0 || math.IsNaN(sd) || math.IsInf(sd, 0) || sd < 0 {
		return output, fmt.Errorf("ordinary result DPS statistics are invalid")
	}
	output.Iterations = decoded.Statistics.Iterations
	output.DPS = mean
	output.StandardDeviation = sd
	output.StandardError = sd / math.Sqrt(float64(expectedIterations))
	return output, nil
}

func verifyFileSHA256(path, expected string) error {
	payload, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	digest := sha256.Sum256(payload)
	actual := hex.EncodeToString(digest[:])
	if actual != expected {
		return fmt.Errorf("artifact SHA-256 %s; expected %s", actual, expected)
	}
	return nil
}

func truncate(value string, limit int) string {
	if len(value) <= limit {
		return value
	}
	return value[:limit] + "..."
}

package engineclient

import (
	"context"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strconv"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

type CompactResult struct {
	Member                                 contracts.IRSeedMember
	Effects                                *contracts.EffectInputsOutput
	ConfigSHA256, ResultSHA256, ResultPath string
	ProcessMS, DecodeMS                    float64
}

// RunCompact captures one seed with the existing engine adapter protocol. It
// shares BoundEngine with ordinary verification; the stage owner verifies the
// binary before/after its whole bounded panel, not once per artifact candidate.
// The exact input config is preserved. Energy is passed explicitly by its owner.
func (bound BoundEngine) RunCompact(ctx context.Context, configText, runDirectory string, seed uint64, ignoreBurstEnergy bool) (CompactResult, error) {
	return bound.runCompact(ctx, configText, runDirectory, seed, ignoreBurstEnergy, false)
}

// Opt-in All Sets transport. A missing capability/sidecar is explicit, never a
// silent downgrade to raw-item-only hints. Legacy Selected calls are unchanged.
func (bound BoundEngine) RunCompactWithEffects(ctx context.Context, configText, runDirectory string, seed uint64, ignoreBurstEnergy bool) (CompactResult, error) {
	if !bound.effectInputs || bound.sourceManifestSHA256 == "" {
		return CompactResult{}, fmt.Errorf("bound engine lacks %s", contracts.EffectInputsCapability)
	}
	return bound.runCompact(ctx, configText, runDirectory, seed, ignoreBurstEnergy, true)
}

func (bound BoundEngine) runCompact(ctx context.Context, configText, runDirectory string, seed uint64, ignoreBurstEnergy, includeEffects bool) (CompactResult, error) {
	var out CompactResult
	if err := ctx.Err(); err != nil {
		return out, err
	}
	if bound.binaryPath == "" || configText == "" || runDirectory == "" {
		return out, fmt.Errorf("compact capture requires bound engine, config and isolated directory")
	}
	dir, err := filepath.Abs(runDirectory)
	if err != nil {
		return out, err
	}
	if err = os.Mkdir(dir, 0700); err != nil {
		return out, fmt.Errorf("create compact directory: %w", err)
	}
	configPath, requestPath, resultPath := filepath.Join(dir, "config.txt"), filepath.Join(dir, "capture-request.json"), filepath.Join(dir, "member.json")
	out.ConfigSHA256 = contracts.TextSHA256(configText)
	request := struct {
		SchemaVersion       int    `json:"schema_version"`
		OutputMode          string `json:"output_mode"`
		ContextSHA256       string `json:"context_sha256"`
		Seed                string `json:"seed"`
		Iterations          int    `json:"iterations"`
		Workers             int    `json:"workers"`
		IgnoreBurstEnergy   bool   `json:"ignore_burst_energy"`
		IncludeEffectInputs bool   `json:"include_effect_inputs,omitempty"`
	}{1, "compact_ir_v1", out.ConfigSHA256, strconv.FormatUint(seed, 10), 1, 1, ignoreBurstEnergy, includeEffects}
	payload, err := json.Marshal(request)
	if err != nil {
		return out, err
	}
	if err = os.WriteFile(configPath, []byte(configText), 0600); err != nil {
		return out, err
	}
	if err = os.WriteFile(requestPath, payload, 0600); err != nil {
		return out, err
	}
	cmd := exec.CommandContext(ctx, bound.binaryPath, "-c", configPath, "-out", resultPath, "-gtt-trace-equation", requestPath)
	cmd.Dir = dir
	cmd.Env = append(os.Environ(), "GOMAXPROCS=1")
	hideCaptureWindow(cmd)
	started := time.Now()
	combined, err := cmd.CombinedOutput()
	out.ProcessMS = float64(time.Since(started)) / float64(time.Millisecond)
	if err != nil {
		if ctx.Err() != nil {
			return out, fmt.Errorf("compact capture cancelled: %w", ctx.Err())
		}
		return out, fmt.Errorf("compact capture failed: %w: %s", err, truncate(string(combined), 4000))
	}
	started = time.Now()
	payload, err = os.ReadFile(resultPath)
	if err != nil {
		return out, err
	}
	out.Member, err = contracts.DecodeSeedMember(payload)
	if err != nil {
		return out, fmt.Errorf("compact result: %w", err)
	}
	if out.Member.Seed != seed {
		return out, fmt.Errorf("compact result seed mismatch")
	}
	if includeEffects {
		effectsPayload, err := os.ReadFile(resultPath + ".effects.json")
		if err != nil {
			return out, fmt.Errorf("compact effect sidecar: %w", err)
		}
		out.Effects, err = decodeEffectInputs(effectsPayload, payload, out.Member, out.ConfigSHA256, bound.sourceManifestSHA256)
		if err != nil {
			return out, err
		}
	}
	if err = ctx.Err(); err != nil {
		return out, err
	}
	out.DecodeMS = float64(time.Since(started)) / float64(time.Millisecond)
	out.ResultSHA256, out.ResultPath = contracts.TextSHA256(string(payload)), resultPath
	return out, nil
}

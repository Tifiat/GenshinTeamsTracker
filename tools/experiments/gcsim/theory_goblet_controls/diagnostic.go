package engineclient

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"os/exec"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

const (
	stage16TraceSchemaVersion        = 6
	stage16TraceCapability           = "gtt_trace_equation_v6"
	stage16TargetEnemy               = 0
	stage16TargetGadget              = 2
	stage16MaxSeed            uint64 = 1<<63 - 1
)

var stage16ImportPattern = regexp.MustCompile(`^import "(.+)"$`)
var stage16SHA256Pattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

// Stage16ActorDamage is the observed enemy-hit damage assigned to one trace
// actor. Actors are kept in the exact character_keys order reported by GCSIM.
type Stage16ActorDamage struct {
	CharacterKey string
	Damage       float64
	HitCount     int
}

// Stage16DiagnosticResult contains a bounded summary of one schema-6 trace.
// ResultPath points to the retained raw trace inside the isolated job folder.
type Stage16DiagnosticResult struct {
	Seed               uint64
	DPS                float64
	DurationFrames     int64
	HitCount           int
	AllHitCount        int
	NonEnemyHitCount   int
	CharacterKeys      []string
	PerActorDamage     []Stage16ActorDamage
	UnsupportedCodes   []string
	ConfigSHA256       string
	SourceConfigSHA256 string
	RequestSHA256      string
	FormulaSHA256      string
	TargetSHA256       string
	ResultSHA256       string
	ElapsedMS          float64
	ResultPath         string
}

type stage16TraceRequest struct {
	SchemaVersion       int    `json:"schema_version"`
	ContextSHA256       string `json:"context_sha256"`
	Seed                string `json:"seed"`
	Iterations          int    `json:"iterations"`
	Workers             int    `json:"workers"`
	IgnoreBurstEnergy   bool   `json:"ignore_burst_energy"`
	OutputMode          string `json:"output_mode,omitempty"`
	IncludeEffectInputs bool   `json:"include_effect_inputs,omitempty"`
}

// stage16TraceRequestWire deliberately serializes the false effect-input flag
// while leaving output_mode absent. The engine re-marshals its own request
// type, whose false effect-input flag is omitted, when producing request_sha256.
type stage16TraceRequestWire struct {
	SchemaVersion       int    `json:"schema_version"`
	ContextSHA256       string `json:"context_sha256"`
	Seed                string `json:"seed"`
	Iterations          int    `json:"iterations"`
	Workers             int    `json:"workers"`
	IgnoreBurstEnergy   bool   `json:"ignore_burst_energy"`
	IncludeEffectInputs bool   `json:"include_effect_inputs"`
}

type stage16TraceDocument struct {
	SchemaVersion      *int               `json:"schema_version"`
	Capability         *string            `json:"capability"`
	ContextSHA256      *string            `json:"context_sha256"`
	RequestSHA256      *string            `json:"request_sha256"`
	SourceConfigSHA256 *string            `json:"source_config_sha256"`
	FormulaSHA256      *string            `json:"formula_sha256"`
	TargetSHA256       *string            `json:"target_sha256"`
	Seed               *string            `json:"seed"`
	DurationFrames     *int64             `json:"duration_frames"`
	CharacterKeys      *[]string          `json:"character_keys"`
	Hits               *[]stage16TraceHit `json:"hits"`
	Unsupported        json.RawMessage    `json:"unsupported"`
}

type stage16TraceHit struct {
	HitID          *uint64         `json:"hit_id"`
	ActorIndex     *int            `json:"actor_index"`
	TargetType     *int            `json:"target_type"`
	ReportedDamage *float64        `json:"reported_damage"`
	Unsupported    json.RawMessage `json:"unsupported"`
}

// RunStage16Diagnostic observes one actual ordinary simulation through the
// seeded raw trace route. It creates no compact model and has no fallback.
func (bound BoundEngine) RunStage16Diagnostic(ctx context.Context, configText, runDirectory string, seed uint64) (Stage16DiagnosticResult, error) {
	var output Stage16DiagnosticResult
	if ctx == nil {
		return output, fmt.Errorf("stage-16 diagnostic requires a context")
	}
	if err := ctx.Err(); err != nil {
		return output, err
	}
	if bound.binaryPath == "" || configText == "" || runDirectory == "" {
		return output, fmt.Errorf("stage-16 diagnostic requires bound engine, config and isolated directory")
	}
	if seed == 0 || seed > stage16MaxSeed {
		return output, fmt.Errorf("stage-16 diagnostic seed must be a positive int64")
	}

	dir, err := filepath.Abs(runDirectory)
	if err != nil {
		return output, fmt.Errorf("resolve stage-16 diagnostic directory: %w", err)
	}
	if err = os.Mkdir(dir, 0o700); err != nil {
		return output, fmt.Errorf("create stage-16 diagnostic directory: %w", err)
	}
	configPath := filepath.Join(dir, "config.txt")
	requestPath := filepath.Join(dir, "trace-request.json")
	resultPath := filepath.Join(dir, "trace-result.json")
	if err = os.WriteFile(configPath, []byte(configText), 0o600); err != nil {
		return output, fmt.Errorf("write stage-16 diagnostic config: %w", err)
	}
	configSHA := contracts.TextSHA256(configText)
	sourceConfigSHA, err := stage16SourceConfigSHA256(configPath, dir)
	if err != nil {
		return output, fmt.Errorf("bind stage-16 source config: %w", err)
	}
	canonicalRequest := stage16TraceRequest{
		SchemaVersion: 1, ContextSHA256: configSHA, Seed: strconv.FormatUint(seed, 10),
		Iterations: 1, Workers: 1, IgnoreBurstEnergy: true,
	}
	canonicalRequestBytes, err := json.Marshal(canonicalRequest)
	if err != nil {
		return output, fmt.Errorf("encode stage-16 trace request binding: %w", err)
	}
	requestSHA := contracts.TextSHA256(string(canonicalRequestBytes))
	wireRequest := stage16TraceRequestWire{
		SchemaVersion: 1, ContextSHA256: configSHA, Seed: strconv.FormatUint(seed, 10),
		Iterations: 1, Workers: 1, IgnoreBurstEnergy: true, IncludeEffectInputs: false,
	}
	requestBytes, err := json.Marshal(wireRequest)
	if err != nil {
		return output, fmt.Errorf("encode stage-16 trace request: %w", err)
	}
	if err = os.WriteFile(requestPath, requestBytes, 0o600); err != nil {
		return output, fmt.Errorf("write stage-16 trace request: %w", err)
	}

	command := exec.CommandContext(ctx, bound.binaryPath, "-c", configPath, "-out", resultPath, "-gtt-trace-equation", requestPath)
	command.Dir = dir
	command.Env = append(os.Environ(), "GOMAXPROCS=1")
	hideCaptureWindow(command)
	started := time.Now()
	combined, runErr := command.CombinedOutput()
	processMS := float64(time.Since(started)) / float64(time.Millisecond)
	if runErr != nil {
		if ctx.Err() != nil {
			return Stage16DiagnosticResult{ElapsedMS: processMS}, fmt.Errorf("stage-16 diagnostic cancelled: %w", ctx.Err())
		}
		return Stage16DiagnosticResult{ElapsedMS: processMS}, fmt.Errorf("stage-16 diagnostic failed: %w: %s", runErr, truncate(string(combined), 4000))
	}
	if err = ctx.Err(); err != nil {
		return output, err
	}
	payload, err := os.ReadFile(resultPath)
	if err != nil {
		return output, fmt.Errorf("read stage-16 raw trace: %w", err)
	}
	output, err = parseStage16Trace(payload, seed, configSHA, sourceConfigSHA, requestSHA)
	if err != nil {
		return Stage16DiagnosticResult{}, err
	}
	if err = ctx.Err(); err != nil {
		return Stage16DiagnosticResult{}, err
	}
	output.ElapsedMS = processMS
	output.ResultPath = resultPath
	return output, nil
}

func parseStage16Trace(payload []byte, expectedSeed uint64, expectedConfigSHA, expectedSourceConfigSHA, expectedRequestSHA string) (Stage16DiagnosticResult, error) {
	var output Stage16DiagnosticResult
	if expectedSeed == 0 || expectedSeed > stage16MaxSeed {
		return output, fmt.Errorf("stage-16 expected seed must be a positive int64")
	}
	for label, value := range map[string]string{
		"config": expectedConfigSHA, "source config": expectedSourceConfigSHA, "request": expectedRequestSHA,
	} {
		if !stage16SHA256Pattern.MatchString(value) {
			return output, fmt.Errorf("stage-16 expected %s SHA-256 is malformed", label)
		}
	}
	var document stage16TraceDocument
	if err := json.Unmarshal(payload, &document); err != nil {
		return output, fmt.Errorf("decode stage-16 trace result: %w", err)
	}
	if document.SchemaVersion == nil || *document.SchemaVersion != stage16TraceSchemaVersion ||
		document.Capability == nil || *document.Capability != stage16TraceCapability {
		return output, fmt.Errorf("stage-16 trace schema/capability mismatch")
	}
	if document.Seed == nil || *document.Seed != strconv.FormatUint(expectedSeed, 10) {
		return output, fmt.Errorf("stage-16 trace seed mismatch")
	}
	if document.ContextSHA256 == nil || *document.ContextSHA256 != expectedConfigSHA {
		return output, fmt.Errorf("stage-16 trace context/config SHA-256 mismatch")
	}
	if document.RequestSHA256 == nil || *document.RequestSHA256 != expectedRequestSHA {
		return output, fmt.Errorf("stage-16 trace request SHA-256 mismatch")
	}
	if document.SourceConfigSHA256 == nil || *document.SourceConfigSHA256 != expectedSourceConfigSHA {
		return output, fmt.Errorf("stage-16 trace source config SHA-256 mismatch")
	}
	if document.FormulaSHA256 == nil || !stage16SHA256Pattern.MatchString(*document.FormulaSHA256) ||
		document.TargetSHA256 == nil || !stage16SHA256Pattern.MatchString(*document.TargetSHA256) {
		return output, fmt.Errorf("stage-16 trace formula/target SHA-256 is malformed")
	}
	if document.DurationFrames == nil || *document.DurationFrames <= 0 {
		return output, fmt.Errorf("stage-16 trace duration_frames must be positive")
	}
	if document.CharacterKeys == nil || len(*document.CharacterKeys) != 4 {
		return output, fmt.Errorf("stage-16 trace must bind exactly four character keys")
	}
	characters := append([]string(nil), (*document.CharacterKeys)...)
	seenCharacters := make(map[string]struct{}, len(characters))
	for _, character := range characters {
		if strings.TrimSpace(character) == "" {
			return output, fmt.Errorf("stage-16 trace character key is empty")
		}
		if _, exists := seenCharacters[character]; exists {
			return output, fmt.Errorf("stage-16 trace repeats character key %q", character)
		}
		seenCharacters[character] = struct{}{}
	}
	if document.Hits == nil {
		return output, fmt.Errorf("stage-16 trace hits are missing")
	}
	actorDamage := make([]float64, len(characters))
	actorHits := make([]int, len(characters))
	seenHitIDs := make(map[uint64]struct{}, len(*document.Hits))
	unsupported := make(map[string]struct{})
	rootUnsupported, err := decodeStage16Unsupported(document.Unsupported)
	if err != nil {
		return output, fmt.Errorf("stage-16 trace: %w", err)
	}
	if err := addStage16Unsupported(unsupported, rootUnsupported); err != nil {
		return output, err
	}
	var enemyDamage float64
	enemyHitCount, nonEnemyHitCount := 0, 0
	for index, hit := range *document.Hits {
		if hit.HitID == nil || *hit.HitID == 0 {
			return output, fmt.Errorf("stage-16 hit %d has invalid hit_id", index)
		}
		if _, exists := seenHitIDs[*hit.HitID]; exists {
			return output, fmt.Errorf("stage-16 trace repeats hit_id %d", *hit.HitID)
		}
		seenHitIDs[*hit.HitID] = struct{}{}
		if hit.ActorIndex == nil || *hit.ActorIndex < 0 || *hit.ActorIndex >= len(characters) {
			return output, fmt.Errorf("stage-16 hit %d has invalid actor_index", index)
		}
		if hit.TargetType == nil || *hit.TargetType < stage16TargetEnemy || *hit.TargetType > stage16TargetGadget {
			return output, fmt.Errorf("stage-16 hit %d has invalid target_type", index)
		}
		if hit.ReportedDamage == nil || math.IsNaN(*hit.ReportedDamage) || math.IsInf(*hit.ReportedDamage, 0) || *hit.ReportedDamage < 0 {
			return output, fmt.Errorf("stage-16 hit %d has invalid reported_damage", index)
		}
		hitUnsupported, err := decodeStage16Unsupported(hit.Unsupported)
		if err != nil {
			return output, fmt.Errorf("stage-16 hit %d: %w", index, err)
		}
		if err := addStage16Unsupported(unsupported, hitUnsupported); err != nil {
			return output, fmt.Errorf("stage-16 hit %d: %w", index, err)
		}
		if *hit.TargetType != stage16TargetEnemy {
			nonEnemyHitCount++
			continue
		}
		enemyHitCount++
		enemyDamage += *hit.ReportedDamage
		actorDamage[*hit.ActorIndex] += *hit.ReportedDamage
		actorHits[*hit.ActorIndex]++
		if math.IsNaN(enemyDamage) || math.IsInf(enemyDamage, 0) ||
			math.IsNaN(actorDamage[*hit.ActorIndex]) || math.IsInf(actorDamage[*hit.ActorIndex], 0) {
			return output, fmt.Errorf("stage-16 enemy damage total is not finite")
		}
	}
	dps := enemyDamage * 60 / float64(*document.DurationFrames)
	if math.IsNaN(dps) || math.IsInf(dps, 0) || dps < 0 {
		return output, fmt.Errorf("stage-16 observed DPS is not finite")
	}
	unsupportedCodes := make([]string, 0, len(unsupported))
	for code := range unsupported {
		unsupportedCodes = append(unsupportedCodes, code)
	}
	sort.Strings(unsupportedCodes)
	perActor := make([]Stage16ActorDamage, len(characters))
	for index, character := range characters {
		perActor[index] = Stage16ActorDamage{CharacterKey: character, Damage: actorDamage[index], HitCount: actorHits[index]}
	}
	output.Seed = expectedSeed
	output.DPS = dps
	output.DurationFrames = *document.DurationFrames
	output.HitCount = enemyHitCount
	output.AllHitCount = len(*document.Hits)
	output.NonEnemyHitCount = nonEnemyHitCount
	output.CharacterKeys = characters
	output.PerActorDamage = perActor
	output.UnsupportedCodes = unsupportedCodes
	output.ConfigSHA256 = expectedConfigSHA
	output.SourceConfigSHA256 = expectedSourceConfigSHA
	output.RequestSHA256 = expectedRequestSHA
	output.FormulaSHA256 = *document.FormulaSHA256
	output.TargetSHA256 = *document.TargetSHA256
	output.ResultSHA256 = contracts.TextSHA256(string(payload))
	return output, nil
}

func addStage16Unsupported(destination map[string]struct{}, codes []string) error {
	for _, code := range codes {
		if strings.TrimSpace(code) == "" {
			return fmt.Errorf("stage-16 trace has an empty unsupported code")
		}
		destination[code] = struct{}{}
	}
	return nil
}

func decodeStage16Unsupported(raw json.RawMessage) ([]string, error) {
	if len(raw) == 0 {
		return nil, fmt.Errorf("unsupported codes are missing")
	}
	if strings.TrimSpace(string(raw)) == "null" {
		return nil, nil
	}
	var codes []string
	if err := json.Unmarshal(raw, &codes); err != nil {
		return nil, fmt.Errorf("unsupported codes are malformed: %w", err)
	}
	return codes, nil
}

// stage16SourceConfigSHA256 mirrors the active simulator ReadConfig behavior:
// normalize CRLF, add LF after each non-import row, and inline import bytes.
func stage16SourceConfigSHA256(configPath, runDirectory string) (string, error) {
	payload, err := os.ReadFile(configPath)
	if err != nil {
		return "", err
	}
	rows := strings.Split(strings.ReplaceAll(string(payload), "\r\n", "\n"), "\n")
	var expanded strings.Builder
	for _, row := range rows {
		match := stage16ImportPattern.FindStringSubmatch(row)
		if match == nil {
			expanded.WriteString(row)
			expanded.WriteByte('\n')
			continue
		}
		importPath := path.Join(path.Dir(configPath), match[1])
		if !filepath.IsAbs(filepath.FromSlash(importPath)) {
			importPath = filepath.Join(runDirectory, filepath.FromSlash(importPath))
		} else {
			importPath = filepath.FromSlash(importPath)
		}
		imported, readErr := os.ReadFile(importPath)
		if readErr != nil {
			return "", fmt.Errorf("read imported config %q: %w", match[1], readErr)
		}
		expanded.Write(imported)
	}
	return contracts.TextSHA256(expanded.String()), nil
}

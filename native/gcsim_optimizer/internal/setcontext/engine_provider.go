package setcontext

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"reflect"
	"regexp"
	"strconv"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/engineclient"
)

var captureOptions = regexp.MustCompile(`(?m)^[ \t]*options[ \t]+([^;\r\n]+);[ \t]*\r?$`)

type CaptureTiming struct {
	ContextSHA256 string  `json:"context_sha256"`
	Seed          uint64  `json:"seed"`
	ProcessMS     float64 `json:"process_ms"`
	DecodeMS      float64 `json:"decode_ms"`
	ResultSHA256  string  `json:"result_sha256"`
}

// EngineProvider uses one verified binary and isolated run root for a stage.
// It accepts exactly the configured panel (at least two seeds), never n1 search.
// It is still separate from the installed Selected/UI route. Call Close even
// after failure/cancellation to check that the executable did not change.
type EngineProvider struct {
	bound          engineclient.BoundEngine
	binding        Binding
	root           string
	timings        []CaptureTiming
	closed         bool
	includeEffects bool
}

func NewEngineProvider(binding Binding, runRoot string) (*EngineProvider, error) {
	if len(binding.Seeds) < 2 {
		return nil, fmt.Errorf("All Sets capture requires at least two seeds")
	}
	for i := 1; i < len(binding.Seeds); i++ {
		if binding.Seeds[i-1] >= binding.Seeds[i] {
			return nil, fmt.Errorf("capture seeds must be strictly sorted and distinct")
		}
	}
	if runRoot == "" {
		return nil, fmt.Errorf("isolated run root required")
	}
	root, err := filepath.Abs(runRoot)
	if err != nil {
		return nil, err
	}
	info, err := os.Stat(root)
	if err != nil || !info.IsDir() {
		return nil, fmt.Errorf("capture root must be an existing directory")
	}
	bound, err := engineclient.BindEngine(contracts.OptimizerRequest{Engine: binding.Engine})
	if err != nil {
		return nil, err
	}
	binding.Seeds = append([]uint64(nil), binding.Seeds...)
	binding.Engine.Capabilities = append([]string(nil), binding.Engine.Capabilities...)
	return &EngineProvider{bound: bound, binding: binding, root: root}, nil
}

// The production-directed All Sets route requires typed source-bound inputs.
// The legacy constructor remains only for existing isolated capture receipts.
func NewEffectEngineProvider(binding Binding, runRoot string) (*EngineProvider, error) {
	found := false
	for _, capability := range binding.Engine.Capabilities {
		found = found || capability == contracts.EffectInputsCapability
	}
	if !found {
		return nil, fmt.Errorf("All Sets requires %s", contracts.EffectInputsCapability)
	}
	p, err := NewEngineProvider(binding, runRoot)
	if err != nil {
		return nil, err
	}
	p.includeEffects = true
	return p, nil
}

func IgnoreBurstEnergy(text string) (bool, error) {
	rows := captureOptions.FindAllStringSubmatch(text, -1)
	if len(rows) != 1 {
		return false, fmt.Errorf("capture requires one prepared options row")
	}
	found := false
	value := false
	for _, field := range strings.Fields(rows[0][1]) {
		if !strings.HasPrefix(field, "ignore_burst_energy=") {
			continue
		}
		if found {
			return false, fmt.Errorf("duplicate energy option")
		}
		found = true
		var err error
		value, err = strconv.ParseBool(strings.TrimPrefix(field, "ignore_burst_energy="))
		if err != nil {
			return false, fmt.Errorf("invalid energy option")
		}
	}
	if !found {
		return false, fmt.Errorf("explicit energy option required; no implicit override")
	}
	return value, nil
}

func (p *EngineProvider) Capture(ctx context.Context, c *Context) (Capture, error) {
	var out Capture
	if p == nil || p.closed || c == nil {
		return out, fmt.Errorf("capture provider unavailable")
	}
	if err := ctx.Err(); err != nil {
		return out, err
	}
	if !reflect.DeepEqual(p.binding, c.binding) {
		return out, fmt.Errorf("capture provider binding changed")
	}
	_, err := IgnoreBurstEnergy(c.text)
	if err != nil {
		return out, err
	}
	dir := filepath.Join(p.root, "context-"+c.key)
	if err = os.Mkdir(dir, 0700); err != nil {
		return out, fmt.Errorf("context directory already exists or unavailable: %w", err)
	}
	out = Capture{ContextSHA256: c.key, ConfigSHA256: c.configSHA, EngineBindingSHA256: c.binding.Engine.BindingSHA256}
	for _, seed := range c.binding.Seeds {
		capture := p.bound.RunCompact
		if p.includeEffects {
			capture = p.bound.RunCompactWithEffects
		}
		// A formula capture observes the complete intended rotation even when
		// the product config enables real burst costs. Ordinary finalist runs
		// retain c.text unchanged and remain the feasibility authority.
		result, err := capture(ctx, c.text, filepath.Join(dir, "seed-"+strconv.FormatUint(seed, 10)), seed, true)
		p.timings = append(p.timings, CaptureTiming{c.key, seed, result.ProcessMS, result.DecodeMS, result.ResultSHA256})
		if err != nil {
			return Capture{}, err
		}
		if result.ConfigSHA256 != c.configSHA {
			return Capture{}, fmt.Errorf("captured config mismatch")
		}
		out.Members = append(out.Members, result.Member)
		if p.includeEffects {
			out.Effects = append(out.Effects, *result.Effects)
		}
	}
	return out, nil
}

func (p *EngineProvider) Timings() []CaptureTiming { return append([]CaptureTiming(nil), p.timings...) }
func (p *EngineProvider) Close() error {
	if p == nil {
		return fmt.Errorf("nil capture provider")
	}
	p.closed = true
	return p.bound.VerifyUnchanged()
}

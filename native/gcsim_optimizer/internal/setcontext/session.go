package setcontext

import (
	"context"
	"fmt"
	"reflect"
	"sort"
	"strconv"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

// CaptureProvider must bind its actual config/engine invocation to this
// envelope. EngineProvider binds actual subprocess calls; tests can replay
// previously captured fixtures. Callers cannot hand
// an unbound IR member to the session and call it the new package's formula.
type Capture struct {
	ContextSHA256       string
	ConfigSHA256        string
	EngineBindingSHA256 string
	Members             []contracts.IRSeedMember
	Effects             []contracts.EffectInputsOutput
}
type CaptureProvider func(context.Context, *Context) (Capture, error)

type compiledContext struct {
	origin        *Context
	graphSHA      string
	coordinates   []string
	panel         *evaluator.Panel
	hits          int
	effectCapture *Capture
}

type Handle struct {
	context  *Context
	compiled *compiledContext
	decision Decision
}

func (h *Handle) Route() Route            { return h.decision.Route }
func (h *Handle) Reason() string          { return h.decision.Reason }
func (h *Handle) HitCount() int           { return h.compiled.hits }
func (h *Handle) GraphSHA256() string     { return h.compiled.graphSHA }
func (h *Handle) ContextKey() string      { return h.context.key }
func (h *Handle) Sets(actor string) []Set { return h.context.Sets(actor) }
func (h *Handle) SourceIdentity() (string, string, string) {
	b := h.context.binding
	return b.Engine.ArtifactSHA256, b.Engine.SourceManifestSHA256, b.CatalogSHA256
}

// EvaluateDPS deliberately reuses the shared Go compiler. This adapter is not
// another formula implementation. Exact captured handles also expose the
// same compiled panel to the shared FGBS hot path through SearchPanel.
func (h *Handle) EvaluateDPS(rawArtifactDeltas map[string]float64) (float64, error) {
	if h == nil || h.compiled == nil {
		return 0, fmt.Errorf("missing compiled context")
	}
	d := h.decision
	if d.Route == FreshCapture {
		d.Route = IdentityReuse
	} // new graph already contains its own set effects
	composed, err := d.ComposeDeltas(rawArtifactDeltas)
	if err != nil {
		return 0, err
	}
	dense := make([]float64, len(h.compiled.coordinates))
	for i, key := range h.compiled.coordinates {
		dense[i] = composed[key]
		delete(composed, key)
	}
	for key, value := range composed {
		if value != 0 {
			return 0, fmt.Errorf("unrepresented evaluation coordinate: %s", key)
		}
	}
	return h.compiled.panel.EvaluateDPS(dense)
}

// SearchPanel is available only for a graph captured for this exact context.
// Static-bias contexts need a bias-aware dense search adapter, not accidental
// direct access that would drop the replacement. No such producer is enabled.
func (h *Handle) SearchPanel() (*evaluator.Panel, error) {
	if h == nil || h.compiled == nil || h.context.key != h.compiled.origin.key {
		return nil, fmt.Errorf("search requires an exact captured context")
	}
	return h.compiled.panel, nil
}

// VisitEffectSnapshots borrows read-only graph/evidence slices for one guide
// compilation; callbacks must not mutate or retain them. No JSON round trip or
// graph deep-copy in the hot path. Substituted/static-bias handles are rejected.
func (h *Handle) VisitEffectSnapshots(visit func(contracts.IRSeedMember, contracts.EffectInputsOutput) error) error {
	if h == nil || h.compiled == nil || h.context.key != h.compiled.origin.key || h.compiled.effectCapture == nil || visit == nil {
		return fmt.Errorf("guide requires source inputs for its exact captured context")
	}
	c := h.compiled.effectCapture
	for i, member := range c.Members {
		if err := visit(member, c.Effects[i]); err != nil {
			return err
		}
	}
	return nil
}

// Session is sequential, run-local and bounded by explicit seed-member calls.
// Failed attempts spend their reservation; no hidden retry or broad fallback.
// The outer run context supplies the shared wall-clock/cancellation deadline.
type Session struct {
	provider         CaptureProvider
	limit, attempted int
	cache            map[string]*compiledContext
}

func NewSession(provider CaptureProvider, maxCaptureMembers int) (*Session, error) {
	if provider == nil || maxCaptureMembers < 0 {
		return nil, fmt.Errorf("invalid capture provider/budget")
	}
	return &Session{provider: provider, limit: maxCaptureMembers, cache: map[string]*compiledContext{}}, nil
}

func (s *Session) AttemptedCaptureMembers() int { return s.attempted }

func (s *Session) Resolve(ctx context.Context, target *Context, base *Handle, proof *StaticProof) (*Handle, error) {
	if s == nil || target == nil {
		return nil, fmt.Errorf("missing session/target")
	}
	if err := ctx.Err(); err != nil {
		return nil, err
	}
	if cached := s.cache[target.key]; cached != nil {
		return &Handle{target, cached, Decision{Route: IdentityReuse, Reason: "cached_complete_context", FromContextSHA256: target.key, ToContextSHA256: target.key}}, nil
	}
	d := Decision{Route: FreshCapture, Reason: "no_captured_context", ToContextSHA256: target.key}
	if base != nil && base.compiled != nil {
		// Never chain biases on an already substituted graph. Always prove a
		// transition from the actual captured origin, so A->B->C cannot retain B.
		d = Decide(base.compiled.origin, target, base.compiled.graphSHA, base.compiled.coordinates, proof)
		if d.Route != FreshCapture {
			return &Handle{target, base.compiled, d}, nil
		}
	}
	if len(target.binding.Seeds) > s.limit-s.attempted {
		return nil, fmt.Errorf("context capture budget exhausted")
	}
	s.attempted += len(target.binding.Seeds)
	capture, err := s.provider(ctx, target)
	if err != nil {
		return nil, err
	}
	if err = ctx.Err(); err != nil {
		return nil, err
	}
	compiled, err := compileCapture(target, capture)
	if err != nil {
		return nil, err
	}
	if err = ctx.Err(); err != nil {
		return nil, err
	}
	s.cache[target.key] = compiled
	return &Handle{target, compiled, d}, nil
}

func compileCapture(target *Context, capture Capture) (*compiledContext, error) {
	if capture.ContextSHA256 != target.key || capture.ConfigSHA256 != target.configSHA || capture.EngineBindingSHA256 != target.binding.Engine.BindingSHA256 {
		return nil, fmt.Errorf("capture context/config/engine identity mismatch")
	}
	if len(capture.Members) != len(target.binding.Seeds) {
		return nil, fmt.Errorf("capture seed panel incomplete")
	}
	compiled := &compiledContext{origin: target, coordinates: graphCoordinates(capture.Members)}
	if capture.Effects != nil {
		if len(capture.Effects) != len(capture.Members) {
			return nil, fmt.Errorf("effect input panel incomplete")
		}
		for i, e := range capture.Effects {
			if e.Capability != contracts.EffectInputsCapability || e.SchemaVersion != 1 || e.ContextSHA256 != target.configSHA || e.InputConfigSHA256 != target.configSHA || e.SourceManifestBodySHA256 != target.binding.Engine.SourceManifestSHA256 || e.Seed != strconv.FormatUint(capture.Members[i].Seed, 10) || !reflect.DeepEqual(e.CharacterKeys, target.actors) {
				return nil, fmt.Errorf("effect input context/config/source/owner mismatch")
			}
		}
		compiled.effectCapture = &capture
	}
	var err error
	compiled.graphSHA, err = contracts.CanonicalSHA256(capture.Members)
	if err != nil {
		return nil, err
	}
	actors := append([]string(nil), target.actors...)
	sort.Strings(actors) // numeric wearer indexes follow the canonical artifact domain, not initialization order
	compiled.panel, err = evaluator.CompileMembers(actors, target.binding.Seeds, capture.Members)
	if err != nil {
		return nil, err
	}
	for _, member := range capture.Members {
		for _, channel := range member.Channels {
			compiled.hits += channel.HitCount
		}
	}
	return compiled, nil
}

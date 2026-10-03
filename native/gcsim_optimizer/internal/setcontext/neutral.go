package setcontext

// Source-bound bridge from one owned neutral capture to search views. Ordinary
// set changes only bind effect expressions to the retained aggregate. Unknown
// rules return explicit boundaries; this API never silently captures a set.
import (
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"genshinteamstracker/native/gcsim_optimizer/internal/seteffects"
	"strings"
	"time"
)

type contextDispatch struct {
	key         [32]byte
	uncertainty []string
}

type NeutralModel struct {
	targetPrograms           map[string]contextDispatch
	origin                   *Context
	panel                    *evaluator.Panel
	binding                  *seteffects.NeutralBinding
	prepared                 *formula.ParametricProgram
	graphSHA                 string
	hits                     int
	owners                   map[string]int
	stats                    NeutralModelStats
	programCache             map[[32]byte]*formula.ParametricProgram
	programOrder             [][32]byte
	programNodes             int
	specializations          *formula.SpecializationCache
	effectKeys, constantKeys []string
	constantDimensions       []int
	effectDimensions         []int
}

// Preparation costs are recorded independently of item enumeration. These are
// run-local measurements, not speed claims based on reduced node counts.
type NeutralModelStats struct {
	Requests, Unavailable                         int
	RegionReuse                                   formula.RegionBindingStats
	DispatchHits                                  int
	ProgramHits, ProgramMisses                    int
	ConstantVectorBindings, ExpressionMapBindings int
	RuleSeconds, BindSeconds, ViewSeconds         float64
	ConstantBindSeconds, SymbolicBindSeconds      float64
	Specialization                                formula.SpecializationStats
	EffectInputs, ConstantDamageInputs            int
	Preparation                                   seteffects.NeutralPreparationStats
}

func (m *NeutralModel) Stats() NeutralModelStats {
	stats := m.stats
	stats.RegionReuse = m.prepared.RegionBindingStats()
	stats.Preparation = m.binding.PreparationStats()
	if m.specializations != nil {
		stats.Specialization = m.specializations.Stats()
	}
	return stats
}

// NewNeutralModel transfers the validated effect evidence out of the capture
// handle, rather than retaining the borrowed VisitEffectSnapshots slices. The
// arithmetic/identity handle remains usable; capture/energy borrowing ends.
// Compile any neutral energy ledger before this one-way transfer.
func NewNeutralModel(h *Handle, sources *seteffects.SourceCatalog) (*NeutralModel, error) {
	if h == nil || h.compiled == nil || h.compiled.effectCapture == nil || h.context.key != h.compiled.origin.key || sources == nil {
		return nil, fmt.Errorf("owned neutral capture required")
	}
	engine, source, catalog := h.SourceIdentity()
	if engine != sources.EngineSHA256 || source != sources.SourceManifestSHA256 || catalog != sources.CatalogSHA256 {
		return nil, fmt.Errorf("neutral rules differ from captured source")
	}
	for _, actor := range h.context.actors {
		if len(h.context.Sets(actor)) != 0 {
			return nil, fmt.Errorf("neutral model contains original set bonuses")
		}
	}
	capture := h.compiled.effectCapture
	binding, err := seteffects.NewNeutralBinding(sources, capture.Effects)
	if err != nil {
		return nil, err
	}
	prepared, err := h.compiled.panel.PrepareEffectInputsWithReads(binding.Ports(), binding.Reads())
	if err != nil {
		return nil, err
	}
	model := &NeutralModel{origin: h.context, panel: h.compiled.panel, binding: binding, prepared: prepared, graphSHA: h.compiled.graphSHA, hits: h.compiled.hits, owners: map[string]int{}}
	model.specializations = formula.NewSpecializationCache(neutralProgramEntries, neutralProgramNodes)
	for i, actor := range h.context.actors {
		model.owners[actor] = i
	}
	h.compiled.effectCapture = nil
	h.compiled.capture = nil
	return model, nil
}

func (m *NeutralModel) Resolve(target *Context) (*Handle, []string, error) {
	if m == nil || target == nil || !m.origin.SameFrame(target) {
		return nil, nil, fmt.Errorf("neutral target differs from captured run frame")
	}
	m.stats.Requests++
	if known, ok := m.targetPrograms[target.key]; ok {
		if program := m.programCache[known.key]; program != nil {
			m.stats.DispatchHits++
			return m.contextView(target, program, known.uncertainty)
		}
	}
	choices := []seteffects.RuleChoice{}
	for _, actor := range target.actors {
		owner, ok := m.owners[actor]
		if !ok {
			return nil, nil, fmt.Errorf("neutral target changed owner identity")
		}
		for _, set := range target.Sets(actor) {
			if strings.TrimSpace(set.Parameters) != "" {
				return nil, []string{"set_parameters_not_bound:" + actor + ":" + set.UID}, nil
			}
			choices = append(choices, seteffects.RuleChoice{Owner: owner, Key: set.UID, Pieces: set.Count})
		}
	}
	start := time.Now()
	effects := m.binding.CompilePackagesSparse(choices)
	m.stats.RuleSeconds += time.Since(start).Seconds()
	if !effects.Complete() {
		m.stats.Unavailable++
		return nil, append([]string(nil), effects.Boundaries...), nil
	}
	start = time.Now()
	var program *formula.ParametricProgram
	var err error
	if effects.SparseEffects != nil {
		m.stats.ExpressionMapBindings++
		program, err = m.bindMixed(effects.Constants, effects.SparseEffects)
	} else if effects.Constants != nil {
		m.stats.ConstantVectorBindings++
		program, err = m.bindConstants(effects.Constants)
	} else {
		m.stats.ExpressionMapBindings++
		program, err = m.bindProgram(effects.Effects)
	}
	m.stats.BindSeconds += time.Since(start).Seconds()
	if err != nil {
		return nil, nil, err
	}

	for key, cached := range m.programCache {
		if cached == program {
			if m.targetPrograms == nil || len(m.targetPrograms) >= 8192 {
				m.targetPrograms = map[string]contextDispatch{}
			}
			m.targetPrograms[target.key] = contextDispatch{key, append([]string(nil), effects.Uncertainty...)}
			break
		}
	}
	return m.contextView(target, program, effects.Uncertainty)
}

func (m *NeutralModel) contextView(target *Context, program *formula.ParametricProgram, uncertainty []string) (*Handle, []string, error) {
	start := time.Now()
	panel, err := m.panel.ParametricView(program.WithSpecializationCache(m.specializations), uncertainty)
	m.stats.ViewSeconds += time.Since(start).Seconds()
	if err != nil {
		return nil, nil, err
	}
	compiled := &compiledContext{origin: target, graphSHA: m.graphSHA, coordinates: panel.Coordinates(), panel: panel, hits: m.hits}
	handle := &Handle{context: target, compiled: compiled, decision: Decision{Route: NeutralEffects, Reason: "bound_neutral_event_effects", FromContextSHA256: m.origin.key, ToContextSHA256: target.key}}
	return handle, nil, nil
}

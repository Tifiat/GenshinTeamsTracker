package theorysearch

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
	"genshinteamstracker/native/gcsim_optimizer/internal/setcontext"
	alloc "genshinteamstracker/native/gcsim_optimizer/internal/theoryalloc"
	"genshinteamstracker/native/gcsim_optimizer/internal/theorypackages"
)

type formulaEntry struct {
	program  *formula.ArtifactProgram
	coords   []string
	at       map[string]int
	baseline []float64
	indices  [4][10]int
}
type targetEntry struct {
	family  string
	context string
	codes   []string
}

// FormulaWorld binds only ordinary source-checked neutral views. Unsupported
// source behavior remains unavailable; there is no schedule recapture path.
type FormulaWorld struct {
	req         contracts.OptimizerRequest
	base        *setcontext.Context
	model       *setcontext.NeutralModel
	binding     string
	entries     map[string]*formulaEntry
	order       []string
	targets     map[string]targetEntry
	targetOrder []string
	closed      bool
}

func NewFormulaWorld(req contracts.OptimizerRequest, base *setcontext.Context, model *setcontext.NeutralModel, binding string) (*FormulaWorld, error) {
	if base == nil || model == nil || binding == "" {
		return nil, fmt.Errorf("missing Theory neutral universe")
	}
	if err := req.ValidateTheory(); err != nil {
		return nil, err
	}
	raw, err := json.Marshal(req)
	if err != nil {
		return nil, err
	}
	var owned contracts.OptimizerRequest
	if err = json.Unmarshal(raw, &owned); err != nil {
		return nil, err
	}
	return &FormulaWorld{req: owned, base: base, model: model, binding: binding, entries: map[string]*formulaEntry{}, targets: map[string]targetEntry{}}, nil
}
func (w *FormulaWorld) entry(family, context string, codes []string) *Entry {
	e := w.entries[family]
	if e == nil {
		return nil
	}
	return &Entry{Family: family, ContextSHA256: context, Uncertainty: append([]string(nil), codes...), Objective: w.objective(e)}
}
func (w *FormulaWorld) remember(key string, v targetEntry) {
	if _, ok := w.targets[key]; !ok {
		if len(w.targetOrder) >= 4096 {
			delete(w.targets, w.targetOrder[0])
			w.targetOrder = w.targetOrder[1:]
		}
		w.targetOrder = append(w.targetOrder, key)
	}
	v.codes = append([]string(nil), v.codes...)
	w.targets[key] = v
}
func (w *FormulaWorld) Resolve(ctx context.Context, p [4]domain.Package) (*Entry, []string, error) {
	if err := ctx.Err(); err != nil {
		return nil, nil, err
	}
	if w.closed {
		return nil, nil, fmt.Errorf("Theory world closed")
	}
	tuple := theorypackages.Key(p)
	if known, ok := w.targets[tuple]; ok {
		if known.family == "" {
			return nil, append([]string(nil), known.codes...), nil
		}
		if e := w.entry(known.family, known.context, known.codes); e != nil {
			return e, nil, nil
		}
	}
	changes := map[string][]setcontext.Set{}
	for a, wearer := range w.req.Wearers {
		changes[wearer.WearerKey] = nil
		for _, s := range p[a].Sets {
			changes[wearer.WearerKey] = append(changes[wearer.WearerKey], setcontext.Set{UID: s.SetUID, Count: s.Count})
		}
	}
	target, err := w.base.Replace(changes)
	if err != nil {
		return nil, nil, err
	}
	h, key, codes, err := w.model.TheoryFamily(target)
	if err != nil {
		return nil, nil, err
	}
	if h == nil {
		w.remember(tuple, targetEntry{codes: codes})
		return nil, append([]string(nil), codes...), nil
	}
	panel, err := h.SearchPanel()
	if err != nil {
		return nil, nil, err
	}
	codes = append(append([]string(nil), codes...), panel.OpaqueReasons()...)
	coords := panel.Coordinates()
	// The immutable session binding includes the canonical request/anchor,
	// seeds and allocator domain. Thus equal arithmetic and coordinates also
	// have equal baselines; aliases reuse specialization before rebuilding it.
	frame, err := contracts.CanonicalSHA256(map[string]any{"coordinates": coords, "session_binding": w.binding})
	if err != nil {
		return nil, nil, err
	}
	// Preserve the research policy's arithmetic-key tie order in the warm bank
	// while disambiguating every allocator/input frame.
	family := key + ":" + frame
	if w.entries[family] != nil {
		w.remember(tuple, targetEntry{family: family, context: h.ContextKey(), codes: codes})
		return w.entry(family, h.ContextKey(), codes), nil, nil
	}
	index, err := domain.BuildTheory(w.req, coords)
	if err != nil {
		return nil, nil, err
	}
	baseline, err := index.AssignmentStats(index.Incumbent)
	if err != nil {
		return nil, nil, err
	}
	dense := make([]float64, len(coords))
	at := map[string]int{}
	for i, k := range coords {
		at[k] = i
	}
	var indices [4][10]int
	statKeys := alloc.StatKeys()
	for a, wearer := range w.req.Wearers {
		for k, v := range baseline[a] {
			if i, ok := at[wearer.WearerKey+"."+k]; ok {
				dense[i] -= v
			}
		}
		for j, k := range statKeys {
			indices[a][j] = -1
			if i, ok := at[wearer.WearerKey+"."+k]; ok {
				indices[a][j] = i
			}
		}
	}
	if w.entries[family] == nil {
		delta, err := index.DenseDeltas(index.Incumbent)
		if err != nil {
			return nil, nil, err
		}
		program, err := panel.ArtifactProgramForActors(delta, 0, 1, 2, 3)
		if err != nil {
			return nil, nil, err
		}
		if strings.Join(coords, "\x00") != strings.Join(program.Coordinates(), "\x00") {
			return nil, nil, fmt.Errorf("Theory coordinate ordering changed")
		}
		if len(w.order) >= 768 {
			delete(w.entries, w.order[0])
			w.order = w.order[1:]
		}
		w.entries[family] = &formulaEntry{program: program, coords: coords, at: at, baseline: dense, indices: indices}
		w.order = append(w.order, family)
	}
	w.remember(tuple, targetEntry{family: family, context: h.ContextKey(), codes: codes})
	return w.entry(family, h.ContextKey(), codes), nil, nil
}
func (w *FormulaWorld) objective(e *formulaEntry) alloc.Objective {
	mainValues, statValues := alloc.MainValues(), alloc.StatValues()
	return func(s alloc.State, want bool) (float64, [4][10]float64, error) {
		var g [4][10]float64
		if w.closed {
			return 0, g, fmt.Errorf("Theory world closed")
		}
		dense := append([]float64(nil), e.baseline...)
		rolls := s.Rolls()
		for a, wearer := range w.req.Wearers {
			for _, main := range s.Mains[a] {
				if i, ok := e.at[wearer.WearerKey+"."+main]; ok {
					dense[i] += mainValues[main]
				}
			}
			for j, u := range rolls[a] {
				if i := e.indices[a][j]; i >= 0 {
					dense[i] += u * statValues[j]
				}
			}
		}
		if !want {
			v, err := e.program.Evaluate(dense)
			return v, g, err
		}
		v, gradient, _, err := e.program.ValueGradient(dense)
		if err != nil {
			return v, g, err
		}
		for a := range g {
			for j := range g[a] {
				if i := e.indices[a][j]; i >= 0 {
					g[a][j] = gradient[i] * statValues[j]
				}
			}
		}
		return v, g, nil
	}
}
func (w *FormulaWorld) Fork() (Resolver, error) {
	if w == nil || w.closed {
		return nil, fmt.Errorf("cannot fork closed Theory world")
	}
	n := *w
	n.model = w.model.ForkTheory()
	n.entries = copyMap(w.entries)
	for k, e := range n.entries {
		c := *e
		c.program = e.program.ForkTheory()
		c.coords = append([]string(nil), e.coords...)
		c.baseline = append([]float64(nil), e.baseline...)
		c.at = copyMap(e.at)
		n.entries[k] = &c
	}
	n.order = append([]string(nil), w.order...)
	n.targets = copyMap(w.targets)
	for k, v := range n.targets {
		v.codes = append([]string(nil), v.codes...)
		n.targets[k] = v
	}
	n.targetOrder = append([]string(nil), w.targetOrder...)
	return &n, nil
}
func (w *FormulaWorld) Close() {
	if w == nil || w.closed {
		return
	}
	w.closed = true
	w.entries = nil
	w.targets = nil
	w.order = nil
	w.targetOrder = nil
	w.base = nil
	w.model = nil
	w.req = contracts.OptimizerRequest{}
}

package setcontext

import (
	"fmt"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

// TheoryFamily exposes only an exact bound-program identity after the ordinary
// neutral source checks. It has no capture fallback and no schedule equivalence
// claim. The caller additionally binds input, coordinates and allocator domain.
func (m *NeutralModel) TheoryFamily(target *Context) (*Handle, string, []string, error) {
	h, codes, err := m.Resolve(target)
	if h == nil || err != nil {
		return h, "", codes, err
	}
	if d, ok := m.targetPrograms[target.key]; ok {
		return h, fmt.Sprintf("program:%x", d.key), codes, nil
	}
	return h, "context:" + target.key, codes, nil
}

// ForkTheory is a live in-memory branch, not persistence of borrowed captures.
// Programs share immutable arithmetic but not mutable scratch or cache maps.
func (m *NeutralModel) ForkTheory() *NeutralModel {
	if m == nil {
		return nil
	}
	out := *m
	out.prepared = m.prepared.ForkTheory()
	out.binding = m.binding.ForkTheory()
	out.specializations = m.specializations.ForkTheory()
	out.targetPrograms = make(map[string]contextDispatch, len(m.targetPrograms))
	for k, v := range m.targetPrograms {
		v.uncertainty = append([]string(nil), v.uncertainty...)
		out.targetPrograms[k] = v
	}
	out.programCache = make(map[[32]byte]*formula.ParametricProgram, len(m.programCache))
	for k, v := range m.programCache {
		out.programCache[k] = v.ForkTheory()
	}
	out.programOrder = append([][32]byte(nil), m.programOrder...)
	out.owners = make(map[string]int, len(m.owners))
	for k, v := range m.owners {
		out.owners[k] = v
	}
	out.effectKeys = append([]string(nil), m.effectKeys...)
	out.constantKeys = append([]string(nil), m.constantKeys...)
	out.constantDimensions = append([]int(nil), m.constantDimensions...)
	out.effectDimensions = append([]int(nil), m.effectDimensions...)
	return &out
}

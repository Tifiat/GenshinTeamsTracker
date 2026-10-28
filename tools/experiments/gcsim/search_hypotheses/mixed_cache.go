package setcontext

import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"math"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

// Only sparse expressions need symbolic encoding. The dense part stays numbers;
// all dimensions, even latent or overridden ones, are validated before lookup.
func (m *NeutralModel) bindMixed(values []float64, sparse map[int]*formula.InputExpression) (*formula.ParametricProgram, error) {
	started := time.Now()
	defer func() { m.stats.SymbolicBindSeconds += time.Since(started).Seconds() }()
	if err := m.prepareEffectDimensions(); err != nil { return nil, err }
	if len(values) != len(m.effectKeys) { return nil, fmt.Errorf("mixed capture dimensions differ") }
	for _, value := range values {
		if math.IsNaN(value) || math.IsInf(value, 0) { return nil, fmt.Errorf("nonfinite mixed capture constant") }
	}
	for i, expression := range sparse {
		if i < 0 || i >= len(values) || expression == nil { return nil, fmt.Errorf("invalid mixed capture expression") }
	}
	ordered := make([]float64, len(values))
	expressions := make(map[int]*formula.InputExpression, len(sparse))
	identityExpressions := make(map[string]*formula.InputExpression, len(sparse))
	keys := make([]string, 0, len(sparse))
	data := make([]byte, 8*len(ordered), 8*len(ordered)+32)
	for i, dimension := range m.effectDimensions {
		ordered[i] = values[dimension]
		binary.LittleEndian.PutUint64(data[i*8:], math.Float64bits(ordered[i]))
		if x, ok := sparse[dimension]; ok {
			expressions[i] = x
			identityExpressions[m.effectKeys[i]] = x
			keys = append(keys, m.effectKeys[i])
		}
	}
	digest, cacheable := symbolicEffectKey(keys, identityExpressions)
	data = append(data, digest[:]...)
	key := taggedProgramCacheKey("mixed-sparse-v1", sha256.Sum256(data))
	if cacheable {
		if program := m.programCache[key]; program != nil {
			m.stats.ProgramHits++
			return program, nil
		}
	}
	m.stats.ProgramMisses++
	program, err := m.prepared.BindMixedEffects(ordered, expressions)
	if err == nil && cacheable { m.retainProgram(key, program) }
	return program, err
}

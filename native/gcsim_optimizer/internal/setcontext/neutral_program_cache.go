package setcontext

// Cache already bound effects only when their exact expression identity matches
// this one owned graph. The constant fast path still validates every input before
// projecting damage-live constants; symbolic expressions include every root,
// including latent read roots. Source activation/interaction checks still run
// before lookup; equal point DPS or an equal set label never shares a program.
// The run-local FIFO has both entry and node limits; eviction cannot prune work.
import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"hash"
	"math"
	"sort"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

const neutralProgramEntries = 256
const neutralProgramNodes = 1024000

const neutralExpressionDepthLimit = 4096
const neutralExpressionVisitLimit = 2_000_000
const neutralExpressionByteLimit = 64 << 20

func projectedConstantEffectKey(keys, relevant []string, effects map[string]*formula.InputExpression) ([32]byte, bool) {
	if len(keys) != len(effects) {
		return [32]byte{}, false
	}
	for _, key := range keys {
		x := effects[key]
		if x == nil || x.Operation != "constant" || len(x.Inputs) != 0 || math.IsNaN(x.Value) || math.IsInf(x.Value, 0) {
			return [32]byte{}, false
		}
	}
	data := make([]byte, 8*len(relevant))
	for i, key := range relevant {
		x := effects[key]
		if x == nil {
			return [32]byte{}, false
		}
		binary.LittleEndian.PutUint64(data[8*i:], math.Float64bits(x.Value))
	}
	return sha256.Sum256(data), true
}

func (m *NeutralModel) prepareEffectKeys() {
	if m.effectKeys == nil {
		m.effectKeys = m.prepared.EffectKeys()
		m.constantKeys = m.prepared.ConstantDamageEffectKeys()
		m.stats.EffectInputs, m.stats.ConstantDamageInputs = len(m.effectKeys), len(m.constantKeys)
	}
}

func (m *NeutralModel) bindConstants(values []float64) (*formula.ParametricProgram, error) {
	started := time.Now()
	defer func() { m.stats.ConstantBindSeconds += time.Since(started).Seconds() }()
	m.prepareEffectKeys()
	if len(values) != len(m.effectKeys) {
		return nil, fmt.Errorf("neutral constant vector does not match effect ports")
	}
	if err := m.prepareEffectDimensions(); err != nil {
		return nil, err
	}
	return m.bindConstantDimensions(values)
}

func (m *NeutralModel) prepareEffectDimensions() error {
	m.prepareEffectKeys()
	// Binding order is capture order; formula order is deliberately independent.
	// Derive and validate the complete bijection once, never assume they match.
	if m.effectDimensions == nil {
		keys := m.binding.Keys()
		if len(keys) != len(m.effectKeys) {
			return fmt.Errorf("neutral effect port identity differs from formula")
		}
		byKey := make(map[string]int, len(keys))
		for i, key := range keys {
			if _, duplicate := byKey[key]; duplicate {
				return fmt.Errorf("duplicate neutral effect port")
			}
			byKey[key] = i
		}
		all, live := make([]int, len(m.effectKeys)), make([]int, len(m.constantKeys))
		for i, key := range m.effectKeys {
			index, ok := byKey[key]
			if !ok {
				return fmt.Errorf("missing neutral effect port: %s", key)
			}
			all[i] = index
		}
		for i, key := range m.constantKeys {
			index, ok := byKey[key]
			if !ok {
				return fmt.Errorf("missing damage effect port: %s", key)
			}
			live[i] = index
		}
		m.effectDimensions, m.constantDimensions = all, live
	}
	return nil
}

func (m *NeutralModel) bindConstantDimensions(values []float64) (*formula.ParametricProgram, error) {
	// Validate ALL ports, including latent roots, before damage projection.
	for _, value := range values {
		if math.IsNaN(value) || math.IsInf(value, 0) {
			return nil, fmt.Errorf("nonfinite neutral effect constant")
		}
	}
	data := make([]byte, 8*len(m.constantDimensions))
	for i, dimension := range m.constantDimensions {
		binary.LittleEndian.PutUint64(data[8*i:], math.Float64bits(values[dimension]))
	}
	key := taggedProgramCacheKey("constant", sha256.Sum256(data))
	if program := m.programCache[key]; program != nil {
		m.stats.ProgramHits++
		return program, nil
	}
	m.stats.ProgramMisses++
	ordered := make([]float64, len(m.effectDimensions))
	for i, dimension := range m.effectDimensions {
		ordered[i] = values[dimension]
	}
	program, err := m.prepared.BindConstantEffectsRegions(ordered)
	if err == nil {
		m.retainProgram(key, program)
	}
	return program, err
}

func (m *NeutralModel) bindProgram(effects map[string]*formula.InputExpression) (*formula.ParametricProgram, error) {
	started := time.Now()
	defer func() { m.stats.SymbolicBindSeconds += time.Since(started).Seconds() }()
	m.prepareEffectKeys()
	key, cacheable := projectedConstantEffectKey(m.effectKeys, m.constantKeys, effects)
	tag := "constant"
	if !cacheable {
		key, cacheable = symbolicEffectKey(m.effectKeys, effects)
		tag = "symbolic"
	}
	if cacheable {
		key = taggedProgramCacheKey(tag, key)
		if program := m.programCache[key]; program != nil {
			m.stats.ProgramHits++
			return program, nil
		}
	}
	m.stats.ProgramMisses++
	program, err := m.prepared.BindEffectExpressions(effects)
	if err != nil {
		return nil, err
	}
	if cacheable {
		m.retainProgram(key, program)
	}
	return program, nil
}

func symbolicEffectKey(keys []string, effects map[string]*formula.InputExpression) ([32]byte, bool) {
	if len(keys) != len(effects) {
		return [32]byte{}, false
	}
	ordered := append([]string(nil), keys...)
	sort.Strings(ordered)
	for i, key := range ordered {
		if key == "" || i > 0 && ordered[i-1] == key || effects[key] == nil {
			return [32]byte{}, false
		}
	}

	// One contiguous encoding avoids a hash-interface write (and escaping tiny
	// slice) for every field of every port. The byte stream and digest are exactly
	// the same as incremental hashing; no expression identity is weakened.
	data := make([]byte, 0, min(neutralExpressionByteLimit, len(ordered)*88+64))
	writeBytes := func(value []byte) bool {
		if len(value) > neutralExpressionByteLimit-len(data) {
			return false
		}
		data = append(data, value...)
		return true
	}
	writeUint64 := func(value uint64) bool {
		if len(data) > neutralExpressionByteLimit-8 {
			return false
		}
		data = binary.LittleEndian.AppendUint64(data, value)
		return true
	}
	writeString := func(value string) bool {
		if !writeUint64(uint64(len(value))) || len(value) > neutralExpressionByteLimit-len(data) {
			return false
		}
		data = append(data, value...)
		return true
	}
	if !writeString("neutral-symbolic-program-v1") || !writeUint64(uint64(len(ordered))) {
		return [32]byte{}, false
	}
	active := make(map[*formula.InputExpression]bool)
	seen := make(map[*formula.InputExpression]uint64)
	var nextID uint64
	visits := 0
	var expression func(*formula.InputExpression, int) bool
	expression = func(x *formula.InputExpression, depth int) bool {
		visits++
		if x == nil || depth > neutralExpressionDepthLimit || visits > neutralExpressionVisitLimit {
			return false
		}
		if active[x] {
			return false
		}
		if id, ok := seen[x]; ok {
			return writeBytes([]byte{2}) && writeUint64(id)
		}
		if math.IsNaN(x.Value) || math.IsInf(x.Value, 0) {
			return false
		}
		id := nextID
		nextID++
		seen[x] = id
		active[x] = true
		defer delete(active, x)
		if !writeBytes([]byte{1}) || !writeUint64(id) || !writeString(x.Operation) || !writeString(x.Key) ||
			!writeUint64(math.Float64bits(x.Value)) || !writeUint64(uint64(len(x.Inputs))) {
			return false
		}
		for _, child := range x.Inputs {
			if !expression(child, depth+1) {
				return false
			}
		}
		return true
	}
	for _, key := range ordered {
		if !writeString(key) || !expression(effects[key], 0) {
			return [32]byte{}, false
		}
	}
	return sha256.Sum256(data), true
}

func taggedProgramCacheKey(tag string, digest [32]byte) [32]byte {
	h := sha256.New()
	writeNeutralCacheString(h, "neutral-program-cache-v1")
	writeNeutralCacheString(h, tag)
	_, _ = h.Write(digest[:])
	var key [32]byte
	copy(key[:], h.Sum(nil))
	return key
}

func writeNeutralCacheString(h hash.Hash, value string) {
	writeNeutralCacheUint64(h, uint64(len(value)))
	_, _ = h.Write([]byte(value))
}

func writeNeutralCacheUint64(h hash.Hash, value uint64) {
	var raw [8]byte
	binary.LittleEndian.PutUint64(raw[:], value)
	_, _ = h.Write(raw[:])
}

func (m *NeutralModel) retainProgram(key [32]byte, program *formula.ParametricProgram) {
	if program == nil || program.NodeCount() > neutralProgramNodes {
		return
	}
	if m.programCache == nil {
		m.programCache = map[[32]byte]*formula.ParametricProgram{}
	}
	if m.programCache[key] != nil {
		return
	}
	nodes := program.NodeCount()
	for len(m.programOrder) > 0 && (len(m.programOrder) >= neutralProgramEntries || m.programNodes+nodes > neutralProgramNodes) {
		old := m.programOrder[0]
		m.programOrder = m.programOrder[1:]
		if cached := m.programCache[old]; cached != nil {
			m.programNodes -= cached.NodeCount()
		}
		delete(m.programCache, old)
	}
	if len(m.programOrder) >= neutralProgramEntries || m.programNodes+nodes > neutralProgramNodes {
		return
	}
	m.programOrder = append(m.programOrder, key)
	m.programCache[key] = program
	m.programNodes += nodes
}

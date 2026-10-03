package seteffects

import (
	"crypto/sha256"
	"encoding/binary"
	"math"
)

// Arithmetic payloads are immutable within one binding. A constant component
// is identified by every raw port's exact bits, not by set names or point DPS.
// Symbolic components retain distinct identities: reuse never assumes
// that two expression programs mean the same thing.
func (b *NeutralBinding) identifyComponent(c *neutralComponent) {
	if !c.usable {
		return
	}
	if len(c.expressions) != 0 {
		b.familySerial++
		data := make([]byte, 9)
		data[0] = 'S'
		binary.LittleEndian.PutUint64(data[1:], b.familySerial)
		c.effectIdentity = sha256.Sum256(data)
		return
	}
	data := make([]byte, 1+8*len(c.raw))
	data[0] = 'C'
	for i, value := range c.raw {
		binary.LittleEndian.PutUint64(data[1+8*i:], math.Float64bits(value))
	}
	c.effectIdentity = sha256.Sum256(data)
}

func (b *NeutralBinding) retainComposedPayload(key string, out NeutralExpressions) {
	if !out.Complete() || out.Constants == nil {
		return
	}
	const maxEntries = 128
	const maxValues = 2_000_000
	const maxNodes = 128_000
	cost := len(out.Constants) + len(out.raw)
	nodes, fits := componentExpressionSize(out.SparseEffects, maxNodes)
	if !fits || cost > maxValues {
		return
	}
	if b.composedPayloads == nil {
		b.composedPayloads = map[string]NeutralExpressions{}
	}
	if _, exists := b.composedPayloads[key]; exists {
		return
	}
	for len(b.composedPayloadOrder) >= maxEntries || b.composedPayloadValues+cost > maxValues || b.composedPayloadNodes+nodes > maxNodes {
		old := b.composedPayloadOrder[0]
		b.composedPayloadOrder = b.composedPayloadOrder[1:]
		previous := b.composedPayloads[old]
		b.composedPayloadValues -= len(previous.Constants) + len(previous.raw)
		oldNodes, _ := componentExpressionSize(previous.SparseEffects, maxNodes)
		b.composedPayloadNodes -= oldNodes
		delete(b.composedPayloads, old)
	}
	// Footprints/diagnostics belong to the current actual set choices, not the
	// numeric family, and are rebuilt on every hit. Avoid retaining them here.
	out.footprint = ruleFootprint{}
	out.Uncertainty = nil
	b.composedPayloads[key] = out
	b.composedPayloadOrder = append(b.composedPayloadOrder, key)
	b.composedPayloadValues += cost
	b.composedPayloadNodes += nodes
}

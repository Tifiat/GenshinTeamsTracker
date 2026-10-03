package seteffects

import (
    "crypto/sha256"
    "encoding/binary"
    "math"
)

// Arithmetic payloads are immutable within one binding. A constant component
// is identified by every raw port's exact bits, not by set names or point DPS.
// Symbolic components retain distinct identities: this prototype never assumes
// that two expression programs mean the same thing.
func (b *NeutralBinding) hypothesisIdentify(c *neutralComponent) {
    if !c.usable { return }
    if len(c.expressions) != 0 {
        b.hypothesisFamilySerial++
        data := make([]byte, 9)
        data[0] = 'S'
        binary.LittleEndian.PutUint64(data[1:], b.hypothesisFamilySerial)
        c.hypothesisIdentity = sha256.Sum256(data)
        return
    }
    data := make([]byte, 1+8*len(c.raw))
    data[0] = 'C'
    for i, value := range c.raw { binary.LittleEndian.PutUint64(data[1+8*i:], math.Float64bits(value)) }
    c.hypothesisIdentity = sha256.Sum256(data)
}

func (b *NeutralBinding) hypothesisRetainPayload(key string, out NeutralExpressions) {
    if !out.Complete() || out.Constants == nil { return }
    const maxEntries = 128
    const maxValues = 2_000_000
    const maxNodes = 128_000
    cost := len(out.Constants) + len(out.raw)
    nodes, fits := componentExpressionSize(out.SparseEffects, maxNodes)
    if !fits || cost > maxValues { return }
    if b.hypothesisPayloads == nil { b.hypothesisPayloads = map[string]NeutralExpressions{} }
    if _, exists := b.hypothesisPayloads[key]; exists { return }
    for len(b.hypothesisPayloadOrder) >= maxEntries || b.hypothesisPayloadValues+cost > maxValues || b.hypothesisPayloadNodes+nodes > maxNodes {
        old := b.hypothesisPayloadOrder[0]
        b.hypothesisPayloadOrder = b.hypothesisPayloadOrder[1:]
        previous := b.hypothesisPayloads[old]
        b.hypothesisPayloadValues -= len(previous.Constants) + len(previous.raw)
        oldNodes, _ := componentExpressionSize(previous.SparseEffects, maxNodes)
        b.hypothesisPayloadNodes -= oldNodes
        delete(b.hypothesisPayloads, old)
    }
    // Footprints/diagnostics belong to the current actual set choices, not the
    // numeric family, and are rebuilt on every hit. Avoid retaining them here.
    out.footprint = ruleFootprint{}
    out.Uncertainty = nil
    b.hypothesisPayloads[key] = out
    b.hypothesisPayloadOrder = append(b.hypothesisPayloadOrder, key)
    b.hypothesisPayloadValues += cost
    b.hypothesisPayloadNodes += nodes
}

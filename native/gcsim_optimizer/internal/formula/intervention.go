package formula

import (
	"fmt"
	"math"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

// InterventionProgram is an isolated proposal-guide program, NOT a replacement
// certificate or artifact scorer. Caller supplies engine-attested exact-graph
// input nodes. An offset is added AFTER the node's original computation, so
// existing stat/cross-owner dependencies survive. Production FAST is unchanged.
type InterventionProgram struct {
	member          *CompiledMember
	segments        [][]uint32
	ports           []uint32
	values          []float64
	referenceInputs map[uint32]float64
}

func CompileInterventions(member contracts.IRSeedMember, actors, coordinates []string, inputNodes []uint32) (*InterventionProgram, error) {
	if len(inputNodes) == 0 || len(inputNodes) > 4096 {
		return nil, fmt.Errorf("invalid intervention input count")
	}
	c, e := CompileSeedMember(member, actors, coordinates)
	if e != nil {
		return nil, e
	}
	p := &InterventionProgram{member: c, ports: append([]uint32(nil), inputNodes...), values: make([]float64, len(c.nodes))}
	sort.Slice(p.ports, func(i, j int) bool { return p.ports[i] < p.ports[j] })
	previous := uint32(0)
	for _, node := range p.ports {
		if node <= previous || int(node) >= len(c.nodes) {
			return nil, fmt.Errorf("invalid or duplicated input node")
		}
		segment := make([]uint32, node-previous)
		for i := range segment {
			segment[i] = previous + 1 + uint32(i)
		}
		p.segments = append(p.segments, segment)
		previous = node
	}
	tail := make([]uint32, len(c.nodes)-1-int(previous))
	for i := range tail {
		tail[i] = previous + 1 + uint32(i)
	}
	p.segments = append(p.segments, tail)
	if _, e = p.Evaluate(make([]float64, len(coordinates)), nil); e != nil {
		return nil, e
	}
	p.referenceInputs = map[uint32]float64{}
	for _, id := range p.ports {
		p.referenceInputs[id] = p.values[id]
	}
	return p, nil
}

func (p *InterventionProgram) ReferenceInputs() map[uint32]float64 {
	out := map[uint32]float64{}
	for id, value := range p.referenceInputs {
		out[id] = value
	}
	return out
}

func (p *InterventionProgram) InputNodes() []uint32 { return append([]uint32(nil), p.ports...) }

func (p *InterventionProgram) Evaluate(deltas []float64, offsets map[uint32]float64) (DenseMemberScore, error) {
	if p == nil || len(deltas) != len(p.member.coordinates) {
		return DenseMemberScore{}, fmt.Errorf("invalid intervention program/deltas")
	}
	if len(offsets) > len(p.ports) {
		return DenseMemberScore{}, fmt.Errorf("unknown intervention input")
	}
	for node, value := range offsets {
		i := sort.Search(len(p.ports), func(i int) bool { return p.ports[i] >= node })
		if i == len(p.ports) || p.ports[i] != node || math.IsNaN(value) || math.IsInf(value, 0) {
			return DenseMemberScore{}, fmt.Errorf("invalid intervention offset")
		}
	}
	for i, segment := range p.segments {
		if e := p.member.evaluateNodeSet(deltas, p.values, segment); e != nil {
			return DenseMemberScore{}, e
		}
		if i < len(p.ports) {
			node := p.ports[i]
			p.values[node] += offsets[node]
			if math.IsNaN(p.values[node]) || math.IsInf(p.values[node], 0) {
				return DenseMemberScore{}, fmt.Errorf("nonfinite intervention value")
			}
		}
	}
	out := DenseMemberScore{Damage: p.member.damage(p.values), ByActor: make([]float64, len(p.member.actorKeys))}
	for _, ch := range p.member.channels {
		out.ByActor[ch.actor] += p.values[ch.root]
	}
	return out, nil
}

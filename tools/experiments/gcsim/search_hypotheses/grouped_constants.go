package formula

// Research-only template cache. Equal effect ports are grouped by their FULL
// assignment partition, not assumed equal from one observed DPS. Every call
// rechecks the partition of every constant; changed partitions get another DAG.
// Zero ports fold once; nonzero group values remain small runtime parameters.
import (
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"math"
	"time"
)

type HypothesisTemplateStats struct {
	Requests, Hits, Misses, Evictions, MaxGroups, Nodes, Entries int
	KeySeconds, BuildSeconds float64
}

func (p *ParametricProgram) HypothesisGroupStats() HypothesisTemplateStats {
	out:=p.hypothesisStats
	out.Nodes=p.hypothesisNodes
	out.Entries=len(p.hypothesisTemplates)
	return out
}

func (p *ParametricProgram) BindConstantEffectsHypothesis(values []float64) (*ParametricProgram, error) {
	if p == nil || len(values) != len(p.effects) {
		return nil, fmt.Errorf("constant vector mismatch")
	}
	p.hypothesisStats.Requests++
	started:=time.Now()
	partition := make([]uint32, len(values))
	encoded := make([]byte, 4*len(values))
	byBits := map[uint64]uint32{}
	groupValues := []float64{}
	for i, v := range values {
		if !isFinite(v) {
			return nil, fmt.Errorf("nonfinite constant")
		}
		bits := math.Float64bits(v)
		if bits == 0 {
			partition[i] = 0
		} else if bits == 1<<63 {
			partition[i] = 1
		} else {
			g, ok := byBits[bits]
			if !ok {
				g = uint32(len(groupValues)) + 2
				byBits[bits] = g
				groupValues = append(groupValues, v)
			}
			partition[i] = g
		}
		binary.LittleEndian.PutUint32(encoded[4*i:], partition[i])
	}
	key := sha256.Sum256(encoded)
	p.hypothesisStats.KeySeconds+=time.Since(started).Seconds()
	p.hypothesisStats.MaxGroups=max(p.hypothesisStats.MaxGroups,len(groupValues))
	template := p.hypothesisTemplates[key]
	if template == nil {
		p.hypothesisStats.Misses++
		started=time.Now()
		p.damageNodes()
		coords := p.Coordinates()
		effects := []string{}
		for i := range groupValues {
			name := fmt.Sprintf("effect-group/%d", i)
			coords = append(coords, name)
			effects = append(effects, name)
		}
		b := newProgramBuilder(coords)
		b.program.unresolved = p.program.unresolved
		mapped := make([]uint32, len(p.program.nodes))
		for _, i := range p.damageOrder {
			n := copyNode(p.program.nodes[i])
			for j, in := range n.inputs {
				n.inputs[j] = mapped[in]
			}
			if n.op == opArtifactStat && n.coordinate >= p.artifactCount {
				g := partition[n.coordinate-p.artifactCount]
				if g < 2 {
					value := float64(0)
					if g == 1 {
						value = math.Copysign(0, -1)
					}
					n = compiledNode{op: opConstant, coordinate: -1, value: value}
				} else {
					n.coordinate = p.artifactCount + int(g) - 2
				}
			}
			var err error
			mapped[i], err = b.add(n)
			if err != nil {
				return nil, err
			}
		}
		template = &ParametricProgram{program: b.finish(mapped[p.program.root]), artifactCount: p.artifactCount, actors: append([]string(nil), p.actors...), effects: effects, input: make([]float64, len(coords))}
		template.damageNodes()
		cost := template.NodeCount()
		if cost <= 128000 {
			if p.hypothesisTemplates == nil {
				p.hypothesisTemplates = map[[32]byte]*ParametricProgram{}
			}
			for len(p.hypothesisOrder) > 0 && (len(p.hypothesisOrder) >= 64 || p.hypothesisNodes+cost > 128000) {
				old := p.hypothesisOrder[0]
				p.hypothesisOrder = p.hypothesisOrder[1:]
				p.hypothesisNodes -= p.hypothesisTemplates[old].NodeCount()
				delete(p.hypothesisTemplates, old)
				p.hypothesisStats.Evictions++
			}
			p.hypothesisOrder = append(p.hypothesisOrder, key)
			p.hypothesisTemplates[key] = template
			p.hypothesisNodes += cost
		}
		p.hypothesisStats.BuildSeconds+=time.Since(started).Seconds()
	} else {
		p.hypothesisStats.Hits++
	}
	bound := template.WithOwnScratch()
	bound.fixedEffects = append([]float64{}, groupValues...)
	bound.effects = nil
	return bound, nil
}

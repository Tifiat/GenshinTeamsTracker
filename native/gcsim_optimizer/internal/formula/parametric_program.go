package formula

// Prepared parametric arithmetic for the approved All Sets overhaul (trace
// handoff section 2). Ports are exact-graph scalar DELTA inputs, not an effect
// activation/replacement certificate. An engine-owned effect producer must
// supply new-minus-old expressions with complete ownership/lifecycle coverage.
// Tests pin input identity and changed-input parity; no named-set rules live here.
import (
	"encoding/binary"
	"fmt"
	"math"
	"strings"
)

// EffectPort names an independently variable correction AFTER this exact source
// node. Equal observed values never merge ports; sharing Key explicitly declares
// the same correction. The caller owns engine/source/graph binding, as for
// CompileInterventions. This API does not infer a new set's activation.
type EffectPort struct {
	Member   int
	NodeID   uint32
	Key      string
	Observed float64
}

// ReadRoot retains a bound neutral-stat/support output even when it does not
// feed baseline damage. A newly selected effect can consume it after reduction.
// It is NOT added to the DPS sum. Its identity is producer/graph-owned.
type ReadRoot struct {
	Member   int
	NodeID   uint32
	Key      string
	Observed float64
}

// ParametricProgram is one reduced whole-panel DPS function. Preparation runs
// once; effects and artifacts stay variable during reduction. It owns sequential
// scratch and specializes without revisiting the original members/hits.
type ParametricProgram struct {
	regions         *regionBinder
	regionStats     RegionBindingStats
	program         *ArtifactProgram
	artifactCount   int
	actors          []string
	effects         []string
	input           []float64
	readRoots       map[string]uint32
	specializations *SpecializationCache
	// Stable immutable arithmetic identity across scratch/proof-status views.
	specializationSource *ArtifactProgram
	damageLive           []bool
	damageOrder          []uint32
}

func PrepareParametric(members []*CompiledMember, ports []EffectPort) (*ParametricProgram, error) {
	return PrepareParametricWithReads(members, ports, nil)
}

func PrepareParametricWithReads(members []*CompiledMember, ports []EffectPort, reads []ReadRoot) (*ParametricProgram, error) {
	if len(members) == 0 || members[0] == nil {
		return nil, fmt.Errorf("parametric program needs a bound member panel")
	}
	p := &ParametricProgram{artifactCount: len(members[0].coordinates), actors: append([]string(nil), members[0].actorKeys...), readRoots: map[string]uint32{}}
	readByMember := make([][]ReadRoot, len(members))
	readSeen := map[string]bool{}
	for _, read := range reads {
		if read.Member < 0 || read.Member >= len(members) || members[read.Member] == nil || read.NodeID == 0 || int(read.NodeID) >= len(members[read.Member].nodes) || read.Key == "" || readSeen[read.Key] || !isFinite(read.Observed) {
			return nil, fmt.Errorf("invalid parametric read root")
		}
		readSeen[read.Key] = true
		readByMember[read.Member] = append(readByMember[read.Member], read)
	}
	coordinates := append([]string(nil), members[0].coordinates...)
	byMember := make([]map[uint32]int, len(members))
	effectIndex := map[string]int{}
	for _, port := range ports {
		if port.Member < 0 || port.Member >= len(members) || members[port.Member] == nil || port.Key == "" || port.NodeID == 0 || int(port.NodeID) >= len(members[port.Member].nodes) || !isFinite(port.Observed) {
			return nil, fmt.Errorf("invalid parametric effect port")
		}
		if byMember[port.Member] == nil {
			byMember[port.Member] = map[uint32]int{}
		}
		if _, exists := byMember[port.Member][port.NodeID]; exists {
			return nil, fmt.Errorf("duplicate parametric source node")
		}
		dim, exists := effectIndex[port.Key]
		if !exists {
			dim = len(coordinates)
			effectIndex[port.Key] = dim
			coordinates = append(coordinates, "effect:"+port.Key)
			p.effects = append(p.effects, port.Key)
		}
		byMember[port.Member][port.NodeID] = dim
	}
	b := newProgramBuilder(coordinates)
	roots := make([]uint32, 0, len(members))
	for mi, m := range members {
		if m == nil || !sameStrings(m.actorKeys, p.actors) || !sameStrings(m.coordinates, members[0].coordinates) || m.durationMS <= 0 {
			return nil, fmt.Errorf("incompatible parametric panel members")
		}
		if len(byMember[mi]) > 0 || len(readByMember[mi]) > 0 {
			// Witnesses are checked before folding or hash-consing source nodes.
			values := append([]float64(nil), m.baseline...)
			all := make([]uint32, len(m.nodes)-1)
			for i := range all {
				all[i] = uint32(i + 1)
			}
			if err := m.evaluateNodeSet(make([]float64, p.artifactCount), values, all); err != nil {
				return nil, err
			}
			for _, port := range ports {
				if port.Member == mi && math.Abs(values[port.NodeID]-port.Observed) > 1e-9*math.Max(1, math.Abs(port.Observed)) {
					return nil, fmt.Errorf("effect port does not match its exact source node")
				}
			}
			for _, read := range readByMember[mi] {
				if math.Abs(values[read.NodeID]-read.Observed) > 1e-9*math.Max(1, math.Abs(read.Observed)) {
					return nil, fmt.Errorf("read root does not match its exact source node")
				}
			}
		}
		mapped := make([]uint32, len(m.nodes))
		live := liveMemberNodes(m)
		for _, read := range readByMember[mi] {
			live[read.NodeID] = true
		}
		for i := len(live) - 1; i > 0; i-- {
			if live[i] {
				for _, in := range m.nodes[i].inputs {
					live[in] = true
				}
			}
		}
		for i := 1; i < len(m.nodes); i++ {
			if !live[i] {
				continue
			}
			n := copyNode(m.nodes[i])
			for j, in := range n.inputs {
				n.inputs[j] = mapped[in]
			}
			r, err := b.add(n)
			if err != nil {
				return nil, err
			}
			if dim, ok := byMember[mi][uint32(i)]; ok {
				input, err := b.add(compiledNode{op: opArtifactStat, coordinate: dim})
				if err != nil {
					return nil, err
				}
				r, err = b.add(compiledNode{op: opAdd, coordinate: -1, inputs: []uint32{r, input}})
				if err != nil {
					return nil, err
				}
			}
			mapped[i] = r
		}
		for _, read := range readByMember[mi] {
			p.readRoots[read.Key] = mapped[read.NodeID]
		}
		channels := make([]uint32, len(m.channels))
		for i, ch := range m.channels {
			channels[i] = mapped[ch.root]
		}
		r, err := b.add(compiledNode{op: opAdd, coordinate: -1, inputs: channels})
		if err != nil {
			return nil, err
		}
		scale, err := b.add(compiledNode{op: opConstant, coordinate: -1, value: 1000 / float64(m.durationMS) / float64(len(members))})
		if err != nil {
			return nil, err
		}
		r, err = b.add(compiledNode{op: opMultiply, coordinate: -1, inputs: []uint32{r, scale}})
		if err != nil {
			return nil, err
		}
		roots = append(roots, r)
		b.program.unresolved = b.program.unresolved || m.hasOpaque
	}
	root, err := b.add(compiledNode{op: opAdd, coordinate: -1, inputs: roots})
	if err != nil {
		return nil, err
	}
	retained := make([]uint32, len(reads))
	for i, read := range reads {
		retained[i] = p.readRoots[read.Key]
	}
	p.program, retained = b.finishRetained(root, retained)
	for i, read := range reads {
		p.readRoots[read.Key] = retained[i]
	}
	p.input = make([]float64, len(coordinates))
	return p, nil
}

func (p *ParametricProgram) NodeCount() int       { return p.program.NodeCount() }
func (p *ParametricProgram) EffectKeys() []string { return append([]string(nil), p.effects...) }

// WithoutPruning preserves usable arithmetic/ordering without promoting an
// approximate event window or neutral-read projection to a hard-bound proof.
// The view owns its scratch; the source prepared program remains unchanged.
func (p *ParametricProgram) WithoutPruning() *ParametricProgram {
	view := p.WithOwnScratch()
	view.program.unresolved = true
	return view
}

// Immutable nodes may be shared across exactly equal bound effect vectors;
// each search view keeps independent evaluation scratch and proof status.
func (p *ParametricProgram) WithOwnScratch() *ParametricProgram {
	view := *p
	if view.specializationSource == nil {
		view.specializationSource = p.program
	}
	view.program = copyArtifactScratch(p.program)
	view.input = make([]float64, len(p.input))
	return &view
}
func (p *ParametricProgram) Coordinates() []string {
	return append([]string(nil), p.program.coordinates[:p.artifactCount]...)
}

func (p *ParametricProgram) Evaluate(artifacts, effects []float64) (float64, error) {
	if p == nil || len(artifacts) != p.artifactCount || len(effects) != len(p.effects) {
		return 0, fmt.Errorf("parametric input length mismatch")
	}
	copy(p.input, artifacts)
	copy(p.input[p.artifactCount:], effects)
	return p.program.Evaluate(p.input)
}

// Specialize freezes the other wearers and supplied corrections at this anchor.
// Several actors may remain variable. This does not certify that fixed scalar
// corrections are sufficient for a stat-dependent set effect.
func (p *ParametricProgram) Specialize(anchor, effects []float64, actors ...int) (*ArtifactProgram, error) {
	if p == nil || len(anchor) != p.artifactCount || len(effects) != len(p.effects) {
		return nil, fmt.Errorf("invalid parametric specialization anchor")
	}
	keep := make([]bool, len(p.actors))
	for _, actor := range actors {
		if actor < 0 || actor >= len(keep) || keep[actor] {
			return nil, fmt.Errorf("invalid or duplicate variable actor")
		}
		keep[actor] = true
	}
	dims := map[int]int{}
	coordinates := []string{}
	for i, key := range p.program.coordinates[:p.artifactCount] {
		for actor, yes := range keep {
			if yes && strings.HasPrefix(key, p.actors[actor]+".") {
				dims[i] = len(coordinates)
				coordinates = append(coordinates, key)
				break
			}
		}
	}
	fixed := append(append([]float64(nil), anchor...), effects...)
	for _, x := range fixed {
		if !isFinite(x) {
			return nil, fmt.Errorf("nonfinite parametric anchor")
		}
	}
	key := specializationKey{}
	if p.specializations != nil {
		key = p.specializationKey(fixed, dims)
		if cached := p.specializations.get(key); cached != nil {
			return cached, nil
		}
	}
	b := newProgramBuilder(coordinates)
	b.program.unresolved = p.program.unresolved
	mapped := make([]uint32, len(p.program.nodes))
	for i, source := range p.program.nodes {
		n := copyNode(source)
		for j, in := range n.inputs {
			n.inputs[j] = mapped[in]
		}
		if n.op == opArtifactStat {
			if d, ok := dims[n.coordinate]; ok {
				n.coordinate = d
			} else {
				n = compiledNode{op: opConstant, coordinate: -1, value: fixed[n.coordinate]}
			}
		}
		var err error
		mapped[i], err = b.add(n)
		if err != nil {
			return nil, err
		}
	}
	result := b.finish(mapped[p.program.root])
	if p.specializations != nil {
		p.specializations.put(key, result)
	}
	return result, nil
}

type programBuilder struct {
	program  *ArtifactProgram
	memo     map[smallProgramKey]uint32
	wideMemo map[string]uint32
}

// Most IR nodes have zero, two or four ordered inputs. A comparable key avoids
// allocating an encoded string for every visit during binding/specialization.
// Wide variadic nodes retain the exact byte-key fallback; no reassociation.
type smallProgramKey struct {
	value      uint64
	coordinate int
	inputs     [4]uint32
	op         uint8
	count      uint8
}

func newProgramBuilder(coordinates []string) *programBuilder {
	return &programBuilder{program: &ArtifactProgram{coordinates: append([]string(nil), coordinates...)}, memo: map[smallProgramKey]uint32{}}
}

func (b *programBuilder) add(n compiledNode) (uint32, error) {
	p := b.program
	if n.op != opConstant && n.op != opArtifactStat {
		fixed := true
		for _, in := range n.inputs {
			fixed = fixed && p.nodes[in].op == opConstant
		}
		if n.op == opSelectLT && p.nodes[n.inputs[0]].op == opConstant && p.nodes[n.inputs[1]].op == opConstant {
			if p.values[n.inputs[0]] < p.values[n.inputs[1]] {
				return n.inputs[2], nil
			}
			return n.inputs[3], nil
		}
		if fixed {
			v, err := evaluateConstantNode(&n, p.values)
			if err != nil {
				return 0, err
			}
			n = compiledNode{op: opConstant, value: v, coordinate: -1}
		}
	}
	// Ordered inputs preserve IEEE arithmetic. A zero baseline never eliminates
	// a parameter; equal observed numbers never merge distinct parameter keys.
	id := uint32(len(p.nodes))
	if len(n.inputs) <= 4 {
		key := smallProgramKey{value: math.Float64bits(n.value), coordinate: n.coordinate, op: n.op, count: uint8(len(n.inputs))}
		copy(key.inputs[:], n.inputs)
		if old, ok := b.memo[key]; ok {
			return old, nil
		}
		b.memo[key] = id
	} else {
		key := make([]byte, 17+4*len(n.inputs))
		key[0] = n.op
		binary.LittleEndian.PutUint64(key[1:], math.Float64bits(n.value))
		binary.LittleEndian.PutUint64(key[9:], uint64(n.coordinate))
		for i, in := range n.inputs {
			binary.LittleEndian.PutUint32(key[17+i*4:], in)
		}
		if old, ok := b.wideMemo[string(key)]; ok {
			return old, nil
		}
		if b.wideMemo == nil {
			b.wideMemo = map[string]uint32{}
		}
		b.wideMemo[string(key)] = id
	}
	p.nodes = append(p.nodes, n)
	p.values = append(p.values, n.value)
	return id, nil
}

func (b *programBuilder) finish(root uint32) *ArtifactProgram {
	p, _ := b.finishRetained(root, nil)
	return p
}
func (b *programBuilder) finishRetained(root uint32, retained []uint32) (*ArtifactProgram, []uint32) {
	p := b.program
	live := make([]bool, len(p.nodes))
	live[root] = true
	for _, r := range retained {
		live[r] = true
	}
	inputCount := 0
	for i := len(p.nodes) - 1; i >= 0; i-- {
		if live[i] {
			inputCount += len(p.nodes[i].inputs)
			for _, in := range p.nodes[i].inputs {
				live[in] = true
			}
		}
	}
	mapped := make([]uint32, len(p.nodes))
	nodes := make([]compiledNode, 0, len(p.nodes))
	// One owned backing array instead of a separate allocation for every tiny
	// operand slice. Keep source slices untouched and constrain each view's cap.
	inputs := make([]uint32, inputCount)
	nextInput := 0
	for i, source := range p.nodes {
		if !live[i] {
			continue
		}
		n := source
		n.inputs = nil
		if len(source.inputs) != 0 {
			end := nextInput + len(source.inputs)
			n.inputs = inputs[nextInput:end:end]
			copy(n.inputs, source.inputs)
			nextInput = end
		}
		mapped[i] = uint32(len(nodes))
		for j, in := range n.inputs {
			n.inputs[j] = mapped[in]
		}
		nodes = append(nodes, n)
	}
	p.root, p.nodes = mapped[root], nodes
	p.values = make([]float64, len(nodes))
	p.active = make([]uint32, 0, len(nodes))
	for i, n := range nodes {
		if n.op == opConstant {
			p.values[i] = n.value
		} else {
			p.active = append(p.active, uint32(i))
		}
	}
	remapped := make([]uint32, len(retained))
	for i, r := range retained {
		remapped[i] = mapped[r]
	}
	p.prepareDependencies() // immutable masks are shared by later scratch views
	return p, remapped
}

func liveMemberNodes(m *CompiledMember) []bool {
	live := make([]bool, len(m.nodes))
	for _, ch := range m.channels {
		live[ch.root] = true
	}
	for i := len(live) - 1; i > 0; i-- {
		if live[i] {
			for _, in := range m.nodes[i].inputs {
				live[in] = true
			}
		}
	}
	return live
}

func copyNode(n compiledNode) compiledNode { n.inputs = append([]uint32(nil), n.inputs...); return n }
func isFinite(v float64) bool              { return !math.IsNaN(v) && !math.IsInf(v, 0) }
func sameStrings(a, b []string) bool {
	if len(a) != len(b) {
		return false
	}
	for i := range a {
		if a[i] != b[i] {
			return false
		}
	}
	return true
}

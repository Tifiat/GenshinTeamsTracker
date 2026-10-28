package formula

// Research-only arithmetic diagnostics and an allowlisted reduced-DAG fixture.
// No event log, raw capture, account record, or runtime scratch is exported.
import (
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math"
	"sort"
)

type ResearchNode struct {
	Op         uint8    `json:"op"`
	Value      float64  `json:"value,omitempty"`
	Coordinate int      `json:"coordinate"`
	Inputs     []uint32 `json:"inputs,omitempty"`
}
type ResearchDAG struct {
	SHA256      string         `json:"sha256"`
	Schema      string         `json:"schema"`
	Nodes       []ResearchNode `json:"nodes"`
	Root        uint32         `json:"root"`
	Coordinates []string       `json:"coordinates"`
	Unresolved  bool           `json:"unresolved"`
}

// Export only the root's reachable, already reduced source arithmetic. The
// enclosing immutable receipt owns provenance, reference stats and retention.
func (p *ArtifactProgram) ResearchExport() ResearchDAG {
	live := make([]bool, len(p.nodes))
	live[p.root] = true
	for i := len(p.nodes) - 1; i >= 0; i-- {
		if live[i] {
			for _, j := range p.nodes[i].inputs {
				live[j] = true
			}
		}
	}
	d := ResearchDAG{Schema: "theory_reduced_dag_v1", Coordinates: p.Coordinates(), Unresolved: p.unresolved}
	ids := map[uint32]uint32{}
	for i, n := range p.nodes {
		if !live[i] {
			continue
		}
		row := ResearchNode{Op: n.op, Value: n.value, Coordinate: n.coordinate}
		for _, j := range n.inputs {
			row.Inputs = append(row.Inputs, ids[j])
		}
		ids[uint32(i)] = uint32(len(d.Nodes))
		d.Nodes = append(d.Nodes, row)
	}
	d.Root = ids[p.root]
	d.SHA256 = researchDAGHash(d)
	return d
}

func researchDAGHash(d ResearchDAG) string {
	d.SHA256 = ""
	raw, err := json.Marshal(d)
	if err != nil {
		return ""
	}
	return fmt.Sprintf("%x", sha256.Sum256(raw))
}

func ResearchRestore(d ResearchDAG) (*ArtifactProgram, error) {
	if d.SHA256 == "" || d.SHA256 != researchDAGHash(d) {
		return nil, fmt.Errorf("research DAG checksum")
	}
	if d.Schema != "theory_reduced_dag_v1" || len(d.Nodes) == 0 || len(d.Nodes) > 20000 || int(d.Root) >= len(d.Nodes) || len(d.Coordinates) == 0 || len(d.Coordinates) > boundDimensions {
		return nil, fmt.Errorf("invalid research DAG shape")
	}
	seen := map[string]bool{}
	for _, c := range d.Coordinates {
		if c == "" || seen[c] {
			return nil, fmt.Errorf("invalid coordinate identity")
		}
		seen[c] = true
	}
	// Restored arithmetic is always a model-only fixture. It cannot recover a
	// source-coverage certificate merely from a serialized boolean.
	p := &ArtifactProgram{root: d.Root, coordinates: append([]string(nil), d.Coordinates...), unresolved: true, values: make([]float64, len(d.Nodes))}
	for i, n := range d.Nodes {
		if !isFinite(n.Value) || n.Op < opConstant || n.Op > opSelectLT {
			return nil, fmt.Errorf("invalid research node %d", i)
		}
		for _, j := range n.Inputs {
			if int(j) >= i {
				return nil, fmt.Errorf("research node is not topological")
			}
		}
		switch n.Op {
		case opConstant:
			if len(n.Inputs) != 0 {
				return nil, fmt.Errorf("constant inputs")
			}
		case opArtifactStat:
			if len(n.Inputs) != 0 || n.Coordinate < 0 || n.Coordinate >= len(d.Coordinates) {
				return nil, fmt.Errorf("coordinate inputs")
			}
		case opPower:
			if len(n.Inputs) != 2 {
				return nil, fmt.Errorf("power arity")
			}
		case opSelectLT:
			if len(n.Inputs) != 4 {
				return nil, fmt.Errorf("select arity")
			}
		default:
			if len(n.Inputs) == 0 {
				return nil, fmt.Errorf("empty operation")
			}
		}
		p.nodes = append(p.nodes, compiledNode{op: n.Op, value: n.Value, coordinate: n.Coordinate, inputs: append([]uint32(nil), n.Inputs...)})
	}
	return p, nil
}

type ResearchOperand struct {
	Node      uint32  `json:"node"`
	Op        string  `json:"op"`
	Lower     float64 `json:"lower"`
	Upper     float64 `json:"upper"`
	AtWitness float64 `json:"at_witness"`
}
type ResearchSlackNode struct {
	Node           int               `json:"node"`
	Op             string            `json:"op"`
	Dependencies   []string          `json:"dependencies"`
	Lower          float64           `json:"lower"`
	Upper          float64           `json:"upper"`
	AtWitness      float64           `json:"at_witness"`
	Radius         float64           `json:"affine_radius"`
	WeightedRadius float64           `json:"sensitivity_weighted_radius"`
	Operands       []ResearchOperand `json:"operands"`
}
type ResearchDiagnosis struct {
	ModelUpper        float64             `json:"model_upper"`
	Witness           float64             `json:"witness"`
	RootRadius        float64             `json:"root_affine_radius"`
	RootLinearUpper   float64             `json:"root_linear_upper"`
	SeparateTermUpper float64             `json:"separately_bounded_sum"`
	NodesByOp         map[string]int      `json:"nodes_by_op"`
	AmbiguousBranches map[string]int      `json:"ambiguous_branches"`
	Top               []ResearchSlackNode `json:"dominant_nonlinear_nodes"`
	Pressure          []float64           `json:"coordinate_pressure"`
	Guard             string              `json:"interpretation"`
}

func researchOp(op uint8) string {
	return map[uint8]string{opConstant: "constant", opArtifactStat: "artifact_stat", opAdd: "add", opMultiply: "multiply", opMin: "min", opMax: "max", opPower: "power", opSelectLT: "select_lt"}[op]
}

func (p *ArtifactProgram) ResearchDiagnose(center, ref, point []float64, support func([]float64) (float64, float64)) (ResearchDiagnosis, error) {
	d := ResearchDiagnosis{NodesByOp: map[string]int{}, AmbiguousBranches: map[string]int{}, Pressure: make([]float64, len(center)), Guard: "Weighted radii rank nested uncertainty; they are not additive root-gap attribution or legal upper bounds. The separately bounded sum deliberately loses cross-term correlations."}
	if p == nil || len(center) != len(p.coordinates) || len(ref) != len(center) || len(point) != len(center) || len(center) > boundDimensions || support == nil {
		return d, fmt.Errorf("diagnostic dimension")
	}
	b := artifactBound{d: len(center), cache: map[boundVector][2]float64{}}
	copy(b.mean[:], center)
	b.research = func(w boundVector) (float64, float64) {
		if v, ok := b.cache[w]; ok {
			return v[0], v[1]
		}
		lo, hi := support(w[:b.d])
		shift, mag := 0.0, math.Abs(lo)+math.Abs(hi)
		for j, x := range center {
			shift += w[j] * x
			mag += math.Abs(w[j] * x)
		}
		guard := 2e-12 * (1 + mag)
		lo, hi = down(lo-shift-guard), up(hi-shift+guard)
		b.cache[w] = [2]float64{lo, hi}
		return lo, hi
	}
	forms := make([]affineValue, len(p.nodes))
	b.researchNode = func(i int, n compiledNode, r affineValue, values []affineValue) {
		forms[i] = r
		d.NodesByOp[researchOp(n.op)]++
		if n.op == opMin || n.op == opMax || n.op == opSelectLT {
			uncertain := false
			for j := 1; j < len(n.inputs); j++ {
				if n.op == opSelectLT && j > 1 {
					break
				}
				a, z := values[n.inputs[0]], values[n.inputs[j]]
				lo, hi := b.span(affinePlus(a, affineScale(z, -1)))
				if lo < 0 && hi >= 0 {
					uncertain = true
				}
			}
			if uncertain {
				d.AmbiguousBranches[researchOp(n.op)]++
			}
		}
	}
	u, _ := p.boundUpper(&b, ref)
	if !isFinite(u) {
		return d, fmt.Errorf("nonfinite diagnostic enclosure")
	}
	d.ModelUpper = u
	delta := make([]float64, len(point))
	for i, x := range point {
		delta[i] = x - ref[i]
	}
	v, err := p.Evaluate(delta)
	if err != nil {
		return d, err
	}
	d.Witness = v
	root := forms[p.root]
	d.RootRadius = root.r
	_, h := b.support(root.w)
	d.RootLinearUpper = root.c + h
	deps := make([]map[int]bool, len(p.nodes))
	gain := make([]float64, len(p.nodes))
	gain[p.root] = 1
	for i, n := range p.nodes {
		deps[i] = map[int]bool{}
		if n.op == opArtifactStat {
			deps[i][n.coordinate] = true
		}
		for _, j := range n.inputs {
			for k := range deps[j] {
				deps[i][k] = true
			}
		}
	}
	for i := len(p.nodes) - 1; i >= 0; i-- {
		n := p.nodes[i]
		g := gain[i]
		if g == 0 {
			continue
		}
		switch n.op {
		case opAdd:
			for _, j := range n.inputs {
				gain[j] += g
			}
		case opMultiply:
			for k, j := range n.inputs {
				v := g
				for l, h := range n.inputs {
					if k != l {
						v *= p.values[h]
					}
				}
				gain[j] += v
			}
		case opPower:
			a, z := n.inputs[0], n.inputs[1]
			gain[a] += g * p.values[z] * math.Pow(p.values[a], p.values[z]-1)
		case opMin, opMax:
			best := n.inputs[0]
			for _, j := range n.inputs[1:] {
				if n.op == opMin && p.values[j] < p.values[best] || n.op == opMax && p.values[j] > p.values[best] {
					best = j
				}
			}
			gain[best] += g
		case opSelectLT:
			pick := n.inputs[3]
			if p.values[n.inputs[0]] < p.values[n.inputs[1]] {
				pick = n.inputs[2]
			}
			gain[pick] += g
		}
	}
	for i, n := range p.nodes {
		if n.op != opMultiply && n.op != opPower && n.op != opMin && n.op != opMax && n.op != opSelectLT {
			continue
		}
		r := forms[i]
		weight := math.Abs(gain[i]) * r.r
		if !isFinite(weight) || weight <= 1e-6 {
			continue
		}
		row := ResearchSlackNode{Node: i, Op: researchOp(n.op), Lower: r.lo, Upper: r.hi, AtWitness: p.values[i], Radius: r.r, WeightedRadius: weight}
		for j := range deps[i] {
			row.Dependencies = append(row.Dependencies, p.coordinates[j])
		}
		sort.Strings(row.Dependencies)
		for _, j := range n.inputs {
			a := forms[j]
			row.Operands = append(row.Operands, ResearchOperand{Node: j, Op: researchOp(p.nodes[j].op), Lower: a.lo, Upper: a.hi, AtWitness: p.values[j]})
		}
		d.Top = append(d.Top, row)
	}
	sort.SliceStable(d.Top, func(i, j int) bool { return d.Top[i].WeightedRadius > d.Top[j].WeightedRadius })
	if len(d.Top) > 8 {
		d.Top = d.Top[:8]
	}
	for _, row := range d.Top {
		r := forms[row.Node]
		den := 0.0
		for j := range center {
			lo, hi := support(unitDirection(len(center), j))
			den += math.Abs(r.w[j]) * (hi - lo)
		}
		for j := range center {
			lo, hi := support(unitDirection(len(center), j))
			if den > 0 {
				d.Pressure[j] += row.WeightedRadius * math.Abs(r.w[j]) * (hi - lo) / den
			} else if deps[row.Node][j] {
				d.Pressure[j] += row.WeightedRadius / float64(len(deps[row.Node]))
			}
		}
	}
	// Flatten only additive and constant-scaled edges. Each terminal retains its
	// true nonlinear expression; their independent upper sum is a diagnostic.
	weights := make([]float64, len(p.nodes))
	weights[p.root] = 1
	for i := len(p.nodes) - 1; i >= 0; i-- {
		w := weights[i]
		if w == 0 {
			continue
		}
		n := p.nodes[i]
		if n.op == opAdd {
			for _, j := range n.inputs {
				weights[j] += w
			}
			continue
		}
		if n.op == opMultiply {
			variable := -1
			scale := w
			for _, j := range n.inputs {
				if p.nodes[j].op == opConstant {
					scale *= p.nodes[j].value
				} else if variable < 0 {
					variable = int(j)
				} else {
					variable = -2
					break
				}
			}
			if variable >= 0 {
				weights[variable] += scale
				continue
			}
		}
		if w >= 0 {
			d.SeparateTermUpper += w * forms[i].hi
		} else {
			d.SeparateTermUpper += w * forms[i].lo
		}
	}
	return d, nil
}
func unitDirection(n, i int) []float64 { w := make([]float64, n); w[i] = 1; return w }

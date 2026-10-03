package formula

// Bind effect arithmetic to the already reduced team program. This is package
// specialization, not capture/compilation of the original hit schedule. Raw
// artifact coordinates, cross-owner dependencies and caps remain variables.
import "fmt"

type InputExpression struct {
	Operation string
	Key       string
	Value     float64
	Inputs    []*InputExpression
}

func (p *ParametricProgram) BindEffectExpressions(effects map[string]*InputExpression) (*ParametricProgram, error) {
	if p == nil || len(effects) != len(p.effects) {
		return nil, fmt.Errorf("effect expression keys do not match prepared inputs")
	}
	for _, key := range p.effects {
		if effects[key] == nil {
			return nil, fmt.Errorf("missing effect expression: %s", key)
		}
	}
	if bound, constant, err := p.bindConstantEffects(effects); constant {
		return bound, err
	}
	return p.bindEffectExpressionsGeneral(effects)
}

// General dependency-aware binding remains the oracle and the required route
// for artifact, read-root, inter-effect and conditional expression inputs.
func (p *ParametricProgram) bindEffectExpressionsGeneral(effects map[string]*InputExpression) (*ParametricProgram, error) {
	return p.bindEffectExpressionsInputs(effects, nil, nil)
}

func (p *ParametricProgram) bindEffectExpressionsInputs(effects map[string]*InputExpression, constants []float64, sparse map[int]*InputExpression) (*ParametricProgram, error) {
	effectIndex := map[string]int{}
	if constants != nil {
		for i, key := range p.effects {
			effectIndex[key] = i
		}
	}
	coords := p.Coordinates()
	coordinate := map[string]int{}
	for i, key := range coords {
		coordinate[key] = i
	}
	b := newProgramBuilder(coords)
	b.program.unresolved = p.program.unresolved
	// Original graph IDs are already dense and bounded. Indexed scratch avoids
	// hashing each visited source node; traversal and emitted arithmetic order
	// remain identical (including reverse-gradient accumulation order).
	graphMemo := make([]uint32, len(p.program.nodes))
	graphDone := make([]bool, len(p.program.nodes))
	graphBusy := make([]bool, len(p.program.nodes))
	exprMemo := map[*InputExpression]uint32{}
	exprBusy := map[*InputExpression]bool{}
	effectBusy := map[string]bool{}
	effectMemo := map[string]uint32{}
	var source func(uint32, int) (uint32, error)
	var expression func(*InputExpression, int) (uint32, error)
	var effect func(string, int) (uint32, error)
	visits := 0
	effect = func(key string, depth int) (uint32, error) {
		if id, ok := effectMemo[key]; ok {
			return id, nil
		}
		if effectBusy[key] {
			return 0, fmt.Errorf("cyclic effect input: %s", key)
		}
		x, ok := effects[key]
		if constants != nil {
			dimension, exists := effectIndex[key]
			if !exists {
				return 0, fmt.Errorf("unknown mixed effect input: %s", key)
			}
			x, ok = sparse[dimension]
			if !ok {
				// Keep the original literal-expression traversal budget even
				// though the allocated expression wrapper is now unnecessary.
				visits++
				if depth+1 > 4096 || visits > 2_000_000 {
					return 0, fmt.Errorf("effect expression budget")
				}
				id, err := b.add(compiledNode{op: opConstant, coordinate: -1, value: constants[dimension]})
				if err == nil {
					effectMemo[key] = id
				}
				return id, err
			}
		}
		if !ok {
			return 0, fmt.Errorf("unknown effect input: %s", key)
		}
		effectBusy[key] = true
		defer delete(effectBusy, key)
		id, err := expression(x, depth+1)
		if err == nil {
			effectMemo[key] = id
		}
		return id, err
	}
	expression = func(x *InputExpression, depth int) (uint32, error) {
		visits++
		if x == nil || depth > 4096 || visits > 2_000_000 {
			return 0, fmt.Errorf("effect expression budget")
		}
		if id, ok := exprMemo[x]; ok {
			return id, nil
		}
		if exprBusy[x] {
			return 0, fmt.Errorf("cyclic effect expression")
		}
		exprBusy[x] = true
		defer delete(exprBusy, x)
		n := compiledNode{coordinate: -1}
		switch x.Operation {
		case "constant":
			if !isFinite(x.Value) {
				return 0, fmt.Errorf("nonfinite effect constant")
			}
			n.op, n.value = opConstant, x.Value
		case "artifact":
			index, ok := coordinate[x.Key]
			if !ok {
				return 0, fmt.Errorf("unknown effect artifact coordinate: %s", x.Key)
			}
			n.op, n.coordinate = opArtifactStat, index
		case "read":
			if len(x.Inputs) != 0 {
				return 0, fmt.Errorf("read leaf has children")
			}
			r, ok := p.readRoots[x.Key]
			if !ok {
				return 0, fmt.Errorf("unbound neutral read root: %s", x.Key)
			}
			return source(r, depth+1)
		case "effect":
			if len(x.Inputs) != 0 {
				return 0, fmt.Errorf("effect leaf has children")
			}
			return effect(x.Key, depth+1)
		default:
			arity := 2
			switch x.Operation {
			case "add":
				n.op = opAdd
			case "subtract":
				n.op = opAdd
			case "multiply":
				n.op = opMultiply
			case "divide":
				n.op = opMultiply
			case "min":
				n.op = opMin
			case "max":
				n.op = opMax
			case "select_lt":
				n.op = opSelectLT
				arity = 4
			default:
				return 0, fmt.Errorf("unsupported effect expression: %s", x.Operation)
			}
			if len(x.Inputs) != arity {
				return 0, fmt.Errorf("effect expression arity")
			}
			for _, in := range x.Inputs {
				r, err := expression(in, depth+1)
				if err != nil {
					return 0, err
				}
				n.inputs = append(n.inputs, r)
			}
			if x.Operation == "subtract" || x.Operation == "divide" {
				minus, err := b.add(compiledNode{op: opConstant, coordinate: -1, value: -1})
				if err != nil {
					return 0, err
				}
				op := uint8(opMultiply)
				if x.Operation == "divide" {
					op = opPower
				}
				r, err := b.add(compiledNode{op: op, coordinate: -1, inputs: []uint32{n.inputs[1], minus}})
				if err != nil {
					return 0, err
				}
				n.inputs[1] = r
			}
		}
		if len(n.inputs) == 0 && len(x.Inputs) != 0 {
			return 0, fmt.Errorf("effect leaf has children")
		}
		id, err := b.add(n)
		if err == nil {
			exprMemo[x] = id
		}
		return id, err
	}
	source = func(id uint32, depth int) (uint32, error) {
		visits++
		if depth > 4096 || visits > 2_000_000 || int(id) >= len(p.program.nodes) {
			return 0, fmt.Errorf("prepared expression budget")
		}
		if graphDone[id] {
			return graphMemo[id], nil
		}
		if graphBusy[id] {
			return 0, fmt.Errorf("effect depends on its own read result")
		}
		graphBusy[id] = true
		defer func() { graphBusy[id] = false }()
		n := copyNode(p.program.nodes[id])
		if n.op == opArtifactStat && n.coordinate >= p.artifactCount {
			out, err := effect(p.effects[n.coordinate-p.artifactCount], depth+1)
			if err == nil {
				graphMemo[id] = out
				graphDone[id] = true
			}
			return out, err
		}
		for i, in := range n.inputs {
			out, err := source(in, depth+1)
			if err != nil {
				return 0, err
			}
			n.inputs[i] = out
		}
		out, err := b.add(n)
		if err == nil {
			graphMemo[id] = out
			graphDone[id] = true
		}
		return out, err
	}
	root, err := source(p.program.root, 0)
	if err != nil {
		return nil, err
	}
	program := b.finish(root)
	return &ParametricProgram{program: program, artifactCount: p.artifactCount, actors: append([]string(nil), p.actors...), input: make([]float64, p.artifactCount)}, nil
}

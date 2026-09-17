package formula

import (
	"fmt"
	"math"
	"strconv"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

const (
	opConstant uint8 = iota + 1
	opArtifactStat
	opAdd
	opMultiply
	opMin
	opMax
	opPower
	opSelectLT
)

type compiledNode struct {
	op         uint8
	value      float64
	coordinate int
	inputs     []uint32
}

type compiledChannel struct {
	root  uint32
	actor int
}

// CompiledMember parses and indexes one validated formula once. EvaluateDense
// is the candidate hot path: it performs no string parsing, hashing, schema
// validation, or map lookup for artifact coordinates.
type CompiledMember struct {
	seed        uint64
	durationMS  int64
	nodes       []compiledNode
	activeNodes []uint32
	actorNodes  [][]uint32
	channels    []compiledChannel
	actorKeys   []string
	coordinates []string
	baseline    []float64
	scratch     []float64
}

type DenseMemberScore struct {
	Damage  float64
	ByActor []float64
}

func CompileSeedMember(member contracts.IRSeedMember, actorKeys, coordinates []string) (*CompiledMember, error) {
	if err := contracts.ValidateSeedMember(member); err != nil {
		return nil, err
	}
	actorIndex := make(map[string]int, len(actorKeys))
	for index, key := range actorKeys {
		actorIndex[key] = index
	}
	coordinateIndex := make(map[string]int, len(coordinates))
	for index, key := range coordinates {
		coordinateIndex[key] = index
	}
	compiled := &CompiledMember{
		seed: member.Seed, durationMS: member.DurationMS,
		nodes:       make([]compiledNode, len(member.Nodes)+1),
		channels:    make([]compiledChannel, 0, len(member.Channels)),
		actorKeys:   append([]string(nil), actorKeys...),
		coordinates: append([]string(nil), coordinates...),
		actorNodes:  make([][]uint32, len(actorKeys)),
	}
	for _, node := range member.Nodes {
		row := compiledNode{coordinate: -1}
		switch node.Operation {
		case "constant", "opaque_frozen":
			row.op = opConstant
			parsed, err := strconv.ParseFloat(node.Value, 64)
			if err != nil {
				return nil, fmt.Errorf("node %d decimal: %w", node.NodeID, err)
			}
			row.value = parsed
		case "artifact_stat":
			row.op = opArtifactStat
			index, ok := coordinateIndex[node.Coordinate]
			if !ok {
				return nil, fmt.Errorf("node %d coordinate %q is outside compiled domain", node.NodeID, node.Coordinate)
			}
			row.coordinate = index
		case "add":
			row.op = opAdd
		case "multiply":
			row.op = opMultiply
		case "min":
			row.op = opMin
		case "max":
			row.op = opMax
		case "power":
			row.op = opPower
		case "select_lt":
			row.op = opSelectLT
		default:
			return nil, fmt.Errorf("node %d unsupported operation %q", node.NodeID, node.Operation)
		}
		row.inputs = make([]uint32, len(node.Inputs))
		for index, input := range node.Inputs {
			row.inputs[index] = input.NodeID
		}
		compiled.nodes[node.NodeID] = row
	}
	if err := compiled.buildEvaluationPlan(); err != nil {
		return nil, err
	}
	for _, channel := range member.Channels {
		index, ok := actorIndex[channel.ActorKey]
		if !ok {
			return nil, fmt.Errorf("channel %q actor %q is outside compiled domain", channel.ChannelID, channel.ActorKey)
		}
		compiled.channels = append(compiled.channels, compiledChannel{root: channel.RootNodeID, actor: index})
	}
	return compiled, nil
}

func (compiled *CompiledMember) EvaluateDense(deltas []float64) (DenseMemberScore, error) {
	if compiled == nil {
		return DenseMemberScore{}, fmt.Errorf("compiled member is nil")
	}
	if len(deltas) != len(compiled.coordinates) {
		return DenseMemberScore{}, fmt.Errorf("dense delta length mismatch")
	}
	values := append([]float64(nil), compiled.baseline...)
	return compiled.evaluate(deltas, values, true)
}

// EvaluateDamageDense reuses member-owned scratch. The compiled panel search
// path is deliberately sequential, so this avoids allocating an 80k+ node
// value array for every artifact candidate.
func (compiled *CompiledMember) EvaluateDamageDense(deltas []float64) (float64, error) {
	if compiled == nil {
		return 0, fmt.Errorf("compiled member is nil")
	}
	if len(compiled.scratch) != len(compiled.nodes) {
		compiled.scratch = append([]float64(nil), compiled.baseline...)
	}
	score, err := compiled.evaluate(deltas, compiled.scratch, false)
	return score.Damage, err
}

// EvaluateChannelDamageDense reuses the SAME program for cheap guide features.
// Values retain the input member's channel order; no gameplay or set-effect
// interpretation is introduced here. Like the other scratch path, sequential.
func (compiled *CompiledMember) EvaluateChannelDamageDense(deltas []float64) ([]float64, error) {
	if _, err := compiled.EvaluateDamageDense(deltas); err != nil {
		return nil, err
	}
	out := make([]float64, len(compiled.channels))
	for i, channel := range compiled.channels {
		out[i] = compiled.scratch[channel.root]
	}
	return out, nil
}

// EvaluateDamageDenseForActor recalculates only the formula nodes that depend
// on one wearer's artifact coordinates. Dependencies may cross character and
// channel ownership boundaries; for example, healer stats can flow through a
// team buff into every damage channel. The caller must establish the current
// complete-team anchor with EvaluateDamageDense before using this hot path.
func (compiled *CompiledMember) EvaluateDamageDenseForActor(deltas []float64, actor int) (float64, error) {
	if compiled == nil {
		return 0, fmt.Errorf("compiled member is nil")
	}
	if len(deltas) != len(compiled.coordinates) {
		return 0, fmt.Errorf("dense delta length mismatch")
	}
	if actor < 0 || actor >= len(compiled.actorNodes) {
		return 0, fmt.Errorf("actor index is outside compiled domain")
	}
	if len(compiled.scratch) != len(compiled.nodes) {
		return 0, fmt.Errorf("actor evaluation needs an established anchor")
	}
	if err := compiled.evaluateNodeSet(deltas, compiled.scratch, compiled.actorNodes[actor]); err != nil {
		return 0, err
	}
	return compiled.damage(compiled.scratch), nil
}

func (compiled *CompiledMember) evaluate(deltas, values []float64, withActors bool) (DenseMemberScore, error) {
	if len(deltas) != len(compiled.coordinates) {
		return DenseMemberScore{}, fmt.Errorf("dense delta length mismatch")
	}
	if err := compiled.evaluateNodeSet(deltas, values, compiled.activeNodes); err != nil {
		return DenseMemberScore{}, err
	}
	score := DenseMemberScore{Damage: compiled.damage(values)}
	if withActors {
		score.ByActor = make([]float64, len(compiled.actorKeys))
		for _, channel := range compiled.channels {
			score.ByActor[channel.actor] += values[channel.root]
		}
	}
	return score, nil
}

func (compiled *CompiledMember) evaluateNodeSet(deltas, values []float64, nodes []uint32) error {
	for _, rawNodeID := range nodes {
		nodeID := int(rawNodeID)
		node := compiled.nodes[nodeID]
		var value float64
		switch node.op {
		case opConstant:
			value = node.value
		case opArtifactStat:
			value = deltas[node.coordinate]
		case opAdd:
			for _, input := range node.inputs {
				value += values[input]
			}
		case opMultiply:
			value = 1
			for _, input := range node.inputs {
				value *= values[input]
			}
		case opMin, opMax:
			value = values[node.inputs[0]]
			for _, input := range node.inputs[1:] {
				if node.op == opMin {
					value = math.Min(value, values[input])
				} else {
					value = math.Max(value, values[input])
				}
			}
		case opPower:
			value = math.Pow(values[node.inputs[0]], values[node.inputs[1]])
		case opSelectLT:
			value = values[node.inputs[3]]
			if values[node.inputs[0]] < values[node.inputs[1]] {
				value = values[node.inputs[2]]
			}
		default:
			return fmt.Errorf("compiled node %d has invalid operation", nodeID)
		}
		if math.IsNaN(value) || math.IsInf(value, 0) {
			return fmt.Errorf("compiled node %d produced a non-finite value", nodeID)
		}
		values[nodeID] = value
	}
	return nil
}

func (compiled *CompiledMember) damage(values []float64) float64 {
	var damage float64
	for _, channel := range compiled.channels {
		damage += values[channel.root]
	}
	return damage
}

func (compiled *CompiledMember) buildEvaluationPlan() error {
	actorMask := make([]uint64, len(compiled.nodes))
	coordinateActors := make([]uint64, len(compiled.coordinates))
	for coordinateIndex, coordinate := range compiled.coordinates {
		for actorIndex, actorKey := range compiled.actorKeys {
			if len(coordinate) > len(actorKey) && coordinate[:len(actorKey)] == actorKey && coordinate[len(actorKey)] == '.' {
				coordinateActors[coordinateIndex] = uint64(1) << actorIndex
				break
			}
		}
	}
	compiled.baseline = make([]float64, len(compiled.nodes))
	for nodeID := 1; nodeID < len(compiled.nodes); nodeID++ {
		node := compiled.nodes[nodeID]
		var mask uint64
		if node.op == opArtifactStat {
			mask = coordinateActors[node.coordinate]
			if mask == 0 {
				return fmt.Errorf("artifact node %d has no wearer binding", nodeID)
			}
		}
		for _, input := range node.inputs {
			mask |= actorMask[input]
		}
		actorMask[nodeID] = mask
		if mask != 0 {
			compiled.activeNodes = append(compiled.activeNodes, uint32(nodeID))
			for actorIndex := range compiled.actorNodes {
				if mask&(uint64(1)<<actorIndex) != 0 {
					compiled.actorNodes[actorIndex] = append(compiled.actorNodes[actorIndex], uint32(nodeID))
				}
			}
			continue
		}
		value, err := evaluateConstantNode(node, compiled.baseline)
		if err != nil {
			return fmt.Errorf("constant node %d: %w", nodeID, err)
		}
		compiled.baseline[nodeID] = value
	}
	return nil
}

func evaluateConstantNode(node compiledNode, values []float64) (float64, error) {
	var value float64
	switch node.op {
	case opConstant:
		value = node.value
	case opArtifactStat:
		return 0, fmt.Errorf("artifact stat in constant subgraph")
	case opAdd:
		for _, input := range node.inputs {
			value += values[input]
		}
	case opMultiply:
		value = 1
		for _, input := range node.inputs {
			value *= values[input]
		}
	case opMin, opMax:
		value = values[node.inputs[0]]
		for _, input := range node.inputs[1:] {
			if node.op == opMin {
				value = math.Min(value, values[input])
			} else {
				value = math.Max(value, values[input])
			}
		}
	case opPower:
		value = math.Pow(values[node.inputs[0]], values[node.inputs[1]])
	case opSelectLT:
		value = values[node.inputs[3]]
		if values[node.inputs[0]] < values[node.inputs[1]] {
			value = values[node.inputs[2]]
		}
	default:
		return 0, fmt.Errorf("invalid operation")
	}
	if math.IsNaN(value) || math.IsInf(value, 0) {
		return 0, fmt.Errorf("produced a non-finite value")
	}
	return value, nil
}

func (compiled *CompiledMember) Seed() uint64      { return compiled.seed }
func (compiled *CompiledMember) DurationMS() int64 { return compiled.durationMS }

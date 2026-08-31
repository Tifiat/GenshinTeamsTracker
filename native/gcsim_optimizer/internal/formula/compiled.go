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
	channels    []compiledChannel
	actorKeys   []string
	coordinates []string
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
		default:
			return nil, fmt.Errorf("node %d unsupported operation %q", node.NodeID, node.Operation)
		}
		row.inputs = make([]uint32, len(node.Inputs))
		for index, input := range node.Inputs {
			row.inputs[index] = input.NodeID
		}
		compiled.nodes[node.NodeID] = row
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
	return compiled.evaluate(deltas, make([]float64, len(compiled.nodes)), true)
}

// EvaluateDamageDense reuses member-owned scratch. The compiled panel search
// path is deliberately sequential, so this avoids allocating an 80k+ node
// value array for every artifact candidate.
func (compiled *CompiledMember) EvaluateDamageDense(deltas []float64) (float64, error) {
	if compiled == nil {
		return 0, fmt.Errorf("compiled member is nil")
	}
	if len(compiled.scratch) != len(compiled.nodes) {
		compiled.scratch = make([]float64, len(compiled.nodes))
	}
	score, err := compiled.evaluate(deltas, compiled.scratch, false)
	return score.Damage, err
}

func (compiled *CompiledMember) evaluate(deltas, values []float64, withActors bool) (DenseMemberScore, error) {
	if len(deltas) != len(compiled.coordinates) {
		return DenseMemberScore{}, fmt.Errorf("dense delta length mismatch")
	}
	for nodeID := 1; nodeID < len(compiled.nodes); nodeID++ {
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
		default:
			return DenseMemberScore{}, fmt.Errorf("compiled node %d has invalid operation", nodeID)
		}
		if math.IsNaN(value) || math.IsInf(value, 0) {
			return DenseMemberScore{}, fmt.Errorf("compiled node %d produced a non-finite value", nodeID)
		}
		values[nodeID] = value
	}
	score := DenseMemberScore{}
	if withActors {
		score.ByActor = make([]float64, len(compiled.actorKeys))
	}
	for _, channel := range compiled.channels {
		value := values[channel.root]
		score.Damage += value
		if withActors {
			score.ByActor[channel.actor] += value
		}
	}
	return score, nil
}

func (compiled *CompiledMember) Seed() uint64      { return compiled.seed }
func (compiled *CompiledMember) DurationMS() int64 { return compiled.durationMS }

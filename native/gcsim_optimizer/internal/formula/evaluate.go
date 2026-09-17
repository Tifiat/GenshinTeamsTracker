// Package formula evaluates the engine-neutral compact formula IR. It has no
// GCSIM, artifact-search, UI, or database dependency.
package formula

import (
	"fmt"
	"math"
	"strconv"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

type MemberScore struct {
	Damage  float64
	ByActor map[string]float64
}

// EvaluateSeedMember interprets artifact_stat leaves as deltas from the
// incumbent artifact stat vector used to capture this seed member.
func EvaluateSeedMember(member contracts.IRSeedMember, artifactDeltas map[string]float64) (MemberScore, error) {
	values := make([]float64, len(member.Nodes)+1)
	for _, node := range member.Nodes {
		var value float64
		switch node.Operation {
		case "constant", "opaque_frozen":
			parsed, err := strconv.ParseFloat(node.Value, 64)
			if err != nil {
				return MemberScore{}, fmt.Errorf("node %d decimal: %w", node.NodeID, err)
			}
			value = parsed
		case "artifact_stat":
			value = artifactDeltas[node.Coordinate]
		case "add":
			for _, input := range node.Inputs {
				value += values[input.NodeID]
			}
		case "multiply":
			value = 1
			for _, input := range node.Inputs {
				value *= values[input.NodeID]
			}
		case "min", "max":
			value = values[node.Inputs[0].NodeID]
			for _, input := range node.Inputs[1:] {
				if node.Operation == "min" {
					value = math.Min(value, values[input.NodeID])
				} else {
					value = math.Max(value, values[input.NodeID])
				}
			}
		case "power":
			value = math.Pow(values[node.Inputs[0].NodeID], values[node.Inputs[1].NodeID])
		case "select_lt":
			value = values[node.Inputs[3].NodeID]
			if values[node.Inputs[0].NodeID] < values[node.Inputs[1].NodeID] {
				value = values[node.Inputs[2].NodeID]
			}
		default:
			return MemberScore{}, fmt.Errorf("node %d unsupported operation %q", node.NodeID, node.Operation)
		}
		if math.IsNaN(value) || math.IsInf(value, 0) {
			return MemberScore{}, fmt.Errorf("node %d produced a non-finite value", node.NodeID)
		}
		values[node.NodeID] = value
	}
	score := MemberScore{ByActor: make(map[string]float64)}
	for _, channel := range member.Channels {
		value := values[channel.RootNodeID]
		score.Damage += value
		score.ByActor[channel.ActorKey] += value
	}
	return score, nil
}

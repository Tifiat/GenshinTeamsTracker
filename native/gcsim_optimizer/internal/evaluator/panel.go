// Package evaluator compiles a validated fixed stochastic panel once and owns
// the low-allocation candidate scoring hot path.
package evaluator

import (
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

const baselineTolerance = 1e-6

type Score struct {
	MeanDamage          float64
	MeanDPS             float64
	ByActorDamage       []float64
	ByActorDPS          []float64
	SampleSDDamage      float64
	StandardErrorDamage float64
	SampleSDDPS         float64
	StandardErrorDPS    float64
}

// ResponseLedgerEntry is formula-derived evidence that changing one artifact
// coordinate can affect one or more actors. It does not claim that the
// response is monotonic and therefore is never, by itself, a hard-prune proof.
type ResponseLedgerEntry struct {
	Coordinate     string   `json:"coordinate"`
	ProviderActor  string   `json:"provider_actor"`
	ConsumerActors []string `json:"consumer_actors"`
}

type Panel struct {
	members       []*formula.CompiledMember
	coordinates   []string
	actorKeys     []string
	ledger        []ResponseLedgerEntry
	opaqueReasons []string
	baseline      Score
}

func Compile(request contracts.OptimizerRequest, compact contracts.CompactIR) (*Panel, error) {
	if err := request.Validate(); err != nil {
		return nil, fmt.Errorf("request: %w", err)
	}
	if err := compact.Validate(); err != nil {
		return nil, fmt.Errorf("compact IR: %w", err)
	}
	requestSHA, err := contracts.CanonicalSHA256(request)
	if err != nil {
		return nil, err
	}
	if compact.RequestSHA256 != requestSHA || compact.EngineBindingSHA256 != request.Engine.BindingSHA256 || compact.ContextSHA256 != request.Context.TraceContextSHA256 {
		return nil, fmt.Errorf("compact IR identity mismatch")
	}
	if len(compact.Members) != len(request.Stochastic.Seeds) {
		return nil, fmt.Errorf("compact IR member count mismatch")
	}
	actorKeys := make([]string, len(request.Wearers))
	for index, wearer := range request.Wearers {
		actorKeys[index] = wearer.WearerKey
	}
	coordinateSet := make(map[string]struct{})
	for memberIndex, member := range compact.Members {
		if member.Seed != request.Stochastic.Seeds[memberIndex] {
			return nil, fmt.Errorf("compact IR seed mismatch")
		}
		for _, node := range member.Nodes {
			if node.Operation == "artifact_stat" {
				coordinateSet[node.Coordinate] = struct{}{}
			}
		}
	}
	coordinates := make([]string, 0, len(coordinateSet))
	for coordinate := range coordinateSet {
		coordinates = append(coordinates, coordinate)
	}
	sort.Strings(coordinates)
	consumerSets := make(map[string]map[string]struct{})
	opaqueSet := make(map[string]struct{})
	for _, member := range compact.Members {
		for _, channel := range member.Channels {
			for _, coordinate := range channel.ResponseCoordinates {
				if consumerSets[coordinate] == nil {
					consumerSets[coordinate] = make(map[string]struct{})
				}
				consumerSets[coordinate][channel.ActorKey] = struct{}{}
			}
		}
		for _, boundary := range member.OpaqueBoundaries {
			opaqueSet[boundary.ReasonCode] = struct{}{}
		}
	}
	ledger := make([]ResponseLedgerEntry, 0, len(consumerSets))
	for coordinate, consumers := range consumerSets {
		provider := coordinate
		if index := strings.IndexByte(provider, '.'); index >= 0 {
			provider = provider[:index]
		}
		row := ResponseLedgerEntry{Coordinate: coordinate, ProviderActor: provider}
		for consumer := range consumers {
			row.ConsumerActors = append(row.ConsumerActors, consumer)
		}
		sort.Strings(row.ConsumerActors)
		ledger = append(ledger, row)
	}
	sort.Slice(ledger, func(i, j int) bool { return ledger[i].Coordinate < ledger[j].Coordinate })
	opaqueReasons := make([]string, 0, len(opaqueSet))
	for reason := range opaqueSet {
		opaqueReasons = append(opaqueReasons, reason)
	}
	sort.Strings(opaqueReasons)
	panel := &Panel{coordinates: coordinates, actorKeys: actorKeys, ledger: ledger, opaqueReasons: opaqueReasons}
	for _, member := range compact.Members {
		compiled, err := formula.CompileSeedMember(member, actorKeys, coordinates)
		if err != nil {
			return nil, err
		}
		panel.members = append(panel.members, compiled)
	}
	baseline, err := panel.Evaluate(make([]float64, len(coordinates)))
	if err != nil {
		return nil, err
	}
	for index, member := range compact.Members {
		declared := 0.0
		for _, channel := range member.Channels {
			value, err := strconv.ParseFloat(channel.BaselineDamage, 64)
			if err != nil {
				return nil, err
			}
			declared += value
		}
		memberScore, err := panel.members[index].EvaluateDense(make([]float64, len(coordinates)))
		if err != nil {
			return nil, err
		}
		if math.Abs(memberScore.Damage-declared) > baselineTolerance {
			return nil, fmt.Errorf("seed %d zero-delta baseline mismatch", member.Seed)
		}
	}
	panel.baseline = baseline
	return panel, nil
}

func (panel *Panel) Evaluate(deltas []float64) (Score, error) {
	if panel == nil {
		return Score{}, fmt.Errorf("compiled panel is nil")
	}
	if len(deltas) != len(panel.coordinates) {
		return Score{}, fmt.Errorf("dense delta length mismatch")
	}
	damages := make([]float64, len(panel.members))
	dps := make([]float64, len(panel.members))
	actorDamageValues := make([][]float64, len(panel.actorKeys))
	actorDPSValues := make([][]float64, len(panel.actorKeys))
	for memberIndex, member := range panel.members {
		score, err := member.EvaluateDense(deltas)
		if err != nil {
			return Score{}, fmt.Errorf("seed %d: %w", member.Seed(), err)
		}
		durationSeconds := float64(member.DurationMS()) / 1000
		damages[memberIndex] = score.Damage
		dps[memberIndex] = score.Damage / durationSeconds
		for actorIndex, value := range score.ByActor {
			actorDamageValues[actorIndex] = append(actorDamageValues[actorIndex], value)
			actorDPSValues[actorIndex] = append(actorDPSValues[actorIndex], value/durationSeconds)
		}
	}
	meanDamage := mean(damages)
	meanDPS := mean(dps)
	result := Score{
		MeanDamage: meanDamage, MeanDPS: meanDPS,
		ByActorDamage:  make([]float64, len(panel.actorKeys)),
		ByActorDPS:     make([]float64, len(panel.actorKeys)),
		SampleSDDamage: sampleSD(damages, meanDamage),
		SampleSDDPS:    sampleSD(dps, meanDPS),
	}
	result.StandardErrorDamage = result.SampleSDDamage / math.Sqrt(float64(len(panel.members)))
	result.StandardErrorDPS = result.SampleSDDPS / math.Sqrt(float64(len(panel.members)))
	for index := range actorDamageValues {
		result.ByActorDamage[index] = mean(actorDamageValues[index])
		result.ByActorDPS[index] = mean(actorDPSValues[index])
	}
	return result, nil
}

// EvaluateDPS is the low-allocation sequential ranking path. Actor detail and
// uncertainty coverage are unchanged by ranking and are reconstructed only for
// retained finalists.
func (panel *Panel) EvaluateDPS(deltas []float64) (float64, error) {
	if panel == nil {
		return 0, fmt.Errorf("compiled panel is nil")
	}
	if len(deltas) != len(panel.coordinates) {
		return 0, fmt.Errorf("dense delta length mismatch")
	}
	values := make([]float64, len(panel.members))
	for index, member := range panel.members {
		damage, err := member.EvaluateDamageDense(deltas)
		if err != nil {
			return 0, fmt.Errorf("seed %d: %w", member.Seed(), err)
		}
		values[index] = damage / (float64(member.DurationMS()) / 1000)
	}
	return mean(values), nil
}

func (panel *Panel) Coordinates() []string { return append([]string(nil), panel.coordinates...) }
func (panel *Panel) ActorKeys() []string   { return append([]string(nil), panel.actorKeys...) }
func (panel *Panel) Baseline() Score       { return panel.baseline }
func (panel *Panel) ResponseLedger() []ResponseLedgerEntry {
	output := make([]ResponseLedgerEntry, len(panel.ledger))
	for index, row := range panel.ledger {
		output[index] = row
		output[index].ConsumerActors = append([]string(nil), row.ConsumerActors...)
	}
	return output
}
func (panel *Panel) OpaqueReasons() []string { return append([]string(nil), panel.opaqueReasons...) }

func mean(values []float64) float64 { return compensatedSum(values) / float64(len(values)) }
func compensatedSum(values []float64) float64 {
	var sum, correction float64
	for _, value := range values {
		next := sum + value
		if math.Abs(sum) >= math.Abs(value) {
			correction += (sum - next) + value
		} else {
			correction += (value - next) + sum
		}
		sum = next
	}
	return sum + correction
}
func sampleSD(values []float64, mean float64) float64 {
	if len(values) <= 1 {
		return 0
	}
	terms := make([]float64, len(values))
	for index, value := range values {
		difference := value - mean
		terms[index] = difference * difference
	}
	return math.Sqrt(compensatedSum(terms) / float64(len(values)-1))
}

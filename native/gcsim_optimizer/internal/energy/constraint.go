// Package energy evaluates exact-time energy feasibility from compact engine
// ledgers. It owns no character-specific rules and never estimates particles
// from action names.
package energy

import (
	"fmt"
	"math"
	"math/big"
	"sort"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

const energyRechargeKey = "energy_recharge"

type SourceContribution struct {
	Source       string  `json:"source"`
	ParticleRaw  float64 `json:"particle_raw_at_er_100"`
	FlatObserved float64 `json:"flat_observed"`
}

type WearerAssessment struct {
	WearerKey          string               `json:"wearer_key"`
	ArtifactER         float64              `json:"artifact_er"`
	RequiredArtifactER float64              `json:"required_artifact_er"`
	Margin             float64              `json:"artifact_er_margin"`
	Feasible           bool                 `json:"feasible"`
	MaximumShortage    float64              `json:"maximum_shortage"`
	BurstDeadlines     int                  `json:"burst_deadlines"`
	Sources            []SourceContribution `json:"sources"`
	UncertaintyCodes   []string             `json:"uncertainty_codes"`
}

type Assessment struct {
	Feasible        bool               `json:"feasible"`
	MaximumShortage float64            `json:"maximum_shortage"`
	Wearers         []WearerAssessment `json:"wearers"`
}

type Feasibility struct {
	Feasible        bool    `json:"feasible"`
	MaximumShortage float64 `json:"maximum_shortage"`
}

type Model struct {
	index               *domain.Index
	members             []contracts.IRSeedMember
	requiredArtifactER  [4]float64
	requirementPossible [4]bool
}

func Compile(index *domain.Index, members []contracts.IRSeedMember) (*Model, error) {
	if index == nil || len(members) == 0 {
		return nil, fmt.Errorf("energy model requires artifact domain and seed members")
	}
	for memberIndex, member := range members {
		if member.EnergyLedger == nil {
			return nil, fmt.Errorf("member %d lacks energy ledger", memberIndex)
		}
		if len(member.EnergyLedger.InitialStates) != len(index.Wearers) {
			return nil, fmt.Errorf("member %d energy wearer count mismatch", memberIndex)
		}
		seen := map[string]bool{}
		for _, state := range member.EnergyLedger.InitialStates {
			seen[state.CharacterKey] = true
		}
		for _, wearer := range index.Wearers {
			if !seen[wearer.WearerKey] {
				return nil, fmt.Errorf("member %d lacks energy wearer %s", memberIndex, wearer.WearerKey)
			}
		}
	}
	model := &Model{index: index, members: append([]contracts.IRSeedMember(nil), members...)}
	for actor := range index.Wearers {
		incumbentER, err := index.IncumbentStat(actor, energyRechargeKey)
		if err != nil {
			return nil, err
		}
		model.requiredArtifactER[actor], model.requirementPossible[actor] = model.computeRequiredArtifactER(actor, incumbentER)
	}
	return model, nil
}

func (model *Model) Assess(assignment domain.Assignment) (Assessment, error) {
	out := Assessment{Feasible: true, Wearers: make([]WearerAssessment, len(model.index.Wearers))}
	for actor, wearer := range model.index.Wearers {
		artifactER, err := model.index.AssignmentStat(assignment, actor, energyRechargeKey)
		if err != nil {
			return Assessment{}, err
		}
		incumbentER, err := model.index.IncumbentStat(actor, energyRechargeKey)
		if err != nil {
			return Assessment{}, err
		}
		required, possible := model.requiredArtifactER[actor], model.requirementPossible[actor]
		shortage, deadlines, sources, uncertainty, err := model.evaluateWearer(actor, artifactER, incumbentER)
		if err != nil {
			return Assessment{}, err
		}
		feasible := shortage <= 1e-8
		if !possible {
			feasible = false
			uncertainty = append(uncertainty, "energy_requirement_exceeds_search_bound")
			sort.Strings(uncertainty)
		}
		out.Wearers[actor] = WearerAssessment{
			WearerKey: wearer.WearerKey, ArtifactER: artifactER,
			RequiredArtifactER: required, Margin: artifactER - required,
			Feasible: feasible, MaximumShortage: shortage, BurstDeadlines: deadlines,
			Sources: sources, UncertaintyCodes: uncertainty,
		}
		out.Feasible = out.Feasible && feasible
		out.MaximumShortage = math.Max(out.MaximumShortage, shortage)
	}
	return out, nil
}

// Feasibility is the hot-path constraint check. It deliberately does not
// binary-search explanatory minimum ER thresholds; those are computed once
// for the reported winner by Assess.
func (model *Model) Feasibility(assignment domain.Assignment) (Feasibility, error) {
	out := Feasibility{Feasible: true}
	for actor := range model.index.Wearers {
		artifactER, err := model.index.AssignmentStat(assignment, actor, energyRechargeKey)
		if err != nil {
			return Feasibility{}, err
		}
		deficit := math.Max(0, model.requiredArtifactER[actor]-artifactER)
		wearerFeasible := model.requirementPossible[actor] && deficit <= 1e-8
		out.Feasible = out.Feasible && wearerFeasible
		out.MaximumShortage = math.Max(out.MaximumShortage, deficit)
	}
	return out, nil
}

func (model *Model) computeRequiredArtifactER(actor int, incumbentER float64) (float64, bool) {
	const upper = 10.0
	shortage, _, _, _, err := model.evaluateWearer(actor, 0, incumbentER)
	if err == nil && shortage <= 1e-8 {
		return 0, true
	}
	shortage, _, _, _, err = model.evaluateWearer(actor, upper, incumbentER)
	if err != nil || shortage > 1e-8 {
		return upper, false
	}
	low, high := 0.0, upper
	for range 56 {
		mid := (low + high) / 2
		shortage, _, _, _, _ = model.evaluateWearer(actor, mid, incumbentER)
		if shortage <= 1e-8 {
			high = mid
		} else {
			low = mid
		}
	}
	return high, true
}

func (model *Model) evaluateWearer(actor int, artifactER, incumbentArtifactER float64) (float64, int, []SourceContribution, []string, error) {
	maximumShortage := 0.0
	deadlines := 0
	sourceTotals := map[string]SourceContribution{}
	uncertaintySet := map[string]bool{}
	for _, member := range model.members {
		ledger := member.EnergyLedger
		wearerKey := model.index.Wearers[actor].WearerKey
		var state *contracts.IREnergyCharacterState
		for stateIndex := range ledger.InitialStates {
			if ledger.InitialStates[stateIndex].CharacterKey == wearerKey {
				state = &ledger.InitialStates[stateIndex]
				break
			}
		}
		if state == nil {
			return 0, 0, nil, nil, fmt.Errorf("energy state for %s is missing", wearerKey)
		}
		energy, err := decimal(state.Energy)
		if err != nil {
			return 0, 0, nil, nil, err
		}
		maximum, err := decimal(state.EnergyMax)
		if err != nil {
			return 0, 0, nil, nil, err
		}
		for _, code := range ledger.UncertaintyCodes {
			uncertaintySet[code] = true
		}
		for _, event := range ledger.Events {
			if event.CharacterKey != wearerKey {
				continue
			}
			amount, err := decimal(event.Amount)
			if err != nil {
				return 0, 0, nil, nil, err
			}
			source := sourceTotals[event.Source]
			source.Source = event.Source
			switch event.Kind {
			case "particle":
				raw, err := decimal(*event.RawAtER100)
				if err != nil {
					return 0, 0, nil, nil, err
				}
				observedER, err := decimal(*event.ObservedER)
				if err != nil {
					return 0, 0, nil, nil, err
				}
				effectiveER := math.Max(0, observedER+artifactER-incumbentArtifactER)
				energy = math.Min(maximum, energy+raw*effectiveER)
				source.ParticleRaw += raw
			case "flat":
				energy = math.Max(0, math.Min(maximum, energy+amount))
				source.FlatObserved += amount
			case "burst":
				deadlines++
				maximumShortage = math.Max(maximumShortage, amount-energy)
				energy = math.Max(0, energy-amount)
			default:
				return 0, 0, nil, nil, fmt.Errorf("unsupported energy event kind %q", event.Kind)
			}
			sourceTotals[event.Source] = source
		}
	}
	sources := make([]SourceContribution, 0, len(sourceTotals))
	for _, row := range sourceTotals {
		if row.ParticleRaw != 0 || row.FlatObserved != 0 {
			sources = append(sources, row)
		}
	}
	sort.Slice(sources, func(i, j int) bool {
		left := math.Abs(sources[i].ParticleRaw) + math.Abs(sources[i].FlatObserved)
		right := math.Abs(sources[j].ParticleRaw) + math.Abs(sources[j].FlatObserved)
		if left != right {
			return left > right
		}
		return sources[i].Source < sources[j].Source
	})
	uncertainty := make([]string, 0, len(uncertaintySet))
	for code := range uncertaintySet {
		uncertainty = append(uncertainty, code)
	}
	sort.Strings(uncertainty)
	return math.Max(0, maximumShortage), deadlines, sources, uncertainty, nil
}

func decimal(value string) (float64, error) {
	ratio, ok := new(big.Rat).SetString(value)
	if !ok {
		return 0, fmt.Errorf("invalid energy decimal %q", value)
	}
	result, _ := ratio.Float64()
	if math.IsNaN(result) || math.IsInf(result, 0) {
		return 0, fmt.Errorf("non-finite energy decimal")
	}
	return result, nil
}

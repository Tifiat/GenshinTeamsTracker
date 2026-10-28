// Package theory computes bounded equal-investment artifact guidance over the
// same compiled FAST panel used by account search. It never selects owned IDs
// and never claims a globally reachable physical build.
package theory

import (
	"fmt"
	"math"
	"sort"
	"strconv"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
	"genshinteamstracker/native/gcsim_optimizer/internal/evaluator"
)

const epsilon = 1e-12

var slots = [5]string{"flower", "plume", "sands", "goblet", "circlet"}

var legalMainStats = map[string][]string{
	"flower":  {"hp"},
	"plume":   {"atk"},
	"sands":   {"atk_percent", "def_percent", "em", "energy_recharge", "hp_percent"},
	"goblet":  {"anemo_damage_bonus", "atk_percent", "cryo_damage_bonus", "def_percent", "dendro_damage_bonus", "electro_damage_bonus", "em", "geo_damage_bonus", "hp_percent", "hydro_damage_bonus", "physical_damage_bonus", "pyro_damage_bonus"},
	"circlet": {"atk_percent", "crit_damage", "crit_rate", "def_percent", "em", "healing_bonus", "hp_percent"},
}

var mainStatValues = map[string]float64{
	"hp": 4780, "atk": 311, "hp_percent": .466, "atk_percent": .466,
	"def_percent": .583, "em": 186.5, "energy_recharge": .518,
	"crit_rate": .311, "crit_damage": .622, "pyro_damage_bonus": .466,
	"hydro_damage_bonus": .466, "electro_damage_bonus": .466,
	"cryo_damage_bonus": .466, "anemo_damage_bonus": .466,
	"geo_damage_bonus": .466, "dendro_damage_bonus": .466,
	"physical_damage_bonus": .583, "healing_bonus": .359,
}

var substatValues = map[string]float64{
	"hp": 298.75, "atk": 19.45, "def": 23.15, "hp_percent": .0583,
	"atk_percent": .0583, "def_percent": .0729, "em": 23.31,
	"energy_recharge": .0648, "crit_rate": .0389, "crit_damage": .0777,
}

type Config struct {
	RollUnitsPerWearer int `json:"roll_units_per_wearer"`
	MainStatCycles     int `json:"main_stat_cycles"`
	ExchangeIterations int `json:"exchange_iterations"`
}

func DefaultConfig() Config { return Config{45, 2, 16} }

type StatAllocation struct {
	StatKey   string  `json:"stat_key"`
	RollUnits float64 `json:"roll_units"`
	StatValue float64 `json:"stat_value"`
}

type WearerAllocation struct {
	WearerKey        string            `json:"wearer_key"`
	MainStats        map[string]string `json:"main_stats"`
	Substats         []StatAllocation  `json:"substats"`
	SpentRollUnits   float64           `json:"spent_roll_units"`
	UnspentRollUnits float64           `json:"unspent_roll_units"`
}

type Result struct {
	FormulaDPS           float64            `json:"formula_dps"`
	Allocations          []WearerAllocation `json:"allocations"`
	FormulaEvaluations   int                `json:"formula_evaluations"`
	MainLayoutsEvaluated int                `json:"main_layouts_evaluated"`
	StopReason           string             `json:"stop_reason"`
}

type solveState struct {
	dps         float64
	mains       [4][5]string
	rolls       [4]map[string]float64
	spent       [4]float64
	evaluations int
}

func Solve(panel *evaluator.Panel, request contracts.OptimizerRequest, cfg Config) (Result, error) {
	var out Result
	if panel == nil || cfg.RollUnitsPerWearer < 0 || cfg.RollUnitsPerWearer > 45 || cfg.MainStatCycles < 1 || cfg.MainStatCycles > 8 || cfg.ExchangeIterations < 0 || cfg.ExchangeIterations > 256 {
		return out, fmt.Errorf("invalid theory solver input")
	}
	if err := request.ValidateTheory(); err != nil {
		return out, err
	}
	actors := panel.ActorKeys()
	if len(actors) != 4 || len(request.Wearers) != 4 {
		return out, fmt.Errorf("theory requires four canonical wearers")
	}
	for i := range actors {
		if actors[i] != request.Wearers[i].WearerKey {
			return out, fmt.Errorf("theory wearer order mismatch")
		}
	}
	index, err := domain.BuildTheory(request, panel.Coordinates())
	if err != nil {
		return out, err
	}
	stats, err := index.AssignmentStats(index.Incumbent)
	if err != nil {
		return out, err
	}
	incumbent := make([]map[string]float64, 4)
	for i := range stats {
		incumbent[i] = stats[i]
	}
	mains, err := incumbentMains(request)
	if err != nil {
		return out, err
	}
	coordinateSet := map[string]bool{}
	for _, key := range panel.Coordinates() {
		coordinateSet[key] = true
	}
	best, err := solveRolls(panel, actors, incumbent, mains, cfg)
	if err != nil {
		return out, err
	}
	totalEvaluations, layouts := best.evaluations, 1
	for cycle := 0; cycle < cfg.MainStatCycles; cycle++ {
		candidateMains := best.mains
		candidateRolls := cloneRolls(best.rolls)
		for actor := 0; actor < 4; actor++ {
			anchorDPS, screenErr := evaluateTarget(panel, actors, incumbent, candidateMains, candidateRolls)
			if screenErr != nil {
				return out, screenErr
			}
			totalEvaluations++
			bestDPS := anchorDPS
			bestMains := candidateMains
			bestRolls := candidateRolls
			for _, candidate := range actorMainLanes(actors[actor], candidateMains[actor], coordinateSet) {
				if candidate == candidateMains[actor] {
					continue
				}
				trialMains := candidateMains
				trialMains[actor] = candidate
				trialRolls := projectRolls(candidateRolls, trialMains, cfg.RollUnitsPerWearer)
				dps, screenErr := evaluateTargetForActor(panel, actors, incumbent, trialMains, trialRolls, actor)
				if screenErr != nil {
					return out, screenErr
				}
				totalEvaluations++
				layouts++
				if dps > bestDPS+1e-10 || (math.Abs(dps-bestDPS) <= 1e-10 && mainIdentity(trialMains) < mainIdentity(bestMains)) {
					bestDPS, bestMains, bestRolls = dps, trialMains, trialRolls
				}
			}
			candidateMains, candidateRolls = bestMains, bestRolls
		}
		if candidateMains == best.mains {
			break
		}
		trial, solveErr := solveRolls(panel, actors, incumbent, candidateMains, cfg)
		if solveErr != nil {
			return out, solveErr
		}
		totalEvaluations += trial.evaluations
		if !betterState(trial, best) {
			break
		}
		best = trial
	}
	out.FormulaDPS = best.dps
	out.FormulaEvaluations = totalEvaluations
	out.MainLayoutsEvaluated = layouts
	out.StopReason = "coordinate_descent_converged"
	for actor, key := range actors {
		row := WearerAllocation{WearerKey: key, MainStats: map[string]string{}, SpentRollUnits: best.spent[actor], UnspentRollUnits: float64(cfg.RollUnitsPerWearer) - best.spent[actor]}
		for slot, stat := range best.mains[actor] {
			row.MainStats[slots[slot]] = stat
		}
		keys := make([]string, 0, len(best.rolls[actor]))
		for stat := range best.rolls[actor] {
			keys = append(keys, stat)
		}
		sort.Strings(keys)
		for _, stat := range keys {
			units := best.rolls[actor][stat]
			if units > epsilon {
				row.Substats = append(row.Substats, StatAllocation{stat, units, units * substatValues[stat]})
			}
		}
		out.Allocations = append(out.Allocations, row)
	}
	return out, nil
}

func solveRolls(panel *evaluator.Panel, actors []string, incumbent []map[string]float64, mains [4][5]string, cfg Config) (solveState, error) {
	state := solveState{mains: mains}
	for i := range state.rolls {
		state.rolls[i] = map[string]float64{}
	}
	coordinates := panel.Coordinates()
	coordinateIndex := map[string]int{}
	for i, key := range coordinates {
		coordinateIndex[key] = i
	}
	buildDense := func(rolls [4]map[string]float64) []float64 {
		dense := make([]float64, len(coordinates))
		for actor, key := range actors {
			for stat, value := range incumbent[actor] {
				if at, ok := coordinateIndex[key+"."+stat]; ok {
					dense[at] -= value
				}
			}
			for _, stat := range mains[actor] {
				if at, ok := coordinateIndex[key+"."+stat]; ok {
					dense[at] += mainStatValues[stat]
				}
			}
			for stat, units := range rolls[actor] {
				if at, ok := coordinateIndex[key+"."+stat]; ok {
					dense[at] += units * substatValues[stat]
				}
			}
		}
		return dense
	}
	evaluate := func(rolls [4]map[string]float64) (float64, error) {
		state.evaluations++
		return panel.EvaluateDPS(buildDense(rolls))
	}
	evaluateActor := func(rolls [4]map[string]float64, actor int) (float64, error) {
		state.evaluations++
		return panel.EvaluateDPSForActor(buildDense(rolls), actor)
	}
	var err error
	state.dps, err = evaluate(state.rolls)
	if err != nil {
		return state, err
	}
	type coordinate struct {
		actor int
		stat  string
		cap   float64
	}
	var available []coordinate
	for actor, key := range actors {
		for stat := range substatValues {
			if !coordinateIndexHas(coordinateIndex, key+"."+stat) {
				continue
			}
			eligible := 0
			for _, main := range mains[actor] {
				if main != stat {
					eligible++
				}
			}
			available = append(available, coordinate{actor, stat, float64(eligible * 6)})
		}
	}
	sort.Slice(available, func(i, j int) bool {
		if available[i].actor != available[j].actor {
			return available[i].actor < available[j].actor
		}
		return available[i].stat < available[j].stat
	})
	remaining := 4 * cfg.RollUnitsPerWearer
	for remaining > 0 {
		bestIndex, bestDPS := -1, state.dps
		for actor := 0; actor < 4; actor++ {
			anchorDPS, anchorErr := evaluate(state.rolls)
			if anchorErr != nil {
				return state, anchorErr
			}
			state.dps = anchorDPS
			if bestIndex < 0 {
				bestDPS = state.dps
			}
			for i, c := range available {
				if c.actor != actor || state.spent[c.actor] >= float64(cfg.RollUnitsPerWearer)-epsilon || state.rolls[c.actor][c.stat] >= c.cap-epsilon {
					continue
				}
				trial := cloneRolls(state.rolls)
				trial[c.actor][c.stat]++
				value, evalErr := evaluateActor(trial, c.actor)
				if evalErr != nil {
					return state, evalErr
				}
				if value > bestDPS+1e-10 || (math.Abs(value-bestDPS) <= 1e-10 && bestIndex >= 0 && coordinateLess(c, available[bestIndex])) {
					bestIndex, bestDPS = i, value
				}
			}
		}
		if bestIndex < 0 || bestDPS <= state.dps+1e-10 {
			break
		}
		chosen := available[bestIndex]
		state.rolls[chosen.actor][chosen.stat]++
		state.spent[chosen.actor]++
		state.dps = bestDPS
		remaining--
	}
	for iteration := 0; iteration < cfg.ExchangeIterations; iteration++ {
		bestDPS := state.dps
		bestSource, bestDestination := -1, -1
		for actor := 0; actor < 4; actor++ {
			anchorDPS, anchorErr := evaluate(state.rolls)
			if anchorErr != nil {
				return state, anchorErr
			}
			state.dps = anchorDPS
			if bestSource < 0 {
				bestDPS = state.dps
			}
			for i, source := range available {
				if source.actor != actor || state.rolls[source.actor][source.stat] < .25-epsilon {
					continue
				}
				for j, destination := range available {
					if destination.actor != actor || i == j || state.rolls[destination.actor][destination.stat] > destination.cap-.25+epsilon {
						continue
					}
					trial := cloneRolls(state.rolls)
					trial[source.actor][source.stat] -= .25
					trial[destination.actor][destination.stat] += .25
					value, evalErr := evaluateActor(trial, source.actor)
					if evalErr != nil {
						return state, evalErr
					}
					if value > bestDPS+1e-10 {
						bestDPS, bestSource, bestDestination = value, i, j
					}
				}
			}
		}
		if bestSource < 0 {
			break
		}
		source, destination := available[bestSource], available[bestDestination]
		state.rolls[source.actor][source.stat] -= .25
		state.rolls[destination.actor][destination.stat] += .25
		state.dps = bestDPS
	}
	return state, nil
}

func evaluateTarget(panel *evaluator.Panel, actors []string, incumbent []map[string]float64, mains [4][5]string, rolls [4]map[string]float64) (float64, error) {
	return panel.EvaluateDPS(targetDense(panel, actors, incumbent, mains, rolls))
}

func evaluateTargetForActor(panel *evaluator.Panel, actors []string, incumbent []map[string]float64, mains [4][5]string, rolls [4]map[string]float64, actor int) (float64, error) {
	return panel.EvaluateDPSForActor(targetDense(panel, actors, incumbent, mains, rolls), actor)
}

func targetDense(panel *evaluator.Panel, actors []string, incumbent []map[string]float64, mains [4][5]string, rolls [4]map[string]float64) []float64 {
	coordinates := panel.Coordinates()
	coordinateIndex := make(map[string]int, len(coordinates))
	for i, key := range coordinates {
		coordinateIndex[key] = i
	}
	dense := make([]float64, len(coordinates))
	for actor, key := range actors {
		for stat, value := range incumbent[actor] {
			if at, ok := coordinateIndex[key+"."+stat]; ok {
				dense[at] -= value
			}
		}
		for _, stat := range mains[actor] {
			if at, ok := coordinateIndex[key+"."+stat]; ok {
				dense[at] += mainStatValues[stat]
			}
		}
		for stat, units := range rolls[actor] {
			if at, ok := coordinateIndex[key+"."+stat]; ok {
				dense[at] += units * substatValues[stat]
			}
		}
	}
	return dense
}

func projectRolls(source [4]map[string]float64, mains [4][5]string, wearerBudget int) [4]map[string]float64 {
	out := cloneRolls(source)
	for actor := range out {
		spent := 0.0
		keys := make([]string, 0, len(out[actor]))
		for stat := range out[actor] {
			keys = append(keys, stat)
		}
		sort.Strings(keys)
		for _, stat := range keys {
			eligible := 0
			for _, main := range mains[actor] {
				if main != stat {
					eligible++
				}
			}
			cap := float64(eligible * 6)
			if out[actor][stat] > cap {
				out[actor][stat] = cap
			}
			remaining := float64(wearerBudget) - spent
			if out[actor][stat] > remaining {
				out[actor][stat] = math.Max(0, remaining)
			}
			spent += out[actor][stat]
		}
	}
	return out
}

func incumbentMains(request contracts.OptimizerRequest) ([4][5]string, error) {
	var out [4][5]string
	artifacts := map[int64]contracts.Artifact{}
	for _, artifact := range request.Artifacts {
		artifacts[artifact.ArtifactID] = artifact
	}
	for actor, wearer := range request.Wearers {
		for slot, assignment := range wearer.CurrentArtifacts {
			artifact, ok := artifacts[assignment.ArtifactID]
			if !ok || artifact.Slot != slots[slot] {
				return out, fmt.Errorf("missing incumbent main stat")
			}
			out[actor][slot] = artifact.MainStat.Key
		}
		for slot, stat := range out[actor] {
			if !contains(legalMainStats[slots[slot]], stat) {
				// Older synthetic fixtures can carry a generic damage_bonus key.
				// It is not a legal farmable main stat, so use the canonical first
				// lane as a deterministic starting point; real candidates are still
				// enumerated from the formula-visible legal axes below.
				out[actor][slot] = legalMainStats[slots[slot]][0]
			}
		}
	}
	return out, nil
}

func actorMainLanes(actor string, current [5]string, coordinates map[string]bool) [][5]string {
	choices := [5][]string{{"hp"}, {"atk"}}
	for slot := 2; slot < 5; slot++ {
		for _, stat := range legalMainStats[slots[slot]] {
			if coordinates[actor+"."+stat] || stat == current[slot] {
				choices[slot] = append(choices[slot], stat)
			}
		}
		if len(choices[slot]) == 0 {
			choices[slot] = []string{current[slot]}
		}
	}
	var out [][5]string
	for _, sands := range choices[2] {
		for _, goblet := range choices[3] {
			for _, circlet := range choices[4] {
				out = append(out, [5]string{"hp", "atk", sands, goblet, circlet})
			}
		}
	}
	sort.Slice(out, func(i, j int) bool { return strings.Join(out[i][:], "\x00") < strings.Join(out[j][:], "\x00") })
	return out
}

func cloneRolls(source [4]map[string]float64) [4]map[string]float64 {
	var out [4]map[string]float64
	for actor := range source {
		out[actor] = map[string]float64{}
		for key, value := range source[actor] {
			out[actor][key] = value
		}
	}
	return out
}

func betterState(candidate, current solveState) bool {
	if candidate.dps > current.dps+1e-10 {
		return true
	}
	if math.Abs(candidate.dps-current.dps) > 1e-10 {
		return false
	}
	return mainIdentity(candidate.mains) < mainIdentity(current.mains)
}

func mainIdentity(mains [4][5]string) string {
	parts := make([]string, 0, 20)
	for _, row := range mains {
		parts = append(parts, row[:]...)
	}
	return strings.Join(parts, "\x00")
}

func coordinateLess(a, b struct {
	actor int
	stat  string
	cap   float64
}) bool {
	return a.actor < b.actor || (a.actor == b.actor && a.stat < b.stat)
}
func coordinateIndexHas(values map[string]int, key string) bool { _, ok := values[key]; return ok }
func contains(values []string, target string) bool {
	for _, value := range values {
		if value == target {
			return true
		}
	}
	return false
}

// RulesReceipt returns the immutable game-rule inputs for debug receipts.
func RulesReceipt() map[string]any {
	return map[string]any{"max_roll_units_per_wearer": 45, "max_rolls_per_stat_per_eligible_piece": 6, "main_stat_values": mainStatValues, "substat_max_values": substatValues, "rule_identity": strconv.Itoa(len(mainStatValues)) + "/" + strconv.Itoa(len(substatValues))}
}

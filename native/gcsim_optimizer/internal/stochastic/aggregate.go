// Package stochastic combines compact formula members from the exact fixed
// seed panel declared by an optimizer request. It deliberately owns no search,
// GCSIM, artifact-database, or UI behavior.
package stochastic

import (
	"fmt"
	"math"
	"sort"
	"strconv"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

const baselineTolerance = 1e-6

type ActorMean struct {
	ActorKey string  `json:"actor_key"`
	Damage   float64 `json:"damage"`
	DPS      float64 `json:"dps"`
}

type MemberResult struct {
	Seed    uint64      `json:"seed"`
	Damage  float64     `json:"damage"`
	DPS     float64     `json:"dps"`
	ByActor []ActorMean `json:"by_actor"`
}

type ReasonCoverage struct {
	ReasonCode string   `json:"reason_code"`
	Seeds      []uint64 `json:"seeds"`
}

// FixedPanelResult is an internal mathematical result, not a product result
// and not authority to prune an artifact branch.
type FixedPanelResult struct {
	RequestSHA256     string  `json:"request_sha256"`
	CompactIRSHA256   string  `json:"compact_ir_sha256"`
	Mode              string  `json:"mode"`
	SampleCount       int     `json:"sample_count"`
	DurationMS        int64   `json:"duration_ms,omitempty"`
	MemberDurationsMS []int64 `json:"member_durations_ms"`

	Members []MemberResult `json:"members"`

	BaselineMeanDamage  float64 `json:"baseline_mean_damage"`
	BaselineMeanDPS     float64 `json:"baseline_mean_dps"`
	CandidateMeanDamage float64 `json:"candidate_mean_damage"`
	CandidateMeanDPS    float64 `json:"candidate_mean_dps"`
	DeltaMeanDamage     float64 `json:"delta_mean_damage"`
	DeltaMeanDPS        float64 `json:"delta_mean_dps"`

	SampleStandardDeviationDamage float64 `json:"sample_standard_deviation_damage"`
	StandardErrorDamage           float64 `json:"standard_error_damage"`
	SampleStandardDeviationDPS    float64 `json:"sample_standard_deviation_dps"`
	StandardErrorDPS              float64 `json:"standard_error_dps"`

	CandidateByActor []ActorMean      `json:"candidate_by_actor"`
	OpaqueReasons    []ReasonCoverage `json:"opaque_reasons"`
}

// ValidateZeroDeltaBaseline proves that a captured member's formula reproduces
// the damage declared by its channels before any artifact delta is applied.
func ValidateZeroDeltaBaseline(member contracts.IRSeedMember) error {
	if err := contracts.ValidateSeedMember(member); err != nil {
		return err
	}
	baselineScore, err := formula.EvaluateSeedMember(member, nil)
	if err != nil {
		return err
	}
	declaredBaseline, err := declaredBaselineDamage(member)
	if err != nil {
		return err
	}
	if math.Abs(baselineScore.Damage-declaredBaseline) > baselineTolerance {
		return fmt.Errorf(
			"zero artifact delta produced %.12g damage; declared channel baseline is %.12g",
			baselineScore.Damage, declaredBaseline,
		)
	}
	return nil
}

// AggregateFixedPanel evaluates every requested member once and combines the
// results with equal weight in canonical seed order. Artifact values are signed
// deltas from the incumbent used to capture the compact formula.
func AggregateFixedPanel(
	request contracts.OptimizerRequest,
	compact contracts.CompactIR,
	artifactDeltas map[string]float64,
) (FixedPanelResult, error) {
	if err := request.Validate(); err != nil {
		return FixedPanelResult{}, fmt.Errorf("request: %w", err)
	}
	if err := compact.Validate(); err != nil {
		return FixedPanelResult{}, fmt.Errorf("compact IR: %w", err)
	}
	for coordinate, value := range artifactDeltas {
		if math.IsNaN(value) || math.IsInf(value, 0) {
			return FixedPanelResult{}, fmt.Errorf("artifact delta %q is non-finite", coordinate)
		}
	}

	requestSHA256, err := contracts.CanonicalSHA256(request)
	if err != nil {
		return FixedPanelResult{}, fmt.Errorf("request identity: %w", err)
	}
	compactSHA256, err := contracts.CanonicalSHA256(compact)
	if err != nil {
		return FixedPanelResult{}, fmt.Errorf("compact IR identity: %w", err)
	}
	if compact.RequestSHA256 != requestSHA256 {
		return FixedPanelResult{}, fmt.Errorf("compact IR request identity mismatch")
	}
	if compact.EngineBindingSHA256 != request.Engine.BindingSHA256 {
		return FixedPanelResult{}, fmt.Errorf("compact IR engine binding mismatch")
	}
	if compact.ContextSHA256 != request.Context.TraceContextSHA256 {
		return FixedPanelResult{}, fmt.Errorf("compact IR context mismatch")
	}
	if len(compact.Members) != len(request.Stochastic.Seeds) {
		return FixedPanelResult{}, fmt.Errorf("compact IR member count does not match requested seed panel")
	}

	actorDomain := make(map[string]struct{}, len(request.Wearers))
	actorKeys := make([]string, 0, len(request.Wearers))
	for _, wearer := range request.Wearers {
		actorDomain[wearer.WearerKey] = struct{}{}
		actorKeys = append(actorKeys, wearer.WearerKey)
	}

	durationMS := compact.Members[0].DurationMS
	memberDurationsMS := make([]int64, 0, len(compact.Members))
	baselineDamages := make([]float64, 0, len(compact.Members))
	candidateDamages := make([]float64, 0, len(compact.Members))
	candidateDPS := make([]float64, 0, len(compact.Members))
	memberResults := make([]MemberResult, 0, len(compact.Members))
	actorDamages := make(map[string][]float64, len(actorKeys))
	actorDPSValues := make(map[string][]float64, len(actorKeys))
	reasonSeeds := make(map[string]map[uint64]struct{})

	for index, member := range compact.Members {
		if member.Seed != request.Stochastic.Seeds[index] {
			return FixedPanelResult{}, fmt.Errorf("compact IR seed panel differs from request at index %d", index)
		}
		if member.DurationMS != durationMS {
			durationMS = 0
		}
		memberDurationsMS = append(memberDurationsMS, member.DurationMS)
		for _, channel := range member.Channels {
			if _, ok := actorDomain[channel.ActorKey]; !ok {
				return FixedPanelResult{}, fmt.Errorf("seed %d channel %q has actor outside request domain", member.Seed, channel.ChannelID)
			}
		}

		baselineScore, err := formula.EvaluateSeedMember(member, nil)
		if err != nil {
			return FixedPanelResult{}, fmt.Errorf("seed %d baseline: %w", member.Seed, err)
		}
		declaredBaseline, err := declaredBaselineDamage(member)
		if err != nil {
			return FixedPanelResult{}, fmt.Errorf("seed %d declared baseline: %w", member.Seed, err)
		}
		if math.Abs(baselineScore.Damage-declaredBaseline) > baselineTolerance {
			return FixedPanelResult{}, fmt.Errorf(
				"seed %d zero artifact delta produced %.12g damage; declared channel baseline is %.12g",
				member.Seed, baselineScore.Damage, declaredBaseline,
			)
		}

		candidateScore, err := formula.EvaluateSeedMember(member, artifactDeltas)
		if err != nil {
			return FixedPanelResult{}, fmt.Errorf("seed %d candidate: %w", member.Seed, err)
		}
		durationSeconds := float64(member.DurationMS) / 1000
		memberActorMeans := make([]ActorMean, 0, len(actorKeys))
		for _, actorKey := range actorKeys {
			damage := candidateScore.ByActor[actorKey]
			actorDamages[actorKey] = append(actorDamages[actorKey], damage)
			actorDPSValues[actorKey] = append(actorDPSValues[actorKey], damage/durationSeconds)
			memberActorMeans = append(memberActorMeans, ActorMean{
				ActorKey: actorKey,
				Damage:   damage,
				DPS:      damage / durationSeconds,
			})
		}
		memberResults = append(memberResults, MemberResult{
			Seed:    member.Seed,
			Damage:  candidateScore.Damage,
			DPS:     candidateScore.Damage / durationSeconds,
			ByActor: memberActorMeans,
		})
		baselineDamages = append(baselineDamages, baselineScore.Damage)
		candidateDamages = append(candidateDamages, candidateScore.Damage)
		candidateDPS = append(candidateDPS, candidateScore.Damage/durationSeconds)

		memberReasons := make(map[string]struct{})
		for _, boundary := range member.OpaqueBoundaries {
			memberReasons[boundary.ReasonCode] = struct{}{}
		}
		for reason := range memberReasons {
			if reasonSeeds[reason] == nil {
				reasonSeeds[reason] = make(map[uint64]struct{})
			}
			reasonSeeds[reason][member.Seed] = struct{}{}
		}
	}

	baselineMeanDamage := compensatedMean(baselineDamages)
	candidateMeanDamage := compensatedMean(candidateDamages)
	baselineDPSValues := make([]float64, len(baselineDamages))
	for index, damage := range baselineDamages {
		baselineDPSValues[index] = damage / (float64(memberDurationsMS[index]) / 1000)
	}
	baselineMeanDPS := compensatedMean(baselineDPSValues)
	candidateMeanDPS := compensatedMean(candidateDPS)
	sampleSDDamage := sampleStandardDeviation(candidateDamages, candidateMeanDamage)
	sampleSDDPS := sampleStandardDeviation(candidateDPS, candidateMeanDPS)
	sqrtN := math.Sqrt(float64(len(candidateDamages)))

	candidateByActor := make([]ActorMean, 0, len(actorKeys))
	for _, actorKey := range actorKeys {
		meanDamage := compensatedMean(actorDamages[actorKey])
		candidateByActor = append(candidateByActor, ActorMean{
			ActorKey: actorKey,
			Damage:   meanDamage,
			DPS:      compensatedMean(actorDPSValues[actorKey]),
		})
	}

	reasons := make([]string, 0, len(reasonSeeds))
	for reason := range reasonSeeds {
		reasons = append(reasons, reason)
	}
	sort.Strings(reasons)
	opaqueReasons := make([]ReasonCoverage, 0, len(reasons))
	for _, reason := range reasons {
		seeds := make([]uint64, 0, len(reasonSeeds[reason]))
		for _, seed := range request.Stochastic.Seeds {
			if _, ok := reasonSeeds[reason][seed]; ok {
				seeds = append(seeds, seed)
			}
		}
		opaqueReasons = append(opaqueReasons, ReasonCoverage{ReasonCode: reason, Seeds: seeds})
	}

	return FixedPanelResult{
		RequestSHA256:                 requestSHA256,
		CompactIRSHA256:               compactSHA256,
		Mode:                          request.Stochastic.Mode,
		SampleCount:                   len(candidateDamages),
		DurationMS:                    durationMS,
		MemberDurationsMS:             memberDurationsMS,
		Members:                       memberResults,
		BaselineMeanDamage:            baselineMeanDamage,
		BaselineMeanDPS:               baselineMeanDPS,
		CandidateMeanDamage:           candidateMeanDamage,
		CandidateMeanDPS:              candidateMeanDPS,
		DeltaMeanDamage:               candidateMeanDamage - baselineMeanDamage,
		DeltaMeanDPS:                  candidateMeanDPS - baselineMeanDPS,
		SampleStandardDeviationDamage: sampleSDDamage,
		StandardErrorDamage:           sampleSDDamage / sqrtN,
		SampleStandardDeviationDPS:    sampleSDDPS,
		StandardErrorDPS:              sampleSDDPS / sqrtN,
		CandidateByActor:              candidateByActor,
		OpaqueReasons:                 opaqueReasons,
	}, nil
}

func declaredBaselineDamage(member contracts.IRSeedMember) (float64, error) {
	values := make([]float64, 0, len(member.Channels))
	for _, channel := range member.Channels {
		value, err := strconv.ParseFloat(channel.BaselineDamage, 64)
		if err != nil {
			return 0, fmt.Errorf("channel %q: %w", channel.ChannelID, err)
		}
		values = append(values, value)
	}
	return compensatedSum(values), nil
}

func compensatedMean(values []float64) float64 {
	return compensatedSum(values) / float64(len(values))
}

// Neumaier summation is deterministic for the canonical input order and more
// stable than a naive accumulator when large and small channel totals coexist.
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

func sampleStandardDeviation(values []float64, mean float64) float64 {
	if len(values) <= 1 {
		return 0
	}
	squaredDifferences := make([]float64, len(values))
	for index, value := range values {
		difference := value - mean
		squaredDifferences[index] = difference * difference
	}
	return math.Sqrt(compensatedSum(squaredDifferences) / float64(len(values)-1))
}

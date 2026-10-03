package search

// Research-only observer and switch. Added via a Go overlay, never installed.
// Baseline/gate runs use the same executable and the same ordered score trace.
import (
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"math"
	"os"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/domain"
)

var hypothesisNeighborhoodEnabled = os.Getenv("GTT_NEIGHBORHOOD_GATE") == "1"
var hypothesisScoreTrace = sha256.New()
var hypothesisCounters struct {
	Scored, PointCalls, Plans, Fallbacks, RepresentativeChecks int64
	SingleSkipped, PairSkipped                                 int64
	PrepareNanoseconds                                         int64
}

func hypothesisRecord(anchor domain.Assignment, actor int, ids [5]int64, dps float64) {
	trial := anchor
	trial[actor] = ids
	var data [168]byte
	position := 0
	for _, wearer := range trial {
		for _, id := range wearer {
			binary.LittleEndian.PutUint64(data[position:], uint64(id))
			position += 8
		}
	}
	binary.LittleEndian.PutUint64(data[position:], math.Float64bits(dps))
	_, _ = hypothesisScoreTrace.Write(data[:])
	hypothesisCounters.Scored++
}

func hypothesisPrepareGate(r *candidateRun, base [5]int64, pools [5][]int64) *domain.HypothesisNeighborhoodGatePlan {
	if !hypothesisNeighborhoodEnabled {
		return nil
	}
	started := time.Now()
	defer func() { hypothesisCounters.PrepareNanoseconds += time.Since(started).Nanoseconds() }()
	plan, err := r.localValidator.PrepareHypothesisNeighborhoodGate(base, pools)
	if err != nil {
		hypothesisCounters.Fallbacks++
		return nil // malformed/unknown domains retain the entire original route
	}
	hypothesisCounters.Plans++
	hypothesisCounters.RepresentativeChecks += int64(plan.Checks)
	return plan
}

// Sequential standalone research CLI only; not a shared/parallel product API.
func HypothesisNeighborhoodSnapshot() any {
	return map[string]any{
		"enabled": hypothesisNeighborhoodEnabled, "scored": hypothesisCounters.Scored,
		"point_calls":          hypothesisCounters.PointCalls,
		"ordered_score_sha256": hex.EncodeToString(hypothesisScoreTrace.Sum(nil)),
		"plans":                hypothesisCounters.Plans, "fallbacks": hypothesisCounters.Fallbacks,
		"representative_checks": hypothesisCounters.RepresentativeChecks,
		"single_skipped":        hypothesisCounters.SingleSkipped, "pair_skipped": hypothesisCounters.PairSkipped,
		"prepare_seconds": float64(hypothesisCounters.PrepareNanoseconds) / float64(time.Second),
	}
}

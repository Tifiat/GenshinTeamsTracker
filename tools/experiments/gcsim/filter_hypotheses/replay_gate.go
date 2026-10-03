package seteffects

// Research-only replay gate. Overlay this file into internal/seteffects beside
// the exact rule_replay.go patch described in replay_gate.patch.json. The flag
// is false by default; HypothesisReplayStudy is single-goroutine only. This is
// not a production toggle or a response-acceptance certificate.
import (
	"fmt"
	"reflect"
	"sort"
	"time"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

var hypothesisReplayGateEnabled bool
var hypothesisReplayGateStats *hypothesisReplayGateCounters

type hypothesisReplayGateCounters struct {
	Advances      int
	Queries       int
	SkippedEvents int
	SkippedHitlag int
}

// Every operation omitted by the gate is inert under this condition:
// tasksBefore has no queued work, emit has no subscriptions and no tracked
// energy, and applyHitlag cannot affect a task or hitlag-sensitive modifier.
// Query evaluation is never bypassed, including conditional/static bonuses.
// A query can begin tracking energy or schedule a task; the next advance then
// checks the changed host afresh. Previously skipped events were consumed in
// their original order and must not be replayed after such a change.
func (h *ruleReplayHost) hypothesisCanSkipEventWalk() bool {
	if len(h.subs) != 0 || len(h.tasks) != 0 || len(h.energy) != 0 {
		return false
	}
	for _, m := range h.mods {
		if m.hitlag {
			return false
		}
	}
	return true
}

// HypothesisReplayMismatch names a full RuleReplay inequality. Field is only
// a compact diagnostic; comparison always uses reflect.DeepEqual on the whole
// result, including expression trees, footprint, uncertainty, and VM Steps.
type HypothesisReplayMismatch struct {
	Member   int
	Choice   *RuleChoice // nil is the no-set control
	Symbolic bool
	Field    string
}

type HypothesisReplayStudyResult struct {
	AvailableChoices int
	SelectedChoices  int
	Members          int
	Cases            int
	EqualCases       int
	Queries          int
	BaselineSeconds  float64
	GatedSeconds     float64
	GatedAdvances    int
	GatedQueries     int
	SkippedEvents    int
	SkippedHitlag    int
	Mismatches       []HypothesisReplayMismatch
}

// HypothesisReplayStudy compares the unmodified replay with the research gate
// for numeric and symbolic runs of each prepared member. Up to 60 singleton
// owner/set/tier choices sample the source catalog deterministically; a no-set
// control is additional. The caller must serialize all replays while this
// process-wide research flag is in use. Inputs are borrowed read-only.
func HypothesisReplayStudy(catalog *SourceCatalog, sidecars []contracts.EffectInputsOutput) (HypothesisReplayStudyResult, error) {
	var result HypothesisReplayStudyResult
	if hypothesisReplayGateEnabled || hypothesisReplayGateStats != nil {
		return result, fmt.Errorf("replay gate study already active")
	}
	binding, err := NewNeutralBinding(catalog, sidecars)
	if err != nil {
		return result, err
	}
	defer func() {
		hypothesisReplayGateEnabled = false
		hypothesisReplayGateStats = nil
	}()
	result.Members = len(binding.members)
	// Two modes and one replay per member for each selected choice. Keep the
	// independent replay count bounded even when a capture has many members.
	const maxCases = 240
	if result.Members > maxCases/2 {
		return result, fmt.Errorf("too many neutral members for bounded replay study")
	}
	maxPairs := (maxCases/(result.Members*2) - 1) / 2
	choices, available := hypothesisReplayStudyChoices(catalog, binding.members, maxPairs)
	result.AvailableChoices = available
	result.SelectedChoices = len(choices)
	// The empty choice exercises the important case where the entire tape is
	// inert, including its tail. A singleton can add static or conditional mods.
	cases := make([][]RuleChoice, 0, len(choices)+1)
	cases = append(cases, nil)
	for _, choice := range choices {
		cases = append(cases, []RuleChoice{choice})
	}
	for _, selected := range cases {
		for mi, member := range binding.members {
			queries, order := member.preparedQueries()
			for _, symbolic := range []bool{false, true} {
				result.Cases++
				result.Queries += len(queries)
				hypothesisReplayGateEnabled = false
				hypothesisReplayGateStats = nil
				started := time.Now()
				baseline := catalog.replayNeutralRulesPrepared(member.neutral, selected, queries, symbolic, order)
				result.BaselineSeconds += time.Since(started).Seconds()
				var counts hypothesisReplayGateCounters
				hypothesisReplayGateStats = &counts
				hypothesisReplayGateEnabled = true
				started = time.Now()
				gated := catalog.replayNeutralRulesPrepared(member.neutral, selected, queries, symbolic, order)
				result.GatedSeconds += time.Since(started).Seconds()
				hypothesisReplayGateEnabled = false
				hypothesisReplayGateStats = nil
				result.GatedAdvances += counts.Advances
				result.GatedQueries += counts.Queries
				result.SkippedEvents += counts.SkippedEvents
				result.SkippedHitlag += counts.SkippedHitlag
				if reflect.DeepEqual(baseline, gated) {
					result.EqualCases++
					continue
				}
				var choice *RuleChoice
				if len(selected) != 0 {
					copy := selected[0]
					choice = &copy
				}
				result.Mismatches = append(result.Mismatches, HypothesisReplayMismatch{
					Member: mi, Choice: choice, Symbolic: symbolic,
					Field: hypothesisReplayDifferentField(baseline, gated),
				})
			}
		}
	}
	return result, nil
}

func hypothesisReplayDifferentField(a, b RuleReplay) string {
	switch {
	case !reflect.DeepEqual(a.Values, b.Values):
		return "values_or_expressions"
	case a.Boundary != b.Boundary:
		return "boundary"
	case !reflect.DeepEqual(a.Uncertainty, b.Uncertainty):
		return "uncertainty"
	case !reflect.DeepEqual(a.footprint, b.footprint):
		return "footprint"
	case a.Steps != b.Steps:
		return "vm_steps"
	default:
		return "other"
	}
}

func hypothesisReplayStudyChoices(catalog *SourceCatalog, members []neutralBoundMember, maxPairs int) ([]RuleChoice, int) {
	if len(members) == 0 {
		return nil, 0
	}
	owners := len(members[0].neutral.Context.Characters)
	for _, member := range members[1:] {
		if n := len(member.neutral.Context.Characters); n < owners {
			owners = n
		}
	}
	keys := make([]string, 0, len(catalog.Sets))
	seen := make(map[string]bool, len(catalog.Sets))
	for _, set := range catalog.Sets {
		if set.rule != nil && !seen[set.Key] {
			keys = append(keys, set.Key)
			seen[set.Key] = true
		}
	}
	sort.Strings(keys)
	pairs := owners * len(keys)
	available := pairs * 2
	if pairs == 0 {
		return nil, available
	}
	sample := min(pairs, maxPairs, 30) // both 2p and 4p, at most 60 choices
	if sample <= 0 {
		return nil, available
	}
	choices := make([]RuleChoice, 0, sample*2)
	for i := 0; i < sample; i++ {
		index := i
		if pairs > sample {
			if sample == 1 {
				index = (pairs - 1) / 2
			} else {
				index = i * (pairs - 1) / (sample - 1)
			}
		}
		owner, key := index/len(keys), keys[index%len(keys)]
		choices = append(choices, RuleChoice{Owner: owner, Key: key, Pieces: 2})
		choices = append(choices, RuleChoice{Owner: owner, Key: key, Pieces: 4})
	}
	return choices, available
}

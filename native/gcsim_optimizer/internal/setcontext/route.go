package setcontext

import (
	"fmt"
	"math"
	"reflect"
	"sort"
	"strings"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
)

type Route string

const (
	IdentityReuse     Route = "identity_reuse"
	StaticReplacement Route = "proved_static_replacement"
	FreshCapture      Route = "fresh_context_capture"
)

// Effect is discovery/provenance, never an assertion that an absent set is
// active. Unknown scopes, conditions and dependencies are retained explicitly.
type Effect struct {
	SetUID                string
	Wearer                string
	Tier                  int
	SourceSHA256          string
	Scope                 string // owner, team, target, new_output, unknown
	ModifierKeys          []string
	StaticStats           map[string]float64 // coordinate -> amount, NOT raw item stats
	ConditionDependencies []string
	TimingDependencies    []string
}

// StaticProof is INTERNAL trusted-verifier output, not request/UI data and not
// produced by the old constructor-pattern classifier. No production proof
// producer is enabled in this pilot. Tests exercise this contract using a
// completely known synthetic model; real unknown transitions use fresh capture.
// A later source verifier must establish all four coverage obligations for the
// complete changed lifecycle, including interactions with unchanged effects.
type StaticProof struct {
	FromContextSHA256, ToContextSHA256, GraphSHA256, EvidenceSHA256                          string
	LifecycleComplete, ReadBindingsComplete, ModifierInteractionsComplete, SchedulePreserved bool
	Before, After                                                                            []Effect
	// Bounds cover every formula coordinate. A point witness may only authorize
	// that point, never silently become a proof for arbitrary artifact changes.
	Bounds map[string]Interval
}

type Interval struct{ Min, Max float64 }

type Decision struct {
	Route                                              Route
	Reason                                             string
	FromContextSHA256, ToContextSHA256, EvidenceSHA256 string
	bias                                               map[string]float64
	bounds                                             map[string]Interval
}

// Decide does not inspect topology at all. A complete context identity or a
// separately bound, trusted proof is required. The safe default is fresh.
func Decide(base, target *Context, graphSHA string, coordinates []string, proof *StaticProof) Decision {
	d := Decision{Route: FreshCapture, Reason: "unproved_effect_change"}
	if base == nil || target == nil {
		d.Reason = "missing_context"
		return d
	}
	d.FromContextSHA256, d.ToContextSHA256 = base.key, target.key
	if base.key == target.key {
		d.Route, d.Reason = IdentityReuse, "identical_complete_context"
		return d
	}
	if base.frameKey != target.frameKey {
		d.Reason = "non_set_context_changed"
		return d
	}
	if proof == nil {
		return d
	}
	if !digest.MatchString(graphSHA) || !digest.MatchString(proof.EvidenceSHA256) || proof.FromContextSHA256 != base.key || proof.ToContextSHA256 != target.key || proof.GraphSHA256 != graphSHA {
		d.Reason = "replacement_proof_identity_mismatch"
		return d
	}
	if !proof.LifecycleComplete || !proof.ReadBindingsComplete || !proof.ModifierInteractionsComplete || !proof.SchedulePreserved {
		d.Reason = "replacement_proof_incomplete"
		return d
	}
	allowed := make(map[string]bool, len(coordinates))
	for _, key := range coordinates {
		allowed[key] = true
	}
	if len(proof.Bounds) != len(allowed) {
		d.Reason = "replacement_bounds_incomplete"
		return d
	}
	for key, bound := range proof.Bounds {
		if !allowed[key] || !finite(bound.Min) || !finite(bound.Max) || bound.Min > bound.Max {
			d.Reason = "replacement_bounds_invalid"
			return d
		}
	}
	// Every changed set's active tiers must be accounted for, even when its
	// proved static contribution is zero. Partial constructor evidence cannot
	// omit a removed 4p effect and pretend the 2p delta is the entire change.
	before, after := changedTiers(base, target), changedTiers(target, base)
	oldStats, err := effectStats(proof.Before, before, allowed)
	if err != nil {
		d.Reason = "old_effect_coverage_invalid"
		return d
	}
	newStats, err := effectStats(proof.After, after, allowed)
	if err != nil {
		d.Reason = "new_effect_coverage_invalid"
		return d
	}
	d.bias = make(map[string]float64)
	for key, value := range oldStats {
		d.bias[key] -= value
	}
	for key, value := range newStats {
		d.bias[key] += value
	}
	for key, value := range d.bias {
		if !finite(value) {
			d.Route, d.Reason = FreshCapture, "nonfinite_effect_delta"
			d.bias = nil
			return d
		}
		if value == 0 {
			delete(d.bias, key)
		}
	}
	d.bounds = make(map[string]Interval, len(proof.Bounds))
	for key, bound := range proof.Bounds {
		d.bounds[key] = bound
	}
	d.Route, d.Reason, d.EvidenceSHA256 = StaticReplacement, "complete_scoped_replacement", proof.EvidenceSHA256
	return d
}

func changedTiers(from, to *Context) map[string]bool {
	result := map[string]bool{}
	for _, p := range from.packages {
		other := to.Sets(p.actor)
		if reflect.DeepEqual(p.sets, other) {
			continue
		}
		for _, set := range p.sets {
			// Count, order and parameters remain part of the context identity.
			for _, tier := range []int{2, 4} {
				if set.Count >= tier {
					result[fmt.Sprintf("%s/%s/%d", p.actor, set.UID, tier)] = true
				}
			}
		}
	}
	return result
}

func effectStats(effects []Effect, expected, allowed map[string]bool) (map[string]float64, error) {
	stats, seen, keys := map[string]float64{}, map[string]bool{}, map[string]bool{}
	for _, effect := range effects {
		id := fmt.Sprintf("%s/%s/%d", effect.Wearer, effect.SetUID, effect.Tier)
		if !expected[id] || seen[id] || !digest.MatchString(effect.SourceSHA256) || effect.Scope != "owner" || len(effect.ConditionDependencies) > 0 || len(effect.TimingDependencies) > 0 {
			return nil, fmt.Errorf("unproved effect %s", id)
		}
		seen[id] = true
		for _, key := range effect.ModifierKeys {
			// Conservative pilot: equal keys across even different owners require
			// a richer scoped modifier proof, not implicit independence.
			if key == "" || keys[key] {
				return nil, fmt.Errorf("ambiguous modifier key")
			}
			keys[key] = true
		}
		for key, value := range effect.StaticStats {
			if !allowed[key] || !strings.HasPrefix(key, effect.Wearer+".") || !finite(value) {
				return nil, fmt.Errorf("unrepresented stat %s", key)
			}
			stats[key] += value
			if !finite(stats[key]) {
				return nil, fmt.Errorf("nonfinite stat sum")
			}
		}
	}
	if len(seen) != len(expected) {
		return nil, fmt.Errorf("incomplete active tiers")
	}
	return stats, nil
}

// ComposeDeltas creates a separate evaluation vector. Its input is always the
// candidate's RAW artifact delta from the capture reference, never a previous
// composed vector. The set bias is not written to item stats or final configs.
func (d Decision) ComposeDeltas(raw map[string]float64) (map[string]float64, error) {
	if d.Route != IdentityReuse && d.Route != StaticReplacement {
		return nil, fmt.Errorf("fresh context required: %s", d.Reason)
	}
	if d.Route == StaticReplacement {
		for key, bound := range d.bounds {
			if value := raw[key]; !finite(value) || value < bound.Min || value > bound.Max {
				return nil, fmt.Errorf("raw artifact delta outside replacement proof: %s", key)
			}
		}
	}
	result := make(map[string]float64, len(raw)+len(d.bias))
	for key, value := range raw {
		if !finite(value) {
			return nil, fmt.Errorf("nonfinite artifact delta")
		}
		if d.Route == StaticReplacement {
			if _, ok := d.bounds[key]; !ok && value != 0 {
				return nil, fmt.Errorf("artifact coordinate outside replacement proof: %s", key)
			}
		}
		result[key] = value
	}
	for key, value := range d.bias {
		result[key] += value
		if !finite(result[key]) {
			return nil, fmt.Errorf("nonfinite composed delta")
		}
	}
	return result, nil
}

func finite(value float64) bool { return !math.IsNaN(value) && !math.IsInf(value, 0) }

func graphCoordinates(members []contracts.IRSeedMember) []string {
	seen := map[string]bool{}
	for _, member := range members {
		for _, node := range member.Nodes {
			if node.Operation == "artifact_stat" {
				seen[node.Coordinate] = true
			}
		}
	}
	keys := make([]string, 0, len(seen))
	for key := range seen {
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}

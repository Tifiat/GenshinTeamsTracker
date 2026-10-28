package seteffects

import (
	"encoding/json"
	"fmt"
	"os"
	"sort"
)

// Diagnostic approximation only. This still pays the initial replay. Collapse
// constant sampled stat values across time to their mean/observed peak, with
// the exact owner/read mode/stat-key/attack identity retained. Any symbolic
// component is wholly untouched. This is not a source
// maximum, a time-weighted uptime, or a guaranteed bound.
func (b *NeutralBinding) hypothesisApproximate(component NeutralExpressions) []float64 {
	raw := component.raw
	mode := os.Getenv("GTT_HYPOTHESIS_UPTIME")
	if mode != "mean" && mode != "peak" {
		return raw
	}
	for _, expression := range component.Effects {
		if expression != nil && expression.Operation != "constant" {
			return raw
		}
	}
	out := append([]float64(nil), raw...)
	changed := 0
	b.hypothesisPrepareUptimeGroups()
	for _, ids := range b.hypothesisUptimeGroups {
		different := false
		for _, id := range ids {
			if raw[id] != raw[ids[0]] {
				different = true
				break
			}
		}
		if !different {
			continue
		}
		value := raw[ids[0]]
		if mode == "mean" {
			value = 0
		}
		for _, id := range ids {
			if mode == "mean" {
				value += raw[id]
			} else if raw[id] > value {
				value = raw[id]
			}
		}
		if mode == "mean" {
			value /= float64(len(ids))
		}
		for _, id := range ids {
			if out[id] != value {
				changed++
			}
			out[id] = value
		}
	}
	if changed > 0 {
		fmt.Printf("HYPOTHESIS_UPTIME mode=%s changed_ports=%d\n", mode, changed)
	}
	return out
}

// Prepare once per immutable captured binding, bounded by its port count.
func (b *NeutralBinding) hypothesisPrepareUptimeGroups() {
	if b.hypothesisUptimePrepared {
		return
	}
	b.hypothesisUptimePrepared = true
	for _, member := range b.members {
		groups := map[string][]int{}
		for _, p := range member.ports {
			if p.curve != nil || (p.query.Kind != "stat" && p.query.Kind != "attack") {
				continue
			}
			q := p.query
			key, err := json.Marshal([]any{q.Owner, q.Kind, q.Stat, q.Mode, q.StatKeys, q.Attack, q.Target})
			if err != nil {
				panic(err)
			}
			groups[string(key)] = append(groups[string(key)], p.dimension)
		}
		keys := make([]string, 0, len(groups))
		for key := range groups {
			keys = append(keys, key)
		}
		sort.Strings(keys)
		for _, key := range keys {
			b.hypothesisUptimeGroups = append(b.hypothesisUptimeGroups, groups[key])
		}
	}
}

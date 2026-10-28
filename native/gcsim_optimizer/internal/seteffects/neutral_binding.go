package seteffects

// Binds the event rule producer to exact preserved ports of ONE neutral graph
// panel. Package evaluation never parses/rebuilds a damage formula. Missing rule
// values are returned as unknown, not installed as zero-valued corrections.
import (
	"fmt"
	"math"
	"sort"
	"strconv"

	"genshinteamstracker/native/gcsim_optimizer/internal/contracts"
	"genshinteamstracker/native/gcsim_optimizer/internal/formula"
)

type neutralBoundPort struct {
	dimension            int
	query                RuleQuery
	resistance, observed float64
	curve                *ScalarSlice
}
type neutralBoundMember struct {
	neutral    *contracts.NeutralInputs
	ports      []neutralBoundPort
	queries    []RuleQuery
	queryOrder []int
	reads      *neutralReadIndex
}
type NeutralBinding struct {
	familySerial             uint64
	twoPieceFamilies         map[[32]byte]bool
	composedPayloads         map[string]NeutralExpressions
	composedPayloadOrder     []string
	composedPayloadValues    int
	composedPayloadNodes     int
	components               map[RuleChoice]neutralComponent
	catalog                  *SourceCatalog
	members                  []neutralBoundMember
	ports                    []formula.EffectPort
	keys                     []string
	reads                    []formula.ReadRoot
	groups                   map[string]neutralComponent
	groupOrder               []string
	groupValues              int
	componentExpressionNodes int
	stats                    NeutralPreparationStats
}
type NeutralEffectVector struct {
	Values      []float64
	Known       []bool
	Boundaries  []string
	Uncertainty []string
}

// Sidecars must already have passed engineclient's exact graph/config/source
// validation. This constructor rechecks the shared source and neutral contract;
// it does not accept client-authored activation certificates.
func NewNeutralBinding(catalog *SourceCatalog, sidecars []contracts.EffectInputsOutput) (*NeutralBinding, error) {
	if catalog == nil || len(sidecars) == 0 {
		return nil, fmt.Errorf("neutral binding requires source and members")
	}
	b := &NeutralBinding{catalog: catalog, components: map[RuleChoice]neutralComponent{}}
	for mi, sidecar := range sidecars {
		n := sidecar.Neutral
		if sidecar.SourceManifestBodySHA256 != catalog.SourceManifestSHA256 || n == nil || !n.Context.NoSets || n.Context.DurationFrames <= 0 || n.World == nil || !n.World.Complete || n.Ledger.Truncated {
			return nil, fmt.Errorf("neutral member lacks bound event/world evidence")
		}
		owners := map[string]int{}
		for i, c := range n.Context.Characters {
			if c.Index != i || c.Key == "" {
				return nil, fmt.Errorf("neutral owner order invalid")
			}
			owners[c.Key] = i
		}
		member := neutralBoundMember{neutral: n, reads: indexNeutralReads(n)}
		for _, read := range n.Reads {
			observed, err := strconv.ParseFloat(read.Observed, 64)
			if err != nil || !finite(observed) {
				return nil, fmt.Errorf("invalid neutral read witness")
			}
			b.reads = append(b.reads, formula.ReadRoot{Member: mi, NodeID: read.NodeID, Key: neutralReadKey(mi, read.NodeID), Observed: observed})
		}
		active := func(order uint64) int {
			i := sort.Search(len(n.World.States), func(i int) bool { return n.World.States[i].Order > order }) - 1
			if i < 0 {
				return -1
			}
			return n.World.States[i].Active
		}
		hits := map[uint64]contracts.NeutralHitPoint{}
		for _, h := range n.Hits {
			hits[h.HitID] = h
		}
		effects := map[string]contracts.NeutralEffectPoint{}
		for _, e := range n.Effects {
			effects[e.EventID] = e
		}
		seen := map[uint32]bool{}
		add := func(node uint32, observed float64, p neutralBoundPort) error {
			if node == 0 || seen[node] || !finite(observed) {
				return fmt.Errorf("ambiguous neutral port")
			}
			seen[node] = true
			key := fmt.Sprintf("neutral:%d:%d", mi, node)
			p.dimension = len(b.keys)
			b.keys = append(b.keys, key)
			b.ports = append(b.ports, formula.EffectPort{Member: mi, NodeID: node, Key: key, Observed: observed})
			member.ports = append(member.ports, p)
			return nil
		}
		for _, p := range n.Stats {
			owner, ok := owners[p.Owner]
			if !ok {
				return nil, fmt.Errorf("unknown neutral stat owner")
			}
			q := RuleQuery{HitID: p.Point.HitID, Order: p.Point.Order, Frame: p.Point.Frame, Active: active(p.Point.Order), Owner: owner, Target: p.Point.TargetKey, Kind: p.Kind, Mode: p.Point.Mode, Stat: p.Stat, StatKeys: p.Point.StatKeys}
			if p.Kind == "attack" {
				h, ok := hits[p.Point.HitID]
				if !ok || h.Attack == nil || p.Point.Order != h.Point.AttackOrder {
					q.Attack = contracts.EventValue{Kind: "unknown", Text: "attack read metadata absent"}
				} else {
					q.Attack = *h.Attack
				}
			}
			if err := add(p.NodeID, 0, neutralBoundPort{query: q}); err != nil {
				return nil, err
			}
		}
		for _, p := range sidecar.EffectInputs {
			e, ok := effects[p.EventID]
			if !ok {
				return nil, fmt.Errorf("effect read missing neutral metadata")
			}
			owner, ok := owners[p.Owner]
			if !ok {
				return nil, fmt.Errorf("unknown neutral effect owner")
			}
			observed, err := strconv.ParseFloat(p.Observed, 64)
			if err != nil {
				return nil, err
			}
			q := RuleQuery{Order: e.Order, Frame: e.Frame, Active: active(e.Order), Owner: owner, Kind: p.Kind, Mode: "stat"}
			if p.Kind == "reaction_bonus" {
				q.Kind = "reaction"
			}
			if e.Input != nil {
				q.Attack = *e.Input
			} else {
				q.Attack = contracts.EventValue{Kind: "unknown", Text: "effect argument missing"}
			}
			if err := add(p.NodeID, observed, neutralBoundPort{query: q}); err != nil {
				return nil, err
			}
		}
		for _, p := range sidecar.ResistanceInputs {
			h, ok := hits[p.HitID]
			if !ok {
				return nil, fmt.Errorf("resistance read missing neutral hit")
			}
			resistance, err := strconv.ParseFloat(p.Resistance, 64)
			if err != nil {
				return nil, err
			}
			observed, err := strconv.ParseFloat(p.Observed, 64)
			if err != nil {
				return nil, err
			}
			var curve *ScalarSlice
			for i := range catalog.Curves {
				value, err := catalog.Curves[i].Evaluate(resistance)
				if err == nil && math.Abs(value-observed) < 1e-10*math.Max(1, math.Abs(observed)) {
					if curve != nil && (curve.SourceSHA256 != catalog.Curves[i].SourceSHA256 || curve.RecipeSHA256 != catalog.Curves[i].RecipeSHA256) {
						return nil, fmt.Errorf("ambiguous neutral resistance curve")
					}
					curve = &catalog.Curves[i]
				}
			}
			if curve == nil {
				return nil, fmt.Errorf("neutral resistance does not match source")
			}
			q := RuleQuery{Order: h.Point.HitOrder, Frame: h.Point.HitFrame, Active: active(h.Point.HitOrder), Owner: h.Actor, Target: p.TargetKey, Kind: "resistance", Mode: "stat", Stat: p.Element}
			q.TargetKeys, q.TargetStateComplete = h.TargetKeys, h.TargetKeys != nil
			if err := add(p.NodeID, observed, neutralBoundPort{query: q, resistance: resistance, observed: observed, curve: curve}); err != nil {
				return nil, err
			}
		}
		member.queries = make([]RuleQuery, len(member.ports))
		member.queryOrder = make([]int, len(member.ports))
		for i, port := range member.ports {
			member.queries[i], member.queryOrder[i] = port.query, i
		}
		sort.SliceStable(member.queryOrder, func(i, j int) bool {
			return member.queries[member.queryOrder[i]].Order < member.queries[member.queryOrder[j]].Order
		})
		b.members = append(b.members, member)
	}
	return b, nil
}
func (b *NeutralBinding) Ports() []formula.EffectPort {
	return append([]formula.EffectPort(nil), b.ports...)
}
func (b *NeutralBinding) Keys() []string { return append([]string(nil), b.keys...) }
func (b *NeutralBinding) Reads() []formula.ReadRoot {
	return append([]formula.ReadRoot(nil), b.reads...)
}
func neutralReadKey(member int, node uint32) string {
	return fmt.Sprintf("neutral-read:%d:%d", member, node)
}

// Constructor-owned query slices are never changed by replay. Synthetic
// bindings assembled directly by tests retain the ordinary preparation path.
func (member neutralBoundMember) preparedQueries() ([]RuleQuery, []int) {
	if len(member.queries) == len(member.ports) && len(member.queryOrder) == len(member.ports) {
		return member.queries, member.queryOrder
	}
	queries := make([]RuleQuery, len(member.ports))
	for i, port := range member.ports {
		queries[i] = port.query
	}
	return queries, nil
}

func (b *NeutralBinding) EvaluatePackages(choices []RuleChoice) NeutralEffectVector {
	out := NeutralEffectVector{Values: make([]float64, len(b.keys)), Known: make([]bool, len(b.keys)), Boundaries: []string{}, Uncertainty: []string{}}
	boundaries, uncertainty := map[string]bool{}, map[string]bool{}
	for _, member := range b.members {
		queries, order := member.preparedQueries()
		r := b.catalog.replayNeutralRulesPrepared(member.neutral, choices, queries, false, order)
		if r.Boundary != "" {
			boundaries[r.Boundary] = true
			continue
		}
		for _, code := range r.Uncertainty {
			uncertainty[code] = true
		}
		for i, p := range member.ports {
			value := r.Values[i]
			if value.Expression != nil {
				boundaries["stat-dependent effect has not been bound to neutral read roots"] = true
				continue
			}
			if !value.Known {
				boundaries[value.Boundary] = true
				continue
			}
			if p.curve != nil {
				x, err := p.curve.Evaluate(p.resistance + value.Value)
				if err != nil {
					boundaries[err.Error()] = true
					continue
				}
				value.Value = x - p.observed
			}
			out.Values[p.dimension], out.Known[p.dimension] = value.Value, true
		}
	}
	for code := range boundaries {
		out.Boundaries = append(out.Boundaries, code)
	}
	for code := range uncertainty {
		out.Uncertainty = append(out.Uncertainty, code)
	}
	sort.Strings(out.Boundaries)
	sort.Strings(out.Uncertainty)
	return out
}
func (v NeutralEffectVector) Complete() bool {
	for _, ok := range v.Known {
		if !ok {
			return false
		}
	}
	return len(v.Boundaries) == 0
}
